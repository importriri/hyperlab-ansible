#!/usr/bin/env python3
"""Focus provenance accents and trust-following keyboard RGB.

Pipeline:

focused host surface (compositor adapter, PID-bearing)
    -> reviewed surface provenance resolver
    -> trust identity
    -> rendered trust-model RGB map (the one identity -> colour table)
    -> focused-window accent + keyboard RGB

Authority stays where it already is. The resolver decides the focused
surface's identity; `hyperlabctl` publishes the host trust claim; the
rendered trust-model map, verified against the canonical colours by
theme_render, is the only identity -> colour table. This tool mirrors those
answers onto presentation and never originates one.

Accent: the colour is bound to the window it was resolved for, so an
identity can never follow focus onto another window. A surface without a
resolved identity carries no trust colour. Compositors that cannot bind a
colour to one window (Sway) get no accent rather than a global one.

Keyboard RGB modes, read from ~/.config/hyperlab/rgb-mode:

  off            the default: RGB is left exactly as the operator set it
  system-trust   follow the host trust claim (unclaimed GPU is HOST)
  focus-trust    follow the resolved identity of the focused surface

RGB is only driven while the trust-model theme is active, is written with
runtime scope only and keeps the operator's brightness. Anything that is not
a validated identity holds the current colours.
"""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import re
import selectors
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import ModuleType
from typing import Any


SCHEMA_VERSION = 1

IDENTITIES = (
    "host",
    "clean",
    "dev",
    "services",
    "dirty",
    "lab",
)

# The reviewed GPU handoff ladder. SERVICES and HOST are not rungs.
GPU_LADDER = {
    "clean": 3,
    "dev": 2,
    "dirty": 1,
    "lab": 0,
}

RGB_MODES = (
    "off",
    "system-trust",
    "focus-trust",
)

DEFAULT_RGB_MODE = "off"

RGB_THEME = "trust-model"

HEX6 = re.compile(r"[0-9a-f]{6}")

ADAPTER = "/usr/local/bin/privatestack-compositor-adapter"
HYPERLABCTL = "/usr/local/bin/hyperlabctl"
NITRO_CONTROL = "/usr/local/bin/hyperlab-nitro-control"

# The adapter's answer when the compositor cannot bind a colour to a window.
ACCENT_UNSUPPORTED_EXIT = 3

TICK_SECONDS = 2.0
RGB_RETRY_SECONDS = 0.3
RGB_UNAVAILABLE_BACKOFF_SECONDS = 60.0
COMMAND_TIMEOUT_SECONDS = 5.0
MAX_REPAINT_RECEIPTS = 32
REPAINT_BATCH = 1
REPAINT_RETRY_SECONDS = 60.0
STABLE_ID = re.compile(r"[0-9a-f]{1,16}")
WINDOW_ID = re.compile(r"0x[0-9a-f]{1,16}")


class AccentError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AccentError(message)


# ------------------------------------------------------------------ inputs


def load_trust_map(path: Path) -> dict[str, str]:
    """Identity -> RRGGBB from the rendered trust-model RGB map."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise AccentError(f"cannot read trust map: {path}") from exc

    require(isinstance(document, dict), "trust map is not a mapping")
    require(document.get("version") == 1, "unsupported trust map version")
    require(document.get("theme") == RGB_THEME, "trust map is not trust-model")
    require(
        document.get("provider") == "hyperlab-nitro-control"
        and document.get("capability") == "per_zone"
        and document.get("zones") == 4
        and document.get("zone_policy") == "uniform-trust-color",
        "trust map left the reviewed RGB contract",
    )

    identities = document.get("identities")

    require(
        isinstance(identities, dict) and set(identities) == set(IDENTITIES),
        "trust map identity set changed",
    )

    colours: dict[str, str] = {}

    for identity in IDENTITIES:
        entry = identities[identity]
        zones = entry.get("zones") if isinstance(entry, dict) else None

        require(
            isinstance(zones, list)
            and len(zones) == 4
            and all(isinstance(z, str) and HEX6.fullmatch(z) for z in zones)
            and len(set(zones)) == 1,
            f"trust map zones invalid for {identity}",
        )

        colours[identity] = zones[0]

    return colours


def read_choice(path: Path, allowed: tuple[str, ...], default: str) -> str:
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return default

    return value if value in allowed else default


def read_theme(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return ""


def system_identity(payload: Any) -> str | None:
    """The host trust claim, validated exactly as the shell validates it."""
    if (
        not isinstance(payload, dict)
        or payload.get("known") is not True
        or not isinstance(payload.get("claimed"), bool)
        or payload.get("class") == "error"
    ):
        return None

    if not payload["claimed"]:
        if payload.get("identity") is not None or payload.get("level") is not None:
            return None

        # No domain holds the GPU: the control plane is what is in charge.
        return "host"

    identity = payload.get("identity")

    if identity not in GPU_LADDER or payload.get("level") != GPU_LADDER[identity]:
        return None

    return identity


def focus_identity(provenance: Any) -> tuple[str | None, str]:
    """The focused surface's identity, and the resolution state behind it."""
    if not isinstance(provenance, dict):
        return None, "unavailable"

    if provenance.get("resolved") is not True:
        return None, "unresolved"

    trust = provenance.get("trust")

    if trust not in IDENTITIES or provenance.get("guest_metadata_authoritative") is not False:
        return None, "unavailable"

    return trust, "resolved"


