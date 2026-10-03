#!/usr/bin/env python3
"""Contract for focus provenance accents and trust-following keyboard RGB.

Pins that the accent and RGB only mirror existing authority -- the surface
provenance resolver, the host trust claim and the rendered trust-model map --
and never originate an identity:

  * accent colour is bound to the resolved window and cleared when its
    provenance is lost; Sway reports unsupported instead of recolouring
    whatever is focused;
  * keyboard RGB defaults to off, follows the host claim or the focused
    surface only when chosen, only under the trust-model theme, with runtime
    scope and the operator's brightness;
  * anything that is not a validated identity holds;
  * a VFIO guest's console is presented as an emulated recovery display.
"""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import re
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import yaml


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/focus_accent.py"
RENDER = ROOT / "tools/theme_render.py"
MAP = ROOT / "themes/trust-model/rendered/hyperlab-rgb-map.json"
FILES = ROOT / "roles/host_desktop_common/files"
QML = FILES / "quickshell/hyperlab"
ADAPTER = FILES / "privatestack-compositor-adapter.sh"
BRIDGE = FILES / "privatestack-focus-accent.sh"
UNIT = FILES / "hyperlab-focus-accent.service"
TASKS = ROOT / "roles/host_desktop_common/tasks/main.yml"
THEME = ROOT / "roles/host_desktop_sway/files/privatestack-theme.sh"
SHELL_ACTIONS = FILES / "privatestack-shell-actions.py"
MACHINE_ACTIONS = FILES / "privatestack-machine-actions.py"
GROUP_VARS = ROOT / "group_vars/all/host-desktop.yml"

HOST_TRUST_UNCLAIMED = {"known": True, "claimed": False, "identity": None,
                        "level": None, "class": "ok"}
