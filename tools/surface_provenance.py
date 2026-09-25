#!/usr/bin/env python3
"""Resolve focused host surfaces to reviewed HyperLab trust provenance.

Security boundary:

* compositor metadata identifies a HOST PROCESS only;
* a HyperLab launcher registration binds that process to a managed VM;
* the VM specification supplies network_profile;
* network_profile maps to the visual trust identity.

Window title, guest application name, guest-supplied app metadata and wallpaper
content are never trust authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = 1

TRUST_IDENTITIES = (
    "clean",
    "dev",
    "services",
    "dirty",
    "lab",
)

MANAGED_SURFACE_KINDS = (
    "looking-glass",
    "spice-console",
)

EXPECTED_EXECUTABLES = {
    "looking-glass": "/usr/local/bin/looking-glass-client",
    "spice-console": "/usr/bin/virt-viewer",
}

# These identifiers are only a fail-closed hint that an unregistered surface
# looks like a managed transport. They NEVER assign trust.
MANAGED_APP_HINTS = {
    "looking-glass",
    "looking-glass-client",
    "virt-viewer",
    "remote-viewer",
}

REGISTRY_KEYS = {
    "version",
    "entries",
}

ENTRY_KEYS = {
    "pid",
    "process_start_ticks",
    "executable",
    "surface_kind",
    "domain",
    "spec_sha256",
    "registered_by",
}

SURFACE_KEYS = {
    "pid",
    "app_id",
    "window_id",
    "title",
}


class ProvenanceError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ProvenanceError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        value = yaml.safe_load(
            path.read_text(encoding="utf-8")
        )
    except (
        OSError,
        UnicodeDecodeError,
        yaml.YAMLError,
    ) as exc:
        raise ProvenanceError(
            f"cannot read YAML: {path}: {exc}"
        ) from exc

    require(
        isinstance(value, dict),
        f"YAML document is not a mapping: {path}",
    )

    return value


def proc_start_ticks(
    proc_root: Path,
    pid: int,
) -> str:
    stat_path = proc_root / str(pid) / "stat"

    try:
        text = stat_path.read_text(
            encoding="utf-8"
        ).strip()
    except OSError as exc:
        raise ProvenanceError(
            f"process stat unavailable for pid {pid}"
        ) from exc

    # /proc/PID/stat field 2 is wrapped in parentheses and may contain spaces.
    close = text.rfind(")")

    require(
        close >= 0,
        f"invalid process stat for pid {pid}",
    )

    remainder = text[close + 2:].split()

    # remainder[0] is original field 3 (state).
    # Original field 22 (starttime) is therefore remainder[19].
    require(
        len(remainder) > 19,
        f"process stat too short for pid {pid}",
    )

    value = remainder[19]

    require(
        value.isdigit(),
        f"invalid process start time for pid {pid}",
    )

    return value


def proc_executable(
    proc_root: Path,
    pid: int,
) -> str:
    path = proc_root / str(pid) / "exe"

    try:
        return str(path.resolve(strict=True))
    except OSError as exc:
        raise ProvenanceError(
            f"process executable unavailable for pid {pid}"
        ) from exc


def validate_surface(
    value: dict[str, Any],
) -> dict[str, Any]:
    require(
        isinstance(value, dict),
        "surface payload must be a mapping",
    )

    unknown = set(value) - SURFACE_KEYS

    require(
        not unknown,
        f"surface payload has unexpected keys: {sorted(unknown)}",
    )

    pid = value.get("pid")

    if pid is not None:
        require(
            isinstance(pid, int)
            and not isinstance(pid, bool)
            and pid > 0,
            "surface pid must be a positive integer or null",
        )

    for key in (
        "app_id",
        "window_id",
        "title",
    ):
        raw = value.get(key)

        require(
            raw is None or isinstance(raw, str),
            f"surface {key} must be string or null",
        )

    return {
        "pid": pid,
        "app_id": value.get("app_id") or "",
        "window_id": value.get("window_id") or "",
        # Intentionally retained only for diagnostics.
        "title": value.get("title") or "",
    }


def secure_registry_file(
    path: Path,
) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ProvenanceError(
            f"surface registry missing: {path}"
        ) from exc
    except OSError as exc:
        raise ProvenanceError(
            f"cannot inspect surface registry: {path}"
        ) from exc

    require(
        not stat.S_ISLNK(info.st_mode),
        "surface registry must not be a symlink",
    )

    require(
        stat.S_ISREG(info.st_mode),
        "surface registry must be a regular file",
    )

    require(
        info.st_uid == os.getuid(),
        "surface registry must be owned by current user",
    )

    require(
        stat.S_IMODE(info.st_mode) == 0o600,
        "surface registry mode must be exactly 0600",
    )


def load_registry(
    path: Path,
) -> dict[str, Any]:
    secure_registry_file(path)

    try:
        value = json.loads(
            path.read_text(encoding="utf-8")
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise ProvenanceError(
            f"invalid surface registry: {path}"
        ) from exc

    require(
        isinstance(value, dict),
        "surface registry must be a mapping",
    )

    require(
        set(value) == REGISTRY_KEYS,
        "surface registry key set changed",
    )

    require(
        value["version"] == 1,
        "unsupported surface registry version",
    )

    entries = value["entries"]

    require(
        isinstance(entries, list),
        "surface registry entries must be a list",
    )

    seen_pids: set[int] = set()

    for entry in entries:
        require(
            isinstance(entry, dict),
            "surface registry entry must be mapping",
        )

        require(
            set(entry) == ENTRY_KEYS,
            "surface registry entry key set changed",
        )

        pid = entry["pid"]

        require(
            isinstance(pid, int)
            and not isinstance(pid, bool)
            and pid > 0,
            "registry pid must be positive integer",
        )

        require(
            pid not in seen_pids,
            f"duplicate registry pid: {pid}",
        )

        seen_pids.add(pid)

        require(
            isinstance(
                entry["process_start_ticks"],
                str,
            )
            and entry["process_start_ticks"].isdigit(),
            "invalid registered process start time",
        )

        require(
            entry["surface_kind"]
            in MANAGED_SURFACE_KINDS,
            "unsupported managed surface kind",
        )

        require(
            entry["executable"]
            == EXPECTED_EXECUTABLES[
                entry["surface_kind"]
            ],
            "registered executable does not match surface kind",
        )

        require(
            isinstance(entry["domain"], str)
            and entry["domain"],
            "registered domain missing",
        )

        require(
            isinstance(entry["spec_sha256"], str)
            and len(entry["spec_sha256"]) == 64
            and all(
                char in "0123456789abcdef"
                for char in entry["spec_sha256"]
            ),
            "invalid registered spec sha256",
        )

        require(
            entry["registered_by"]
            == "hyperlabctl",
            "unreviewed provenance registrar",
        )

    return value


def optional_registry(
    path: Path | None,
) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "version": 1,
            "entries": [],
        }

    return load_registry(path)


def registry_entry_for_pid(
    registry: dict[str, Any],
    pid: int,
) -> dict[str, Any] | None:
    matches = [
        entry
        for entry in registry["entries"]
        if entry["pid"] == pid
    ]

    require(
        len(matches) <= 1,
        "multiple provenance entries for focused pid",
    )

    return matches[0] if matches else None


def spec_for_domain(
    repo: Path,
    domain: str,
) -> tuple[Path, dict[str, Any]]:
    vm_specs = repo / "vm-specs"

    require(
        vm_specs.is_dir(),
        f"vm-specs directory missing: {vm_specs}",
    )

    matches: list[tuple[Path, dict[str, Any]]] = []

    for path in sorted(vm_specs.glob("*.yml")):
        spec = load_yaml(path)

        if spec.get("name") == domain:
            matches.append((path, spec))

    require(
        len(matches) == 1,
        (
            "domain must resolve to exactly one "
            f"reviewed VM specification: {domain}"
        ),
    )

    return matches[0]


def managed_hint(
    app_id: str,
) -> bool:
    normalized = app_id.strip().lower()

    return normalized in MANAGED_APP_HINTS


def unresolved(
    *,
    surface: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "resolved": False,
        "presentation_identity": "host",
        "trust": None,
        "trust_source": None,
        "surface_class": "managed-unresolved",
        "reason": reason,
        "pid": surface["pid"],
        "domain": None,
        "network_profile": None,
        "guest_metadata_authoritative": False,
        "wallpaper_allowed": False,
        "rgb_allowed": False,
    }


def host_native(
    *,
    surface: dict[str, Any],
    reason: str,
) -> dict[str, Any]:
    return {
        "schema": SCHEMA_VERSION,
        "resolved": True,
        "presentation_identity": "host",
        "trust": "host",
        "trust_source": "host-native",
        "surface_class": "host-native",
        "reason": reason,
        "pid": surface["pid"],
        "domain": None,
        "network_profile": None,
        "guest_metadata_authoritative": False,
        "wallpaper_allowed": True,
        "rgb_allowed": True,
    }


def resolve(
    *,
    repo: Path,
    surface: dict[str, Any],
    registry: dict[str, Any],
    proc_root: Path,
) -> dict[str, Any]:
    surface = validate_surface(surface)

    pid = surface["pid"]

    if pid is None:
        return host_native(
            surface=surface,
            reason="no-focused-client",
        )

    entry = registry_entry_for_pid(
        registry,
        pid,
    )

    if entry is None:
        if managed_hint(surface["app_id"]):
            return unresolved(
                surface=surface,
                reason="managed-surface-not-registered",
            )

        return host_native(
            surface=surface,
            reason="unregistered-host-process",
        )

    try:
        observed_start = proc_start_ticks(
            proc_root,
            pid,
        )
        observed_executable = proc_executable(
            proc_root,
            pid,
        )
    except ProvenanceError:
        return unresolved(
            surface=surface,
            reason="registered-process-not-verifiable",
        )

    if (
        observed_start
        != entry["process_start_ticks"]
    ):
        return unresolved(
            surface=surface,
            reason="registered-pid-start-time-mismatch",
        )

    if (
        observed_executable
        != entry["executable"]
    ):
        return unresolved(
            surface=surface,
            reason="registered-executable-mismatch",
        )

    try:
        spec_path, spec = spec_for_domain(
            repo,
            entry["domain"],
        )
    except ProvenanceError:
        return unresolved(
            surface=surface,
            reason="registered-domain-spec-unavailable",
        )

    if sha256(spec_path) != entry["spec_sha256"]:
        return unresolved(
            surface=surface,
            reason="registered-domain-spec-drift",
        )

    if spec.get("name") != entry["domain"]:
        return unresolved(
            surface=surface,
            reason="registered-domain-name-mismatch",
        )

    network = spec.get("network_profile")

    if network not in TRUST_IDENTITIES:
        return unresolved(
            surface=surface,
            reason="unsupported-network-profile",
        )

    if entry["surface_kind"] == "looking-glass":
        if (
            spec.get("device_profile") != "vfio"
            or spec.get("looking_glass") is not True
        ):
            return unresolved(
                surface=surface,
                reason="looking-glass-spec-policy-mismatch",
            )

    return {
        "schema": SCHEMA_VERSION,
        "resolved": True,
        "presentation_identity": network,
        "trust": network,
        "trust_source": "host-owned-vm-spec",
        "surface_class": "managed-guest",
        "surface_kind": entry["surface_kind"],
        "reason": "managed-surface-resolved",
        "pid": pid,
        "domain": entry["domain"],
        "network_profile": network,
        "spec": str(spec_path.resolve()),
        "spec_sha256": entry["spec_sha256"],
        "guest_metadata_authoritative": False,
        "wallpaper_allowed": True,
        "rgb_allowed": True,
    }


def emit(payload: dict[str, Any]) -> None:
    print(
        json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )

    parser.add_argument(
        "--proc-root",
        type=Path,
        default=Path("/proc"),
    )

    sub = parser.add_subparsers(
        dest="command",
        required=True,
    )

    sub.add_parser("validate")

    resolve_parser = sub.add_parser("resolve")

    resolve_parser.add_argument(
        "--surface-json",
        required=True,
    )

    resolve_parser.add_argument(
        "--registry",
        type=Path,
        default=None,
    )

    args = parser.parse_args()

    try:
        if args.command == "validate":
            require(
                (args.repo / "vm-specs").is_dir(),
                "vm-specs directory missing",
            )

            checked = 0

            for path in sorted(
                (args.repo / "vm-specs").glob("*.yml")
            ):
                spec = load_yaml(path)
                network = spec.get("network_profile")

                if network is None:
                    continue

                require(
                    network in TRUST_IDENTITIES,
                    (
                        "VM spec uses unsupported "
                        f"network_profile: {path}: {network}"
                    ),
                )

                checked += 1

            require(
                checked > 0,
                "no reviewed VM specifications found",
            )

            print("SURFACE_PROVENANCE_SCHEMA=1")
            print(
                "SURFACE_PROVENANCE_TRUSTS="
                + ",".join(TRUST_IDENTITIES)
            )
            print(
                "GUEST_METADATA_AUTHORITY=NO"
            )
            print(
                "UNREGISTERED_MANAGED_SURFACE="
                "UNRESOLVED"
            )
            print(
                "SURFACE_PROVENANCE_RESOLVER=PASS"
            )
            return 0

        surface = json.loads(
            args.surface_json
        )

        registry = optional_registry(
            args.registry
        )

        payload = resolve(
            repo=args.repo,
            surface=surface,
            registry=registry,
            proc_root=args.proc_root,
        )

        emit(payload)
        return 0

    except (
        json.JSONDecodeError,
        OSError,
        ProvenanceError,
        TypeError,
    ) as exc:
        print(
            f"HyperLab surface provenance: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