# -------------------------------------------------------------------- plan


def plan(
    *,
    surface: dict[str, Any] | None,
    provenance: Any,
    system_trust: Any,
    rgb_mode: str,
    theme: str,
    colours: dict[str, str],
) -> dict[str, Any]:
    window_id = ""

    if isinstance(surface, dict) and isinstance(surface.get("window_id"), str):
        window_id = surface["window_id"]

    focused, focus_state = focus_identity(provenance)

    accent: dict[str, Any] = {
        "window_id": window_id,
        "identity": focused,
        "state": focus_state,
        "color": None if focused is None or theme != RGB_THEME else "#" + colours[focused],
    }

    rgb: dict[str, Any] = {
        "mode": rgb_mode,
        "action": "hold",
        "identity": None,
        "zones": None,
        "reason": "",
    }

    if rgb_mode not in RGB_MODES or rgb_mode == "off":
        rgb["reason"] = "rgb-mode-off"
    elif theme != RGB_THEME:
        rgb["reason"] = "theme-not-trust-model"
    else:
        identity = (
            focused
            if rgb_mode == "focus-trust"
            else system_identity(system_trust)
        )

        if identity is None:
            rgb["reason"] = (
                "focus-provenance-" + focus_state
                if rgb_mode == "focus-trust"
                else "system-trust-unavailable"
            )
        else:
            rgb.update({
                "action": "set",
                "identity": identity,
                "zones": [colours[identity]] * 4,
                "reason": rgb_mode,
            })

    return {
        "schema": SCHEMA_VERSION,
        "accent": accent,
        "rgb": rgb,
        "guest_metadata_authoritative": False,
    }


# ----------------------------------------------------------------- runtime


def load_resolver(repo: Path) -> ModuleType:
    path = repo / "tools/surface_provenance.py"
    spec = importlib.util.spec_from_file_location("hyperlab_surface_provenance", path)

    require(spec is not None and spec.loader is not None, f"cannot load {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def resolve_focus(
    resolver: ModuleType,
    repo: Path,
    surface: dict[str, Any],
    registry: Path,
) -> Any:
    try:
        return resolver.resolve(
            repo=repo,
            surface={
                "pid": surface.get("pid"),
                "app_id": surface.get("app_id"),
                "window_id": surface.get("window_id"),
            },
            registry=resolver.optional_registry(registry),
            proc_root=Path("/proc"),
        )
    except (OSError, TypeError, ValueError):
        return None


def run_command(argv: list[str]) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            argv,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def nitro(argv: list[str]) -> dict[str, Any] | None:
    result = run_command([NITRO_CONTROL, *argv])

    if result is None:
        return None

    try:
        answer = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    return answer if isinstance(answer, dict) else None


def emit(event: str, payload: dict[str, Any]) -> None:
    print(
        json.dumps({"event": event, **payload}, separators=(",", ":"), sort_keys=True),
        flush=True,
    )