HOST_TRUST_DEV = {"known": True, "claimed": True, "identity": "dev",
                  "level": 2, "class": "warn"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"HyperLab focus provenance accent contract: {message}")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    require(spec is not None and spec.loader is not None, f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def provenance(trust, resolved=True):
    return {"resolved": resolved, "trust": trust,
            "guest_metadata_authoritative": False}


def check_mapping(accent) -> dict[str, str]:
    colours = accent.load_trust_map(MAP)
    canonical = load(RENDER, "theme_render_for_accent").EXPECTED_TRUST_COLORS

    require(
        {k: "#" + v for k, v in colours.items()} == canonical,
        "accent colours are not the canonical trust colours",
    )

    good = json.loads(text(MAP))

    for label, mutate in (
        ("non-uniform zones", lambda d: d["identities"]["dev"]["zones"].__setitem__(0, "ffffff")),
        ("missing identity", lambda d: d["identities"].pop("lab")),
        ("unreviewed provider", lambda d: d.__setitem__("provider", "openrgb")),
        ("wrong theme", lambda d: d.__setitem__("theme", "green")),
        ("bad hex", lambda d: d["identities"]["host"].__setitem__("zones", ["XYZ"] * 4)),
    ):
        document = json.loads(json.dumps(good))
        mutate(document)

        with tempfile.TemporaryDirectory() as name:
            path = Path(name) / "map.json"
            path.write_text(json.dumps(document), encoding="utf-8")

            try:
                accent.load_trust_map(path)
            except accent.AccentError:
                continue

        require(False, f"a tampered trust map was accepted: {label}")

    return colours


def check_plan(accent, colours) -> None:
    def plan(prov, trust=HOST_TRUST_UNCLAIMED, mode="off", theme="trust-model",
             app_id="foot"):
        return accent.plan(
            surface={"pid": 7, "app_id": app_id, "window_id": "0xabc"},
            provenance=prov, system_trust=trust, rgb_mode=mode, theme=theme,
            colours=colours,
        )

    host = plan(provenance("host"))
    require(host["accent"] == {"window_id": "0xabc", "identity": "host",
                               "state": "resolved", "color": "#8b949e"},
            "a host-native surface did not get the HOST accent")

    dev = plan(provenance("dev"), app_id="totally-host")
    require(dev["accent"]["color"] == "#5b8cff",
            "a resolved DEV surface did not get the DEV accent")

    for prov, state in ((provenance(None, resolved=False), "unresolved"),
                        (None, "unavailable"),
                        ({"resolved": True, "trust": "dev",
                          "guest_metadata_authoritative": True}, "unavailable"),
                        (provenance("unclassified"), "unavailable")):
        decided = plan(prov, app_id="dev")
        require(decided["accent"]["color"] is None
                and decided["accent"]["state"] == state,
                f"a surface without a resolved identity got a colour ({state})")

    # RGB: off is the default and holds.
    require(plan(provenance("dev"))["rgb"]["action"] == "hold"
            and accent.DEFAULT_RGB_MODE == "off",
            "keyboard RGB is driven by default")

    require(plan(provenance("dev"), mode="focus-trust", theme="green")
            ["rgb"]["reason"] == "theme-not-trust-model",
            "keyboard RGB was driven outside the trust-model theme")

    focus = plan(provenance("dev"), trust=HOST_TRUST_UNCLAIMED, mode="focus-trust")
    require(focus["rgb"] == {"mode": "focus-trust", "action": "set",
                             "identity": "dev", "zones": ["5b8cff"] * 4,
                             "reason": "focus-trust"},
            "focus-trust did not follow the focused surface")

    require(plan(provenance(None, resolved=False), mode="focus-trust")
            ["rgb"]["action"] == "hold",
            "focus-trust coloured an unresolved surface")

    system = plan(provenance("lab"), trust=HOST_TRUST_DEV, mode="system-trust")
    require(system["rgb"]["identity"] == "dev",
            "system-trust did not follow the host claim")

    require(plan(provenance("lab"), trust=HOST_TRUST_UNCLAIMED,
                 mode="system-trust")["rgb"]["identity"] == "host",
            "an unclaimed GPU did not present HOST")

    for trust in (
        {**HOST_TRUST_DEV, "level": 3},
        {**HOST_TRUST_DEV, "identity": "services", "level": None},
        {**HOST_TRUST_DEV, "identity": "host", "level": None},
        {**HOST_TRUST_DEV, "known": False},
        {**HOST_TRUST_DEV, "class": "error"},
        {**HOST_TRUST_UNCLAIMED, "identity": "dev"},
        None,
    ):
        require(plan(provenance("dev"), trust=trust, mode="system-trust")
                ["rgb"]["action"] == "hold",
                f"system-trust accepted an invalid claim: {trust}")


def live_fixture(argv):
    if argv[1] == "window-identities-json":
        return subprocess.CompletedProcess(argv, 0, json.dumps({"windows": [
            {"window_id": hex(i), "stable_id": format(i, "x")} for i in range(1, 256)]}))
    return None


def check_actuator(accent) -> None:
    calls: list[list[str]] = []
    replies: dict[str, object] = {}

    class Result:
        def __init__(self, code):
            self.returncode = code
            self.stdout = ""

    def run_command(argv):
        snapshot = live_fixture(argv)
        if snapshot is not None:
            return snapshot
        calls.append(argv)
        return Result(replies.get("adapter", 0))

    def nitro(argv):
        calls.append(["nitro", *argv])
        if argv[0] == "status":
            return replies.get("status")
        return replies.get("rgb", {"ok": True})

    accent.run_command = run_command
    accent.nitro = nitro

    with tempfile.TemporaryDirectory() as name:
        config = Path(name)
        actuator = accent.Actuator(ROOT, config, config / "runtime/none.json", config / "state")
        (config / "theme").write_text("trust-model")
        actuator.read_settings()

        def focus(window, prov):
            actuator.surface = {"pid": 7, "app_id": "x", "window_id": window}
            actuator.provenance = prov
            actuator.apply()

        focus("0x1", provenance("dev"))
        require(calls[-1] == [accent.ADAPTER, "focus-accent-set", "0x1", "#5b8cff", "1"],
                "the accent was not bound to the resolved window")

        before = len(calls)
        focus("0x1", provenance("dev"))
        require(len(calls) == before, "an unchanged accent was re-applied")

        focus("0x1", provenance(None, resolved=False))
        require(calls[-1] == [accent.ADAPTER, "focus-accent-clear", "0x1", "#d0d7deff", "1"],
                "a window that lost provenance kept its trust colour")

        before = len(calls)
        focus("0x2", None)
        require(len(calls) == before,
                "a window that never had an accent was touched")

        require(not any(c[0] == "nitro" for c in calls),
                "keyboard RGB was driven with the mode off")

        # Sway: unsupported is remembered, never retried as a global colour.
        replies["adapter"] = accent.ACCENT_UNSUPPORTED_EXIT
        focus("0x3", provenance("clean"))
        replies["adapter"] = 0
        before = len(calls)
        focus("0x4", provenance("lab"))
        require(not actuator.accent_supported and len(calls) == before,
                "an unsupported compositor kept receiving accents")

        # RGB, focus-trust, trust-model theme, brightness preserved.
        (config / "rgb-mode").write_text("focus-trust\n", encoding="utf-8")
        (config / "theme").write_text("trust-model\n", encoding="utf-8")
        require(actuator.read_settings(), "a mode change was not observed")
        replies["status"] = {"ok": True, "status": {
            "capabilities": {"per_zone": True},
            "runtime": {"per_zone": "fff00f,ff00ff,fff00f,ff00ff,37"}}}
        focus("0x5", provenance("dev"))
        require(calls[-1] == ["nitro", "rgb", "37", *["5b8cff"] * 4,
                              "--scope", "runtime"],
                "RGB did not keep brightness or used a persistent scope")

        before = len(calls)
        focus("0x6", provenance("dev"))
        require(len(calls) == before, "an unchanged RGB identity was rewritten")

        focus("0x7", provenance(None, resolved=False))
        require(len(calls) == before, "RGB followed an unresolved surface")

        replies["rgb"] = {"ok": False, "error": "RGB rate limit active"}
        focus("0x8", provenance("clean"))
        require(actuator.pending(), "a rate-limited write was not retried")

        actuator.rgb_retry_at = 0.0
        replies["status"] = {"ok": False, "error": "no socket"}
        before = len(calls)
        focus("0x9", provenance("lab"))
        after = len(calls)
        focus("0xa", provenance("lab"))
        require(after == before + 1 and len(calls) == after,
                "unavailable RGB was not backed off")


def check_sessions(accent) -> None:
    """Exercise writes against a live-state fake, including process replacement."""
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        config = root / "config"
        config.mkdir()
        (config / "theme").write_text("trust-model")
        registry = root / "runtime" / "surface-provenance.json"
        calls = []
        owned = {}
        manual = ["112233", "445566", "778899", "aabbcc"]
        live = [*manual, "37"]
        limited = False
        unavailable = False
        clear_failed = False

        def command(argv):
            snapshot = live_fixture(argv)
            if snapshot is not None:
                return snapshot
            calls.append(argv)
            if argv[1] == "focus-accent-clear":
                if clear_failed:
                    return type("Result", (), {"returncode": 1})()
                owned.pop(argv[2], None)  # Closed targets are harmless no-ops.
            else:
                owned[argv[2]] = argv[3]
            require(len(owned) <= 1, "two windows have active overrides")
            return type("Result", (), {"returncode": 0})()

        def nitro(argv):
            calls.append(["nitro", *argv])
            if unavailable:
                return None
            if argv[0] == "status":
                return {"ok": True, "status": {"capabilities": {"per_zone": True},
                        "runtime": {"per_zone": ",".join(live)}}}
            require(argv[-2:] == ["--scope", "runtime"], "non-runtime RGB write")
            if limited:
                return {"ok": False, "error": "rate limit"}
            live[:] = [*argv[2:6], argv[1]]
            return {"ok": True}

        def settings(mode, theme="trust-model"):
            (config / "rgb-mode").write_text(mode)
            (config / "theme").write_text(theme)
            actuator.read_settings()

        def focus(window, identity):
            actuator.surface = {"window_id": window}
            actuator.provenance = provenance(identity) if identity else None
            actuator.apply()

        with patch.object(accent, "run_command", command), patch.object(accent, "nitro", nitro):
            actuator = accent.Actuator(ROOT, config, registry, config / "state")
            focus("0xa", "dev")
            before = len(calls)
            focus("0xb", "host")
            require(calls[before:before + 2] == [
                [accent.ADAPTER, "focus-accent-clear", "0xa", "#d0d7deff", "a"],
                [accent.ADAPTER, "focus-accent-set", "0xb", "#8b949e", "b"]],
                "DEV -> HOST did not clear before set")
            before = len(calls)
            focus("0xb", "host")
            require(len(calls) == before, "same-window same-colour wrote again")
            focus("0xb", "dev")
            require(owned == {"0xb": "#5b8cff"}, "same-window identity did not update")
            clear_failed = True
            focus("0xc", "host")
            require(owned == {"0xb": "#5b8cff"}, "set proceeded after failed clear")
            clear_failed = False
            for prov in (None, provenance(None, False), {"resolved": True, "trust": "bad"}):
                focus("0xa", "dev")
                actuator.provenance = prov
                actuator.apply()
                require(not owned, "invalid/unavailable provenance retained accent")
            focus("0xa", "dev")
            focus("", "host")
            require(not owned, "missing window retained accent")
            focus("0xa", "dev")
            owned.clear()  # The compositor closed the exact owned window.
            focus("0xb", "host")
            require(owned == {"0xb": "#8b949e"}, "closed window blocked progress")
            actuator.shutdown()
            require(not owned and actuator.state.window is None, "shutdown left an accent")

            actuator = accent.Actuator(ROOT, config, registry, config / "state")
            focus("0xa", "dev")
            actuator.state.close()  # Simulate crash: do not invoke shutdown.
            actuator = accent.Actuator(ROOT, config, registry, config / "state")
            require(not owned and actuator.state.window is None, "restart did not clear old accent")
            settings("focus-trust")
            focus("0xa", "dev")
            require(live[:4] == ["5b8cff"] * 4 and actuator.state.baseline == manual,
                    "operator baseline not captured before trust write")
            state_path = actuator.state.path
            require(stat.S_IMODE(state_path.stat().st_mode) == 0o600
                    and stat.S_IMODE(state_path.parent.stat().st_mode) == 0o700,
                    "runtime modes unsafe")
            saved = json.loads(state_path.read_text())
            require(set(saved) == {"schema", "backend", "instance", "window", "neutralized"},
                    "state contains provenance authority")
            focus("0xb", "host")
            require(actuator.state.baseline == manual, "baseline was recaptured")
            before = live[:]
            focus("0xb", None)
            require(live == before, "unresolved focus did not HOLD")
            actuator.shutdown()
            actuator = accent.Actuator(ROOT, config, registry, config / "state")
            actuator.read_settings()
            focus("0xa", "dev")
            require(actuator.state.baseline == manual, "restart captured managed colours")
            live[4] = "81"
            settings("off")
            actuator.apply()
            require(live == [*manual, "81"] and actuator.state.baseline is None,
                    "off did not restore baseline with live brightness")
            before = len(calls)
            actuator.apply()
            require(len(calls) == before, "off with no baseline wrote RGB")

            settings("system-trust")
            actuator.system_trust = HOST_TRUST_DEV
            actuator.apply()
            settings("system-trust", "green")
            actuator.apply()
            require(live[:4] == manual and actuator.state.baseline is None,
                    "theme exit did not restore operator zones")

            settings("focus-trust")
            focus("0xa", "dev")
            actuator.shutdown()
            (config / "rgb-mode").write_text("off")
            actuator = accent.Actuator(ROOT, config, registry, config / "state")
            actuator.read_settings()
            actuator.apply()
            require(live[:4] == manual and actuator.state.baseline is None,
                    "restart in off did not restore pre-management baseline")

            settings("focus-trust")
            limited = True
            focus("0xa", "dev")
            focus("0xb", "host")
            limited = False
            actuator.rgb_retry_at = 0
            actuator.apply()
            require(live[:4] == ["8b949e"] * 4, "stale retry overwrote newer HOST")
            settings("off")
            unavailable = True
            actuator.apply()
            require(actuator.state.baseline == manual, "failed restore lost ownership")
            unavailable = False
            actuator.rgb_unavailable_until = 0
            actuator.apply()
            require(live[:4] == manual, "restore did not recover from unavailable Nitro")
            actuator.shutdown()



def check_generations(accent) -> None:
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        config = root / "config"
        config.mkdir()
        (config / "rgb-mode").write_text("focus-trust")
        (config / "theme").write_text("trust-model")
        writes = []
        manual = ["123456", "234567", "345678", "456789"]
        live = [*manual, "42"]
        limited = False
        status_hook = None

        def command(argv):
            snapshot = live_fixture(argv)
            if snapshot is not None:
                return snapshot
            writes.append((actuator.focus_generation, "border", argv))
            return type("Result", (), {"returncode": 0})()

        def nitro(argv):
            nonlocal status_hook
            if argv[0] == "status":
                if status_hook:
                    hook, status_hook = status_hook, None
                    hook()
                return {"ok": True, "status": {"capabilities": {"per_zone": True},
                        "runtime": {"per_zone": ",".join(live)}}}
            writes.append((actuator.focus_generation, "rgb", argv))
            if limited:
                return {"ok": False, "error": "rate limit"}
            live[:] = [*argv[2:6], argv[1]]
            return {"ok": True}

        def resolve(_resolver, _repo, surface, _registry):
            return provenance("dev" if surface["pid"] == 1 else "host")

        def event(pid):
            return json.dumps({"pid": pid, "window_id": "0xa" if pid == 1 else "0xb"})

        def zones_since(index):
            return [argv[2:6] for _, kind, argv in writes[index:] if kind == "rgb"]

        with patch.object(accent, "run_command", command), \
             patch.object(accent, "nitro", nitro), \
             patch.object(accent, "resolve_focus", resolve):
            actuator = accent.Actuator(ROOT, config, root / "runtime" / "registry.json", config / "state")
            actuator.read_settings()
            limited = True
            actuator.on_focus(event(1))
            actuator.apply()
            require(actuator.rgb_retry_at > 0, "DEV retry not scheduled")
            actuator.on_focus(event(2))
            require(actuator.focus_generation == 2 and actuator.rgb_retry_at == 0
                    and actuator.provenance is None, "new focus did not invalidate immediately")
            index = len(writes)
            limited = False
            actuator.apply()
            actuator.apply()
            require(zones_since(index) == [["8b949e"] * 4], "stale DEV retry after HOST")

            # Real pipes: both focus lines are readable before apply. No sleeps.
            fr, fw = os.pipe()
            tr, tw = os.pipe()
            with os.fdopen(fr, "rb", buffering=0) as focus_stream, \
                 os.fdopen(tr, "rb", buffering=0) as trust_stream:
                pump = accent.InputPump([(focus_stream, actuator.on_focus),
                                         (trust_stream, actuator.on_trust)], actuator)
                actuator.refresh_inputs = pump.drain
                index = len(writes)
                generation = actuator.focus_generation
                os.write(fw, (event(1) + "\n" + event(2) + "\n").encode())
                actuator.apply()
                require(actuator.focus_generation == generation + 2,
                        "queued focus lines were hidden by buffering")
                require(all(argv[3] != "#5b8cff" for _, kind, argv in writes[index:]
                            if kind == "border") and ["5b8cff"] * 4 not in zones_since(index),
                        "queued stale DEV presentation escaped")
                index = len(writes)
                os.write(fw, (event(1) + "\n" + event(2) + "\n" + event(1) + "\n").encode())
                actuator.apply()
                require(zones_since(index) == [["5b8cff"] * 4]
                        and all(gen == actuator.focus_generation for gen, kind, argv in writes[index:]
                                if kind == "rgb" or argv[1] == "focus-accent-set"),
                        "DEV/HOST/DEV applied an obsolete generation")

                # New focus arrives during a blocking Nitro status call.
                actuator.rgb_applied = None
                status_hook = lambda: os.write(fw, (event(2) + "\n").encode())
                index = len(writes)
                actuator.apply()
                require(not zones_since(index), "old intent wrote after status observed newer focus")
                actuator.apply()
                require(zones_since(index) == [["8b949e"] * 4], "current HOST did not converge")

                # A resolver result for A cannot be installed after B arrives.
                def delayed(*args):
                    os.write(fw, (event(2) + "\n").encode())
                    return provenance("dev")

                actuator.on_focus(event(1))
                index = len(writes)
                with patch.object(accent, "resolve_focus", delayed):
                    actuator.apply()
                require(actuator.provenance is None and not zones_since(index),
                        "A resolver result accepted for B")
                actuator.apply()
                require(actuator.provenance["trust"] == "host", "B resolution lost")
                old_token = actuator.correlation()
                old_plan = accent.plan(surface=actuator.surface, provenance=actuator.provenance,
                                       system_trust=None, rgb_mode="focus-trust",
                                       theme="trust-model", colours=actuator.colours)
                actuator.on_focus(event(1))
                index = len(writes)
                actuator.apply_rgb(old_plan["rgb"], old_token)
                actuator.apply_accent(old_plan["accent"], old_token)
                require(len(writes) == index, "old window/token could mutate current focus")
                actuator.refresh_inputs = actuator.read_settings
            os.close(fw)
            os.close(tw)

            # Mode/theme exit must restore, even with an old rate-limited request.
            for path, value in (("rgb-mode", "off"), ("theme", "green")):
                (config / "rgb-mode").write_text("focus-trust")
                (config / "theme").write_text("trust-model")
                actuator.read_settings()
                actuator.on_focus(event(1))
                limited = True
                actuator.apply()
                require(actuator.rgb_retry_at > 0, "expected pending retry")
                (config / path).write_text(value)
                index = len(writes)
                limited = False
                actuator.apply()
                actuator.apply()
                require(zones_since(index) == [manual] and actuator.state.baseline is None,
                        "stale DEV overwrote operator restore")

            (config / "theme").write_text("trust-model")
            (config / "rgb-mode").write_text("system-trust")
            actuator.on_trust(json.dumps(HOST_TRUST_DEV))
            limited = True
            actuator.apply()
            require(actuator.rgb_retry_at > 0, "system retry not scheduled")
            actuator.on_trust(json.dumps(HOST_TRUST_UNCLAIMED))
            index = len(writes)
            limited = False
            actuator.apply()
            require(zones_since(index) == [["8b949e"] * 4], "stale system trust retry")
            actuator.shutdown()


def check_service_shutdown(accent) -> None:
    """Exercise run's finally through the actual installed signal callbacks."""
    for sig in (signal.SIGTERM, signal.SIGHUP):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            (root / "theme").write_text("trust-model")
            registry = root / "hyperlab" / "surface-provenance.json"
            calls = []

            def command(argv, calls=calls):
                snapshot = live_fixture(argv)
                if snapshot is not None:
                    return snapshot
                calls.append(argv)
                return type("Result", (), {"returncode": 0})()

            class Selector:
                def register(self, *_args):
                    pass

                def select(self, _timeout, sig=sig):
                    signal.getsignal(sig)(sig, None)

                def close(self):
                    pass

            class Process:
                stdout = object()

                def poll(self):
                    return None

                def terminate(self):
                    pass

            with patch.object(accent, "run_command", command):
                actuator = accent.Actuator(ROOT, root, registry, root / "state")
                actuator.surface = {"window_id": "0xa"}
                actuator.provenance = provenance("dev")
                actuator.apply()
                # Keep this owned window through startup apply to exercise finally.
                actuator.surface = {"window_id": "0xa"}
                actuator.provenance = provenance("dev")
                with patch.object(accent, "Actuator", return_value=actuator), \
                     patch.object(accent, "spawn", return_value=Process()), \
                     patch.object(accent, "InputPump"), \
                     patch.object(accent.selectors, "DefaultSelector", return_value=Selector()):
                    require(accent.run(ROOT) == 0, "normal termination did not finish cleanly")
                require(calls[-1] == [accent.ADAPTER, "focus-accent-clear", "0xa", "#d0d7deff", "a"]
                        and actuator.state.window is None, "signal shutdown skipped cleanup")


def check_hardening(accent) -> None:
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        config = root / "config"
        config.mkdir()
        runtime = root / "runtime"
        runtime.mkdir(mode=0o700)
        registry = runtime / "hyperlab" / "registry.json"
        state_dir = root / "state" / "hyperlab"
        calls = []
        manual = ["123456", "234567", "345678", "456789"]
        live = [*manual, "42"]
        clear_code = 0

        def command(argv):
            snapshot = live_fixture(argv)
            if snapshot is not None:
                return snapshot
            calls.append(argv)
            return type("Result", (), {"returncode": clear_code
                        if argv[1] == "focus-accent-clear" else 0})()

        def nitro(argv):
            calls.append(["nitro", *argv])
            if argv[0] == "status":
                return {"ok": True, "status": {"capabilities": {"per_zone": True},
                        "runtime": {"per_zone": ",".join(live)}}}
            require(argv[-2:] == ["--scope", "runtime"], "non-runtime RGB write")
            live[:] = [*argv[2:6], argv[1]]
            return {"ok": True}

        def create():
            return accent.Actuator(ROOT, config, registry, state_dir)

        def focus(a, identity="dev"):
            a.surface = {"window_id": "0xa"}
            a.provenance = provenance(identity)
            a.apply()

        (config / "theme").write_text("trust-model")
        (config / "rgb-mode").write_text("focus-trust")
        with patch.object(accent, "run_command", command), patch.object(accent, "nitro", nitro):
            a = create()
            focus(a)
            require(a.state.baseline == manual, "initial baseline wrong")
            data = json.loads(a.state.rgb.record.path.read_text())
            require(set(data) == {"schema", "boot_id", "zones", "owned"},
                    "persistent state contains presentation/trust authority")
            require(stat.S_IMODE(a.state.rgb.record.path.stat().st_mode) == 0o600
                    and stat.S_IMODE((state_dir / "focus-accent").stat().st_mode) == 0o700,
                    "persistent permissions unsafe")
            a.shutdown()
            shutil.rmtree(runtime)  # Simulate logout without linger.
            runtime.mkdir(mode=0o700)  # Session manager, not the actuator, recreates it.
            a = create()
            focus(a)
            require(a.state.baseline == manual, "logout recaptured trust colour")
            live[4] = "91"
            (config / "rgb-mode").write_text("off")
            a.apply()
            require(live == [*manual, "91"], "logout/off did not restore original zones")
            # Every theme cycle neutralizes all prior receipts from intended palette.
            for theme in ("green", "trust-model", "violet", "trust-model"):
                (config / "theme").write_text(theme)
                before = len(calls)
                focus(a, "clean")
                writes = calls[before:]
                if theme != "trust-model":
                    require(not any(c[1] == "focus-accent-set" for c in writes),
                            "accent created outside trust-model")
                    require(a.state.window is None, "theme exit retained trust ownership")
                else:
                    require(any(c[1] == "focus-accent-set" and c[3] == "#72f2a5"
                                for c in writes), "current trust accent did not replace appearance")
            a.state.close()  # Crash with exact owned window.
            before = len(calls)
            with patch.dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE="new-instance"):
                a = create()
            require(len(calls) == before and a.state.window is None,
                    "old compositor instance received clear IPC")
            a.shutdown()
            # Manufacture valid ownership for the current instance, then change backend.
            a = create()
            focus(a)
            a.state.close()
            before = len(calls)
            with patch.dict(os.environ, HYPERLAB_COMPOSITOR_BACKEND="sway",
                            SWAYSOCK="/run/user/test/sway-session.sock"):
                a = create()
            require(len(calls) == before and a.state.window is None,
                    "Hyprland ownership reached Sway")
            a.shutdown()
            a = create()
            focus(a)
            a.state.close()
            before = len(calls)
            clear_code = accent.ACCENT_UNSUPPORTED_EXIT
            a = create()
            require(len(calls) == before + 1 and a.state.window is None
                    and not a.state.neutralized, "unsupported cleanup not terminal")
            a.apply()
            require(len(calls) == before + 1, "unsupported cleanup retried")
            a.shutdown()
            clear_code = 0
            # Valid previous boot baseline is discarded without a hardware restore.
            stale = {**data, "boot_id": "00000000-0000-0000-0000-000000000000"}
            rgb_path = state_dir / "focus-accent/focus-accent-rgb.json"
            rgb_path.write_text(json.dumps(stale))
            rgb_path.chmod(0o600)
            before = len(calls)
            a = create()
            a.apply()
            require(a.state.baseline is None and not rgb_path.exists()
                    and not any(c[0] == "nitro" for c in calls[before:]),
                    "previous boot restored stale colours")
            a.shutdown()
            # Bad runtime records are quarantined, never interpreted as IPC targets.
            window_path = registry.parent / "focus-accent-state.json"
            for bad in ("not JSON", json.dumps({"window": "0xdead"})):
                window_path.write_text(bad)
                window_path.chmod(0o600)
                before = len(calls)
                a = create()
                require(a.state.window is None and len(calls) == before,
                        "invalid window state caused IPC")
                focus(a)
                require(a.state.window == "0xa", "bad window state prevented border operation")
                a.shutdown()
            # Unsafe runtime entries are dropped without following targets.
            for kind in ("mode", "symlink", "owner"):
                window_path.unlink(missing_ok=True)
                outside = root / "outside-window-state"
                outside.write_text("untouched")
                if kind == "symlink":
                    window_path.symlink_to(outside)
                else:
                    window_path.write_text(json.dumps({"schema": 2, "backend": "hyprland",
                        "instance": "contract-instance", "window": "0xdead", "neutralized": []}))
                    window_path.chmod(0o644 if kind == "mode" else 0o600)
                real_fstat = accent.os.fstat

                def fake_owner(fd, real_fstat=real_fstat):
                    info = real_fstat(fd)
                    if Path(f"/proc/self/fd/{fd}").resolve() == window_path:
                        fields = list(info)
                        fields[4] = os.getuid() + 1
                        return os.stat_result(fields)
                    return info

                before = len(calls)
                with patch.object(accent.os, "fstat", fake_owner if kind == "owner" else real_fstat):
                    a = create()
                require(a.state.window is None and len(calls) == before,
                        "unsafe runtime state caused IPC")
                focus(a)
                require(a.state.window == "0xa", "unsafe runtime state blocked recovery")
                a.shutdown()
                require(outside.read_text() == "untouched", "runtime symlink target changed")
            # Each invalid persistent state disables RGB across successive startups.
            target = root / "untouched"
            target.write_text("operator file")
            for invalid in ("malformed", "mode", "symlink", "owner"):
                rgb_path.unlink(missing_ok=True)
                (state_dir / "focus-accent/focus-accent-rgb.json.invalid").unlink(missing_ok=True)
                if invalid == "symlink":
                    rgb_path.symlink_to(target)
                else:
                    rgb_path.write_text("bad" if invalid == "malformed" else json.dumps(data))
                    rgb_path.chmod(0o644 if invalid == "mode" else 0o600)
                original_fstat = accent.os.fstat

                def wrong_owner(fd, original_fstat=original_fstat):
                    info = original_fstat(fd)
                    if Path(f"/proc/self/fd/{fd}").resolve() == rgb_path:
                        fields = list(info)
                        fields[4] = os.getuid() + 1
                        return os.stat_result(fields)
                    return info

                with patch.object(accent.os, "fstat", wrong_owner if invalid == "owner" else original_fstat):
                    a = create()
                (config / "rgb-mode").write_text("focus-trust")
                before = len(calls)
                focus(a)
                require(a.state.rgb.degraded and a.state.baseline is None
                        and a.state.window == "0xa"
                        and not any(c[0] == "nitro" for c in calls[before:]),
                        "invalid RGB state captured/wrote or blocked borders")
                a.shutdown()
                a = create()
                require(a.state.rgb.degraded, "quarantine silently recovered after restart")
                a.shutdown()
            require(target.read_text() == "operator file", "state symlink target changed")
            # Directory validation never creates a missing session-manager runtime root.
            absent = root / "absent-runtime"
            a = accent.Actuator(ROOT, config, absent / "hyperlab/registry.json", state_dir)
            require(not absent.exists() and not a.state.enabled, "runtime root manufactured")
            a.shutdown()

        # Atomic replacement retains old RGB state on interrupted write.
        (state_dir / "focus-accent/focus-accent-rgb.json.invalid").unlink(missing_ok=True)
        rgb = accent.RGBState(state_dir)
        rgb.baseline = manual
        rgb.save()
        old = rgb.record.path.read_bytes()
        with patch.object(accent.os, "replace", side_effect=OSError("interrupted")):
            rgb.baseline = ["ffffff"] * 4
            try:
                rgb.save()
            except OSError:
                pass
        require(rgb.record.path.read_bytes() == old, "atomic state corrupted")


def check_border_fallback() -> None:
    """Real adapter + fake IPC: palette changes precede global reload deliberately."""
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        config = root / "config" / "hyperlab"
        config.mkdir(parents=True)
        bindir = root / "bin"
        bindir.mkdir()
        fake = bindir / "hyprctl"
        fake.write_text('#!/bin/sh\nprintf "%s\n" "$*"\n')
        fake.chmod(0o755)
        palette = root / "palettes"
        palette.mkdir()
        for theme in ("green", "violet", "trust-model"):
            source = (ROOT / "themes/trust-model/rendered" if theme == "trust-model" else
                      ROOT / "roles/host_desktop_sway/files/palette" / theme)
            (palette / theme).symlink_to(source, target_is_directory=True)
        env = dict(os.environ, XDG_CONFIG_HOME=str(config.parent),
                   HYPERLAB_PALETTE_ROOT=str(palette), PATH=str(bindir) + ":" + os.environ["PATH"],
                   HYPERLAB_COMPOSITOR_BACKEND="hyprland")
        for theme, colour in (("green", "7ee787ff"), ("trust-model", "d0d7deff"),
                              ("violet", "9d6cffff"), ("trust-model", "d0d7deff")):
            (config / "theme").write_text(theme)
            actuator = load(TOOL, "fallback_actuator").Actuator(
                ROOT, config, root / "runtime/registry.json", root / "state")
            actuator.palette_root = palette
            neutral = actuator.neutral_colour()
            actuator.shutdown()
            r = subprocess.run(["bash", str(ADAPTER), "focus-accent-clear", "0xa", neutral, "123"],
                               env=env, capture_output=True, text=True, check=False)
            require(r.returncode == 0 and f"rgba({colour})" in r.stdout
                    and "getoption" not in r.stdout and "unset" not in r.stdout,
                    "fallback copied stale global border or used unproven reset: " + r.stdout)
            require('stableid:123' in r.stdout and 'address:0xa' not in r.stdout,
                    "repaint still targets recycled addresses")
        for args in (["0xa", "green", "123"], ["0xa", "#d0d7deff", "bad;ipc"],
                     ["not-address", "#d0d7deff", "123"]):
            r = subprocess.run(["bash", str(ADAPTER), "focus-accent-clear", *args],
                               env=env, capture_output=True, text=True, check=False)
            require(r.returncode == 2 and not r.stdout, "invalid low-level args reached IPC")
        fake.write_text('#!/bin/sh\ncat <<\'DATA\'\n[{"address":"0xa","stableId":"123","mapped":true},{"address":"0xb","stableId":"124","mapped":false}]\nDATA\n')
        r = subprocess.run(["bash", str(ADAPTER), "window-identities-json"],
                           env=env, capture_output=True, text=True, check=False)
        require(r.returncode == 0 and json.loads(r.stdout) ==
                {"windows": [{"window_id": "0xa", "stable_id": "123"}]},
                "live-window adapter snapshot invalid")