def private_directory(directory: Path, *, runtime: bool = False) -> None:
    if runtime:
        # Never manufacture XDG_RUNTIME_DIR: the session manager owns it.
        info = directory.parent.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid(),
                "unsafe or missing runtime root")
        directory.mkdir(mode=0o700, exist_ok=True)
    else:
        require(directory.is_absolute() and directory.resolve() == directory,
                "symlinked state directory")
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        parent = directory.parent.lstat()
        require(stat.S_ISDIR(parent.st_mode) and parent.st_uid == os.getuid()
                and parent.st_mode & 0o022 == 0, "unsafe shared state parent")
    info = directory.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700, "unsafe presentation directory")


class PrivateRecord:
    def __init__(self, directory: Path, name: str, *, runtime: bool = False) -> None:
        self.path = directory / name
        self.quarantine = directory / (name + ".invalid")
        self.usable = True
        try:
            private_directory(directory, runtime=runtime)
        except (OSError, AccentError):
            self.usable = False

    def read(self) -> Any:
        require(self.usable, "unsafe state directory")
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            return None
        with os.fdopen(fd) as source:
            info = os.fstat(source.fileno())
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size < 1048576,
                    "unsafe presentation state")
            return json.load(source)

    def reject(self) -> None:
        if not self.usable:
            return
        try:
            # rename replaces a directory entry, never follows a hostile symlink.
            os.replace(self.path, self.quarantine)
        except FileNotFoundError:
            pass
        except OSError:
            self.usable = False

    def save(self, data: Any) -> None:
        require(self.usable, "unsafe state directory")
        if data is None:
            self.path.unlink(missing_ok=True)
            return
        fd, temporary = tempfile.mkstemp(prefix=".focus-accent-", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w") as target:
                json.dump(data, target)
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            Path(temporary).unlink(missing_ok=True)


def compositor_session() -> tuple[str, str]:
    backend = os.environ.get("HYPERLAB_COMPOSITOR_BACKEND")
    if not backend:
        backend = "hyprland" if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE") else "sway"
    instance = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE" if backend == "hyprland"
                              else "SWAYSOCK", "")
    return backend, instance


class RGBState:
    def __init__(self, directory: Path) -> None:
        self.record = PrivateRecord(directory / "focus-accent", "focus-accent-rgb.json")
        self.baseline: list[str] | None = None
        self.degraded = False
        self.boot_id = ""
        try:
            self.boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            require(re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}",
                                 self.boot_id) is not None, "invalid boot id")
            require(not os.path.lexists(self.record.quarantine), "RGB recovery required")
            data = self.record.read()
            legacy = directory / "focus-accent-rgb.json"
            migrating = data is None and os.path.lexists(legacy)
            require(not os.path.lexists(directory / "focus-accent-rgb.json.invalid"),
                    "legacy RGB recovery required")
            if migrating:
                # The shared parent may be 0755, but must be user-owned and not
                # writable by others. Read the old private file without following links.
                info = directory.lstat()
                require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                        and info.st_mode & 0o022 == 0, "unsafe legacy state parent")
                fd = os.open(legacy, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
                with os.fdopen(fd) as source:
                    info = os.fstat(source.fileno())
                    require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                            and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size < 4096,
                            "unsafe legacy RGB state")
                    data = json.load(source)
            if data is not None:
                require(isinstance(data, dict) and set(data) ==
                        {"schema", "boot_id", "zones", "owned"} and data["schema"] == 1
                        and type(data["schema"]) is int and data["owned"] is True
                        and isinstance(data["boot_id"], str)
                        and re.fullmatch(r"[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}",
                                         data["boot_id"]) is not None
                        and isinstance(data["zones"], list) and len(data["zones"]) == 4
                        and all(isinstance(z, str) and HEX6.fullmatch(z) for z in data["zones"]),
                        "invalid RGB state")
                if data["boot_id"] == self.boot_id:
                    self.baseline = data["zones"]
                else:
                    self.record.save(None)  # Reboot is not a request to restore old hardware state.
                if migrating:
                    self.save()
                    legacy.unlink()  # Only after the private replacement is durable.
        except (OSError, ValueError):
            self.record.reject()
            legacy = directory / "focus-accent-rgb.json"
            if self.record.usable and os.path.lexists(legacy):
                try:
                    os.replace(legacy, self.record.quarantine)
                except OSError:
                    pass  # Legacy entry remains and prevents recapture on restart.
            self.degraded = True
            emit("rgb-degraded", {"reason": "unsafe-state-operator-recovery-required"})

    def save(self) -> None:
        if self.degraded:
            return
        self.record.save(None if self.baseline is None else {
            "schema": 1, "boot_id": self.boot_id, "zones": self.baseline, "owned": True})