def check_private_child(accent) -> None:
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        shared = root / "hyperlab"
        shared.mkdir(mode=0o755)
        shared.chmod(0o755)
        config = root / "config"
        config.mkdir()
        (config / "theme").write_text("trust-model")
        (config / "rgb-mode").write_text("system-trust")
        manual = ["123456", "234567", "345678", "456789"]

        def nitro(argv):
            if argv[0] == "status":
                return {"ok": True, "status": {"capabilities": {"per_zone": True},
                        "runtime": {"per_zone": ",".join([*manual, "45"])}}}
            return {"ok": True}

        with patch.object(accent, "nitro", nitro), \
             patch.dict(os.environ, XDG_STATE_HOME=str(root)):
            a = accent.Actuator(ROOT, config, root / "runtime/registry.json")
            a.on_trust(json.dumps(HOST_TRUST_DEV))
            a.apply()
            require(not a.state.rgb.degraded and a.state.baseline == manual,
                    "0755 shared parent disabled fresh-host RGB")
            record = shared / "focus-accent/focus-accent-rgb.json"
            require(stat.S_IMODE(shared.stat().st_mode) == 0o755
                    and stat.S_IMODE(record.parent.stat().st_mode) == 0o700
                    and stat.S_IMODE(record.stat().st_mode) == 0o600,
                    "private child/file modes or shared mode changed")
            data = record.read_text()
            a.shutdown()
        # Migrate a previously valid same-boot baseline, never recapture trust RGB.
        record.unlink()
        legacy = shared / "focus-accent-rgb.json"
        legacy.write_text(data)
        legacy.chmod(0o600)
        migrated = accent.RGBState(shared)
        require(migrated.baseline == manual and record.exists() and not legacy.exists(),
                "legacy operator baseline lost during private-directory migration")
        record.parent.chmod(0o755)
        require(accent.RGBState(shared).degraded, "unsafe dedicated child accepted")
        record.parent.chmod(0o700)
        shutil.rmtree(record.parent)
        other = root / "other"
        other.mkdir(mode=0o700)
        record.parent.symlink_to(other, target_is_directory=True)
        require(accent.RGBState(shared).degraded and not list(other.iterdir()),
                "symlink dedicated child followed")


def check_repaint_bound(accent) -> None:
    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        config = root / "config"
        config.mkdir()
        (config / "theme").write_text("trust-model")
        live = {hex(i): format(i + 1000, "x") for i in range(1, accent.MAX_REPAINT_RECEIPTS + 10)}
        writes = []
        reads = []

        def command(argv):
            if argv[1] == "window-identities-json":
                reads.append(argv)
                return subprocess.CompletedProcess(argv, 0, json.dumps({"windows": [
                    {"window_id": w, "stable_id": stable} for w, stable in live.items()]}))
            writes.append(argv)
            require(argv[4] in live.values(), "write reached closed/reused receipt")
            return subprocess.CompletedProcess(argv, 0, "ok")

        def focus(a, window):
            a.on_focus(json.dumps({"window_id": window, "pid": 7}))
            a.apply()

        with patch.object(accent, "run_command", command), \
             patch.object(accent, "resolve_focus", return_value=provenance("dev")):
            a = accent.Actuator(ROOT, config, root / "runtime/registry.json", root / "state")
            focus(a, "0x1")
            focus(a, "0x2")
            # First receipt closes, second address is reused by a different stable window.
            del live["0x1"]
            live["0x2"] = "ffff"
            before = len(writes)
            a.clear_accent()
            require(not a.state.neutralized and len(writes) == before,
                    "closed/reused addresses remained repaint eligible")
            for window in list(live):
                focus(a, window)
                require(len(a.state.neutralized) <= accent.MAX_REPAINT_RECEIPTS,
                        "receipt bound exceeded")
            require(len(a.state.neutralized) == accent.MAX_REPAINT_RECEIPTS,
                    "capacity fixture did not fill")
            require(a.state.window is None, "untracked accent created at capacity")
            # Per-call repaint work stays bounded, without evicting live owned windows.
            for theme, colour in (("green", "#7ee787ff"), ("trust-model", "#d0d7deff"),
                                  ("violet", "#9d6cffff"), ("trust-model", "#d0d7deff")):
                (config / "theme").write_text(theme)
                a.read_settings()
                before = len(writes)
                for _ in range(accent.MAX_REPAINT_RECEIPTS + 1):
                    turn = len(writes)
                    a.sync_neutralized(a.correlation())
                    require(len(writes) - turn <= accent.REPAINT_BATCH,
                            "repaint batch blocked unbounded work")
                require(len(writes) - before == accent.MAX_REPAINT_RECEIPTS
                        and all(cmd[3] == colour for cmd in writes[before:]),
                        "live modified windows failed to follow appearance cycles")
            # New input wins before the next repaint, even with a full queue.
            (config / "theme").write_text("green")
            a.read_settings()
            token = a.correlation()
            armed = True

            def refresh():
                nonlocal armed
                if armed:
                    armed = False
                    a.on_focus(json.dumps({"window_id": "0xff", "pid": 8}))
                a.read_settings()

            before = len(writes)
            a.refresh_inputs = refresh
            a.sync_neutralized(token)
            require(len(writes) == before and a.correlation() != token,
                    "stale repaint ignored newest focus generation")
            a.refresh_inputs = a.read_settings
            # Missing or malformed palette issues zero backend subprocesses each tick.
            a.palette_root = root / "missing-palettes"
            before = (len(writes), len(reads))
            for _ in range(20):
                a.sync_neutralized(a.correlation())
            require((len(writes), len(reads)) == before, "missing palette spawned retry storm")
            path = a.palette_root / "green/hyperlab-palette-hyprland.lua"
            path.parent.mkdir(parents=True)
            path.write_text("bad palette")
            for _ in range(20):
                a.sync_neutralized(a.correlation())
            require((len(writes), len(reads)) == before, "invalid palette spawned retry storm")
            path.write_text('active_border = "rgba(7ee787ff)"')
            a.sync_neutralized(a.correlation())
            require(len(writes) == before[0] + 1, "palette repair did not resume repaint")
            a.shutdown()
        # Oversized on-disk state is rejected, not replayed or silently evicted.
        record = root / "runtime/focus-accent-state.json"
        record.write_text(json.dumps({"schema": 3, "backend": "hyprland",
            "instance": "contract-instance", "window": None,
            "neutralized": {hex(i): format(i, "x") for i in range(1, 1000)}}))
        record.chmod(0o600)
        with patch.object(accent, "run_command", side_effect=AssertionError("unsafe IPC")):
            a = accent.Actuator(ROOT, config, root / "runtime/registry.json", root / "state")
            require(not a.state.neutralized, "oversized persisted history accepted")
            a.shutdown()