class PresentationState:
    """Instance-scoped cleanup receipts only; RGB lives separately across logout."""

    def __init__(self, directory: Path, rgb_directory: Path,
                 session: tuple[str, str]) -> None:
        self.record = PrivateRecord(directory, "focus-accent-state.json", runtime=True)
        self.path = self.record.path
        self.backend, self.instance = session
        self.window: str | None = None
        self.neutralized: dict[str, str] = {}
        self.lock: int | None = None
        self.rgb = RGBState(rgb_directory)
        self.enabled = self.record.usable and self.backend in ("hyprland", "sway") and bool(self.instance)
        if not self.enabled:
            self.rgb.degraded = True
            emit("accent-degraded", {"reason": "unsafe-runtime-or-missing-instance"})
            return
        try:
            self.lock = os.open(directory / "focus-accent.lock",
                                os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            info = os.fstat(self.lock)
            require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                    and stat.S_IMODE(info.st_mode) == 0o600, "unsafe presentation lock")
            fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, AccentError):
            self.close()
            self.enabled = False
            self.rgb.degraded = True
            emit("presentation-degraded", {"reason": "unsafe-or-busy-lock"})
            return
        try:
            data = self.record.read()
            if data is not None:
                require(isinstance(data, dict) and set(data) ==
                        {"schema", "backend", "instance", "window", "neutralized"}
                        and type(data["schema"]) is int and data["schema"] == 3
                        and data["backend"] in ("hyprland", "sway")
                        and isinstance(data["instance"], str) and bool(data["instance"])
                        and (data["window"] is None or (isinstance(data["window"], str)
                             and WINDOW_ID.fullmatch(data["window"])))
                        and isinstance(data["neutralized"], dict)
                        and len(data["neutralized"]) <= MAX_REPAINT_RECEIPTS
                        and all(isinstance(w, str) and WINDOW_ID.fullmatch(w)
                                and isinstance(stable, str) and STABLE_ID.fullmatch(stable)
                                for w, stable in data["neutralized"].items())
                        and (data["window"] is None or data["window"] in data["neutralized"]),
                        "invalid border state")
                if (data["backend"], data["instance"]) == session:
                    self.window = data["window"]
                    self.neutralized = dict(data["neutralized"])
                else:
                    self.record.save(None)  # No IPC against another compositor's addresses.
        except (OSError, ValueError):
            self.record.reject()
            self.enabled = self.record.usable
            emit("accent-state-dropped", {"reason": "unsafe-cleanup-record"})

    @property
    def baseline(self) -> list[str] | None:
        return self.rgb.baseline

    @baseline.setter
    def baseline(self, zones: list[str] | None) -> None:
        self.rgb.baseline = zones

    def save(self) -> None:
        if self.enabled:
            self.record.save(None if self.window is None and not self.neutralized else {
                "schema": 3, "backend": self.backend, "instance": self.instance,
                "window": self.window, "neutralized": self.neutralized})
        self.rgb.save()

    def close(self) -> None:
        if self.lock is not None:
            os.close(self.lock)
            self.lock = None