def check_static() -> None:
    adapter = text(ADAPTER)

    for marker in (
        "focus-accent-set|focus-accent-clear)",
        "${window} =~ ^0x[0-9a-f]{1,16}$",
        "${3:-} =~ ^#[0-9a-f]{6}([0-9a-f]{2})?$",
        "exit 3",
        'window = \\"stableid:${stable}\\"',
        "window-identities-json",
    ):
        require(marker in adapter, f"adapter accent contract lost: {marker}")

    sway_branch = adapter[adapter.index("focus-accent-set|focus-accent-clear)"):]
    sway_branch = sway_branch[:sway_branch.index("hyprland)")]
    require("run_swaymsg" not in sway_branch and "client.focused" not in sway_branch,
            "Sway gained a global, focus-following accent")

    bridge = text(BRIDGE)
    require('exec "${python}" -I -B "${actuator}" --repo "${checkout}" run' in bridge
            and "[[ $# -eq 1 && $1 == run ]] || usage" in bridge,
            "accent bridge lost its fixed exec")

    unit = text(UNIT)
    require("PartOf=graphical-session.target" in unit
            and "ExecStart=/usr/local/bin/privatestack-focus-accent run" in unit,
            "accent unit is not bound to the graphical session")

    tasks = text(TASKS)
    for marker in (
        "dest: /usr/local/bin/privatestack-focus-accent",
        "dest: /etc/systemd/user/hyperlab-focus-accent.service",
        "graphical-session.target.wants/hyperlab-focus-accent.service",
    ):
        require(marker in tasks, f"accent deployment lost: {marker}")

    stage = yaml.safe_load(text(GROUP_VARS))["host_desktop_common_shell_stage"]
    require(stage["keyboard_rgb_default_mode"] == "off"
            and stage["keyboard_rgb_modes"] == ["off", "system-trust", "focus-trust"],
            "RGB mode contract changed")

    theme = text(THEME)
    require("valid_rgb_mode \"${value}\" || value=off" in theme
            and "rgb-mode-toggle) toggle_rgb_mode ;;" in theme,
            "theme controller lost the RGB mode setting")

    require('"rgb-mode-toggle": (\n        "/usr/local/bin/privatestack-theme",\n'
            '        "rgb-mode-toggle",' in text(SHELL_ACTIONS),
            "shell action does not map to the theme controller")

    shared = "\n".join(text(p) for p in QML.glob("*.qml"))
    for forbidden in ("hyperlab-nitro-control", "focus-accent", "focus_accent",
                      "active_border", "set_prop"):
        require(forbidden not in shared,
                f"presentation QML gained accent or RGB authority: {forbidden}")

    tool = text(TOOL)
    require("--scope\", \"runtime\"" in tool and '\"--scope\", \"persistent\"' not in tool,
            "the actuator may write persistent RGB")
    require(re.search(r"hyperlab-rgb-map\.json", tool) is not None,
            "the actuator does not read the rendered trust map")

    machine = text(MACHINE_ACTIONS)
    require('"emulated-recovery" if vfio is True' in machine,
            "VFIO console semantics are not bridge-derived")

    state = text(QML / "ShellState.qml")
    pane = text(QML / "MachineContextPane.qml")
    require('const displays = ["primary", "emulated-recovery", "unknown"];' in state,
            "console display class is not validated")
    require('"Recovery console"' in pane
            and "desktop is on Looking Glass or the GPU output" in pane,
            "VFIO console wording lost")