class Actuator:
    def __init__(self, repo: Path, config_dir: Path, registry: Path,
                 state_dir: Path | None = None) -> None:
        self.repo = repo
        self.resolver = load_resolver(repo)
        self.colours = load_trust_map(
            repo / "themes/trust-model/rendered/hyperlab-rgb-map.json"
        )
        self.mode_path = config_dir / "rgb-mode"
        self.theme_path = config_dir / "theme"
        self.registry = registry

        self.focus_generation = 0
        self.decision_revision = 0
        self.focus_pending = False
        self.refresh_inputs = self.read_settings
        self.surface: dict[str, Any] | None = None
        self.provenance: Any = None
        self.system_trust: Any = None
        self.rgb_mode = DEFAULT_RGB_MODE
        self.theme = ""

        self.accent_supported = True
        rgb_directory = state_dir or Path(os.environ.get("XDG_STATE_HOME") or
                                          Path.home() / ".local/state") / "hyperlab"
        self.state = PresentationState(registry.parent, rgb_directory, compositor_session())
        self.accent_supported = self.state.enabled and self.state.backend == "hyprland"
        self.palette_root = Path(os.environ.get("HYPERLAB_PALETTE_ROOT", "/usr/share/hyperlab/palettes"))
        self.palette_key: Any = None
        self.palette_colour: str | None = None
        self.repaint_key: Any = None
        self.repaint_pending: list[str] = []
        self.repaint_retry_at = 0.0
        self.cleanup_theme: str | None = None
        self.accent_colour: str | None = None
        self.checked_focus_generation = -1
        # Recover a crashed writer before any fresh presentation.
        self.clear_accent()

        self.rgb_applied: list[str] | None = None
        self.rgb_retry_at = 0.0
        self.rgb_unavailable_until = 0.0

    def read_settings(self) -> bool:
        mode = read_choice(self.mode_path, RGB_MODES, DEFAULT_RGB_MODE)
        theme = read_theme(self.theme_path)
        changed = (mode, theme) != (self.rgb_mode, self.theme)
        self.rgb_mode, self.theme = mode, theme

        if changed:
            # A new mode or theme is a new decision, not a repeat.
            self.rgb_applied = None
            self.invalidate_intent()

        return changed

    def invalidate_intent(self) -> None:
        self.decision_revision += 1
        self.rgb_retry_at = 0.0

    def correlation(self) -> tuple[int, str, int]:
        window = self.surface.get("window_id", "") if self.surface else ""
        return self.focus_generation, window, self.decision_revision

    def current(self, token: tuple[int, str, int]) -> bool:
        # Drain inputs again after blocking resolver/IPC/status work, before writes.
        self.refresh_inputs()
        return token == self.correlation()

    def on_focus(self, raw: str) -> None:
        self.focus_generation += 1
        self.invalidate_intent()
        self.provenance = None
        try:
            surface = json.loads(raw)
        except json.JSONDecodeError:
            surface = None
        self.surface = surface if isinstance(surface, dict) else None
        self.focus_pending = self.surface is not None
        window = self.surface.get("window_id") if self.surface else None
        if window != self.state.window:
            self.clear_accent()
        # Resolution is deferred until every queued focus line has been drained.

    def on_trust(self, raw: str) -> None:
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = None
        if value != self.system_trust:
            self.system_trust = value
            self.invalidate_intent()

    def apply(self) -> None:
        self.refresh_inputs()
        token = self.correlation()
        if self.focus_pending:
            surface = dict(self.surface)
            answer = resolve_focus(self.resolver, self.repo, surface, self.registry)
            if not self.current(token):
                return
            self.provenance = answer
            self.focus_pending = False
        decided = plan(
            surface=self.surface,
            provenance=self.provenance,
            system_trust=self.system_trust,
            rgb_mode=self.rgb_mode,
            theme=self.theme,
            colours=self.colours,
        )
        if not self.current(token):
            return
        self.apply_accent(decided["accent"], token)
        self.sync_neutralized(token)
        self.apply_rgb(decided["rgb"], token)

    def neutral_colour(self) -> str | None:
        # Presentation policy belongs here, never in the compositor translator.
        theme = read_theme(self.theme_path)
        if theme not in ("green", "violet", "blue", "red", "trust-model"):
            theme = "trust-model"
        path = self.palette_root / theme / "hyperlab-palette-hyprland.lua"
        try:
            info = path.stat()
            stamp = (info.st_ino, info.st_mtime_ns, info.st_size)
        except OSError:
            stamp = None
        key = (theme, stamp)
        if key != self.palette_key:
            self.palette_key, self.palette_colour = key, None
            try:
                match = re.search(r'active_border = "rgba\(([0-9a-f]{8})\)"',
                                  path.read_text(encoding="utf-8"))
                if match:
                    self.palette_colour = "#" + match.group(1)
            except (OSError, UnicodeError):
                pass
            if self.palette_colour is None:
                emit("accent-palette-unavailable", {"reason": "no-reviewed-neutral-border"})
        return self.palette_colour

    def live_windows(self) -> dict[str, str] | None:
        result = run_command([ADAPTER, "window-identities-json"])
        if result is not None and result.returncode == ACCENT_UNSUPPORTED_EXIT:
            self.accent_supported = False
            self.state.window, self.state.neutralized = None, {}
            self.state.save()
            return {}
        try:
            require(result is not None and result.returncode == 0, "live windows unavailable")
            data = json.loads(result.stdout)
            require(isinstance(data, dict) and isinstance(data.get("windows"), list),
                    "invalid live windows")
            live = {}
            for row in data["windows"]:
                require(isinstance(row, dict) and isinstance(row.get("window_id"), str)
                        and WINDOW_ID.fullmatch(row["window_id"])
                        and isinstance(row.get("stable_id"), str)
                        and STABLE_ID.fullmatch(row["stable_id"])
                        and row["window_id"] not in live, "invalid window identity")
                live[row["window_id"]] = row["stable_id"]
            return live
        except (ValueError, TypeError):
            return None

    def prune_receipts(self, live: dict[str, str]) -> None:
        retained = {window: stable for window, stable in self.state.neutralized.items()
                    if live.get(window) == stable}
        if retained != self.state.neutralized:
            self.state.neutralized = retained
            if self.state.window not in retained:
                self.state.window = None
                self.accent_colour = None
            self.state.save()

    def clear_accent(self) -> bool:
        if self.state.window is None:
            return True
        colour = self.neutral_colour()
        if colour is None:
            return False  # No IPC retries until palette data/selection actually changes.
        live = self.live_windows()
        if live is None:
            return False
        self.prune_receipts(live)
        window = self.state.window
        if window is None:
            return True
        result = run_command([ADAPTER, "focus-accent-clear", window, colour,
                              self.state.neutralized[window]])
        if result is not None and result.returncode == ACCENT_UNSUPPORTED_EXIT:
            self.accent_supported = False
            self.state.neutralized = {}
        elif result is None or result.returncode != 0:
            emit("accent-cleanup-pending", {})
            return False
        self.state.window = None
        self.accent_colour = None
        self.state.save()
        return True

    def sync_neutralized(self, token: tuple[int, str, int]) -> None:
        if not self.state.enabled or not self.state.neutralized:
            return
        colour = self.neutral_colour()
        if colour is None:
            return
        if self.repaint_key != self.palette_key:
            self.repaint_key = self.palette_key
            self.repaint_pending = list(self.state.neutralized)
            self.repaint_retry_at = 0.0
        if not self.repaint_pending or time.monotonic() < self.repaint_retry_at:
            return
        if not self.current(token):
            return
        live = self.live_windows()
        if live is None:
            self.repaint_retry_at = time.monotonic() + REPAINT_RETRY_SECONDS
            return
        self.prune_receipts(live)
        if not self.current(token):
            return
        for _ in range(REPAINT_BATCH):
            if not self.repaint_pending or not self.current(token):
                return
            window = self.repaint_pending.pop(0)
            if window == self.state.window or window not in self.state.neutralized:
                continue
            result = run_command([ADAPTER, "focus-accent-clear", window, colour,
                                  self.state.neutralized[window]])
            if not self.current(token):
                self.repaint_pending.insert(0, window)
                return
            if result is not None and result.returncode == ACCENT_UNSUPPORTED_EXIT:
                self.accent_supported = False
                self.state.window, self.state.neutralized = None, {}
                self.repaint_pending = []
                self.state.save()
                return
            if result is None or result.returncode != 0:
                self.repaint_pending.insert(0, window)
                self.repaint_retry_at = time.monotonic() + REPAINT_RETRY_SECONDS
                return
        if not self.repaint_pending:
            self.cleanup_theme = self.theme

    def shutdown(self) -> None:
        try:
            self.clear_accent()
        finally:
            # RGB ownership survives service restarts; only off/theme exit restores it.
            self.state.close()

    def apply_accent(self, accent: dict[str, Any], token: tuple[int, str, int]) -> None:
        if not self.current(token) or accent["window_id"] != token[1]:
            return
        window_id, colour = accent["window_id"], accent["color"]
        valid = (self.theme == RGB_THEME and isinstance(window_id, str) and WINDOW_ID.fullmatch(window_id)
                 and accent["state"] == "resolved" and accent["identity"] in IDENTITIES
                 and colour == "#" + self.colours[accent["identity"]])
        if not valid:
            self.clear_accent()
            return
        if self.state.window != window_id and not self.clear_accent():
            return  # Never own a second window while cleanup is outstanding.
        if not self.accent_supported or self.neutral_colour() is None:
            return
        if (self.state.window == window_id and self.accent_colour == colour
                and self.checked_focus_generation == self.focus_generation):
            return
        live = self.live_windows()
        if live is None:
            return
        self.prune_receipts(live)
        stable = live.get(window_id)
        if stable is None or not self.current(token):
            return
        self.checked_focus_generation = self.focus_generation
        if self.state.window == window_id and self.accent_colour == colour:
            return
        if window_id not in self.state.neutralized and len(self.state.neutralized) >= MAX_REPAINT_RECEIPTS:
            emit("accent-capacity", {"reason": "live-cleanup-receipts-full"})
            return  # Do not evict live ownership or create an untracked override.
        self.state.neutralized[window_id] = stable
        # Write-ahead cleanup intent also covers a crash between IPC and save.
        self.state.window = window_id
        self.state.save()
        if not self.current(token):
            return
        result = run_command([ADAPTER, "focus-accent-set", window_id, colour, stable])
        if result is not None and result.returncode == ACCENT_UNSUPPORTED_EXIT:
            self.accent_supported = False
            self.state.window = None
            self.state.neutralized.pop(window_id, None)
            self.state.save()
            emit("accent-unsupported", {})
        elif result is None or result.returncode != 0:
            self.accent_colour = None
            emit("accent-failed", {"window_id": window_id})
        else:
            self.accent_colour = colour
            self.state.save()
            emit("accent", {k: accent[k] for k in ("identity", "state")})

    def apply_rgb(self, rgb: dict[str, Any], token: tuple[int, str, int]) -> None:
        if not self.current(token):
            return
        if self.state.rgb.degraded:
            self.rgb_retry_at = 0.0
            return
        restoring = rgb["reason"] in ("rgb-mode-off", "theme-not-trust-model")
        zones = self.state.baseline if restoring else rgb["zones"]
        if zones is None or (not restoring and
                             (rgb["action"] != "set" or zones == self.rgb_applied)):
            self.rgb_retry_at = 0.0
            return

        now = time.monotonic()

        if now < self.rgb_unavailable_until or now < self.rgb_retry_at:
            return

        status = nitro(["status"])
        if not isinstance(status, dict) or not isinstance(status.get("status"), dict):
            status = None
        runtime = (
            status.get("status", {}).get("runtime", {})
            if status is not None and status.get("ok") is True
            else {}
        )
        capabilities = (
            status.get("status", {}).get("capabilities", {})
            if status is not None and status.get("ok") is True
            else {}
        )
        current = runtime.get("per_zone") if isinstance(runtime, dict) else None

        # Keep the operator's brightness: the last field of the live value.
        parts = current.split(",") if isinstance(current, str) else []

        if (
            not isinstance(capabilities, dict)
            or capabilities.get("per_zone") is not True
            or len(parts) != 5
            or not all(HEX6.fullmatch(z) for z in parts[:4])
            or not parts[4].isdigit()
            or not 0 <= int(parts[4]) <= 100
        ):
            self.rgb_unavailable_until = now + RGB_UNAVAILABLE_BACKOFF_SECONDS
            emit("rgb-unavailable", {})
            return

        if not self.current(token):
            return
        if not restoring and self.state.baseline is None:
            # Save before the first write so a crash cannot recapture trust colours.
            self.state.baseline = parts[:4]
            self.state.save()
        if not self.current(token):
            return
        answer = nitro(["rgb", parts[4], *zones, "--scope", "runtime"])
        if not self.current(token):
            # Ownership stays journalled, but obsolete results cannot schedule retries.
            self.rgb_applied = None
            return

        if answer is not None and answer.get("ok") is True:
            self.rgb_retry_at = 0.0
            self.rgb_applied = None if restoring else list(zones)
            if restoring:
                self.state.baseline = None
                self.state.save()
            emit("rgb", {"identity": rgb["identity"], "mode": rgb["mode"]})
            return

        if answer is not None and "rate limit" in str(answer.get("error", "")):
            self.rgb_retry_at = now + RGB_RETRY_SECONDS
            return

        self.rgb_unavailable_until = now + RGB_UNAVAILABLE_BACKOFF_SECONDS
        emit("rgb-failed", {"identity": rgb["identity"]})

    def pending(self) -> bool:
        return (self.focus_pending or self.rgb_retry_at > 0.0
                or bool(self.repaint_pending and self.palette_colour is not None
                        and time.monotonic() >= self.repaint_retry_at))


class SourceEnded(AccentError):
    pass


class InputPump:
    """Unbuffered nonblocking framing: selector readiness cannot hide read-ahead lines."""

    def __init__(self, streams: list[tuple[Any, Any]], actuator: Actuator) -> None:
        self.streams = streams  # Focus first, then system trust.
        self.buffers = {stream.fileno(): b"" for stream, _ in streams}
        self.actuator = actuator
        for stream, _ in streams:
            os.set_blocking(stream.fileno(), False)

    def drain(self) -> None:
        for stream, callback in self.streams:
            fd = stream.fileno()
            while True:
                try:
                    chunk = os.read(fd, 65536)
                except BlockingIOError:
                    break
                if not chunk:
                    raise SourceEnded("presentation source ended")
                self.buffers[fd] += chunk
                require(len(self.buffers[fd]) <= 1024 * 1024, "presentation source too large")
                while b"\n" in self.buffers[fd]:
                    line, self.buffers[fd] = self.buffers[fd].split(b"\n", 1)
                    callback(line.decode("utf-8", errors="replace"))
        self.actuator.read_settings()


def spawn(argv: list[str]) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
    )


def run(repo: Path) -> int:
    config_dir = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config") / "hyperlab"
    runtime_dir = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")

    actuator = Actuator(repo, config_dir, runtime_dir / "hyperlab/surface-provenance.json")
    processes: list[subprocess.Popen[bytes]] = []
    selector = selectors.DefaultSelector()

    def stop(_signum: int, _frame: Any) -> None:
        raise KeyboardInterrupt

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGTERM, signal.SIGHUP)}
    try:
        actuator.read_settings()
        actuator.apply()  # Recover RGB ownership even before the first focus event.
        streams = []
        for argv, callback in (
            ([ADAPTER, "focused-window-watch"], actuator.on_focus),
            ([HYPERLABCTL, "watch", "--field", "trust"], actuator.on_trust),
        ):
            process = spawn(argv)
            processes.append(process)
            assert process.stdout is not None
            selector.register(process.stdout, selectors.EVENT_READ)
            streams.append((process.stdout, callback))
        actuator.refresh_inputs = InputPump(streams, actuator).drain
        while True:
            timeout = RGB_RETRY_SECONDS if actuator.pending() else TICK_SECONDS
            selector.select(timeout)
            # apply drains all queued focus lines before resolving or retrying.
            actuator.apply()
    except SourceEnded:
        emit("source-ended", {})
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            actuator.shutdown()
        finally:
            selector.close()
            for process in processes:
                if process.poll() is None:
                    process.terminate()
            for sig, handler in previous.items():
                signal.signal(sig, handler)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("validate")
    sub.add_parser("run")

    one = sub.add_parser("plan")
    one.add_argument("--surface-json", required=True)
    one.add_argument("--provenance-json", required=True)
    one.add_argument("--trust-json", required=True)
    one.add_argument("--rgb-mode", required=True)
    one.add_argument("--theme", required=True)

    args = parser.parse_args()

    try:
        colours = load_trust_map(
            args.repo / "themes/trust-model/rendered/hyperlab-rgb-map.json"
        )

        if args.command == "validate":
            print("FOCUS_ACCENT_SCHEMA=1")
            print("ACCENT_SOURCE=HOST_OWNED_PROVENANCE")
            print("COLOUR_SOURCE=RENDERED_TRUST_MODEL_MAP")
            print("RGB_MODES=" + ",".join(RGB_MODES))
            print("RGB_DEFAULT=" + DEFAULT_RGB_MODE)
            print("FOCUS_ACCENT=PASS")
            return 0

        if args.command == "plan":
            print(json.dumps(plan(
                surface=json.loads(args.surface_json),
                provenance=json.loads(args.provenance_json),
                system_trust=json.loads(args.trust_json),
                rgb_mode=args.rgb_mode,
                theme=args.theme,
                colours=colours,
            ), separators=(",", ":"), sort_keys=True))
            return 0

        return run(args.repo)
    except (AccentError, json.JSONDecodeError, OSError) as exc:
        print(f"HyperLab focus accent: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