def check_resolver_follows_checkout(accent) -> None:
    """A resolver pulled into the checkout is used without a new session."""
    import shutil

    with tempfile.TemporaryDirectory() as name:
        root = Path(name)
        repo = root / "repo"
        (repo / "tools").mkdir(parents=True)
        shutil.copy(ROOT / "tools/surface_provenance.py", repo / "tools/surface_provenance.py")
        (repo / "themes/trust-model/rendered").mkdir(parents=True)
        shutil.copy(ROOT / "themes/trust-model/rendered/hyperlab-rgb-map.json",
                    repo / "themes/trust-model/rendered/hyperlab-rgb-map.json")
        config = root / "config"
        config.mkdir()
        actuator = accent.Actuator(repo, config, root / "registry.json", root / "state")
        first = actuator.resolver

        actuator.ensure_current_resolver()
        assert actuator.resolver is first, "an unchanged resolver was reloaded"

        source = repo / "tools/surface_provenance.py"
        source.write_text(source.read_text() + "\nPULLED_MARKER = True\n")
        actuator.ensure_current_resolver()
        assert getattr(actuator.resolver, "PULLED_MARKER", False), "a pulled resolver was ignored"

        good = actuator.resolver
        source.write_text("def broken(:\n")
        actuator.ensure_current_resolver()
        assert actuator.resolver is good, "a broken resolver replaced the last good one"


def main() -> int:
    os.environ["HYPERLAB_COMPOSITOR_BACKEND"] = "hyprland"
    os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = "contract-instance"
    with tempfile.TemporaryDirectory() as name:
        palette = Path(name)
        for theme in ("green", "violet", "blue", "red", "trust-model"):
            source = (ROOT / "themes/trust-model/rendered" if theme == "trust-model" else
                      ROOT / "roles/host_desktop_sway/files/palette" / theme)
            (palette / theme).symlink_to(source, target_is_directory=True)
        with patch.dict(os.environ, HYPERLAB_PALETTE_ROOT=str(palette)):
            return run_checks()


def run_checks() -> int:
    accent = load(TOOL, "focus_accent_contract")
    colours = check_mapping(accent)
    check_plan(accent, colours)
    check_actuator(accent)
    check_sessions(accent)
    check_generations(accent)
    check_service_shutdown(accent)
    check_hardening(accent)
    check_border_fallback()
    check_private_child(accent)
    check_repaint_bound(accent)
    check_static()
    check_resolver_follows_checkout(accent)
    print("HyperLab focus provenance accent contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
