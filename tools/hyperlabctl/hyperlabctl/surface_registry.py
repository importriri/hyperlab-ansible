"""Host-owned runtime registry for managed graphical guest surfaces."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

import yaml

from .errors import Unavailable


REGISTRY_VERSION = 1

TRUST_IDENTITIES = {
    "clean",
    "dev",
    "services",
    "dirty",
    "lab",
}

EXPECTED_EXECUTABLES = {
    "looking-glass": "/usr/local/bin/looking-glass-client",
    "spice-console": "/usr/bin/virt-viewer",
    "ssh": "/usr/bin/foot",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def _runtime_root(
    override: Path | None = None,
) -> Path:
    root = (
        override
        if override is not None
        else Path(
            os.environ.get(
                "XDG_RUNTIME_DIR",
                f"/run/user/{os.getuid()}",
            )
        )
    )

    try:
        info = root.lstat()
    except OSError as exc:
        raise Unavailable(
            f"runtime directory is unavailable: {root}"
        ) from exc

    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
    ):
        raise Unavailable(
            f"runtime directory is not trusted: {root}"
        )

    return root


def _registry_directory(
    runtime_root: Path,
) -> Path:
    directory = runtime_root / "hyperlab"

    try:
        directory.mkdir(
            mode=0o700,
            exist_ok=True,
        )
    except OSError as exc:
        raise Unavailable(
            f"cannot create runtime provenance directory: {directory}"
        ) from exc

    try:
        info = directory.lstat()
    except OSError as exc:
        raise Unavailable(
            f"cannot inspect runtime provenance directory: {directory}"
        ) from exc

    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise Unavailable(
            f"runtime provenance directory is not private: {directory}"
        )

    return directory


def _process_start_ticks(
    proc_root: Path,
    pid: int,
) -> str:
    try:
        value = (
            proc_root
            / str(pid)
            / "stat"
        ).read_text(
            encoding="utf-8"
        ).strip()
    except OSError as exc:
        raise Unavailable(
            f"cannot inspect process start time for pid {pid}"
        ) from exc

    close = value.rfind(")")

    if close < 0:
        raise Unavailable(
            f"invalid process stat for pid {pid}"
        )

    remainder = value[close + 2:].split()

    if (
        len(remainder) <= 19
        or not remainder[19].isdigit()
    ):
        raise Unavailable(
            f"invalid process start time for pid {pid}"
        )

    return remainder[19]


def _validate_spec(
    spec_path: Path,
    domain: str,
) -> str:
    try:
        info = spec_path.lstat()
    except OSError as exc:
        raise Unavailable(
            f"managed VM specification is unavailable: {spec_path}"
        ) from exc

    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
    ):
        raise Unavailable(
            f"managed VM specification is not a real file: {spec_path}"
        )

    try:
        document = yaml.safe_load(
            spec_path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        UnicodeDecodeError,
        yaml.YAMLError,
    ) as exc:
        raise Unavailable(
            f"cannot read managed VM specification: {spec_path}"
        ) from exc

    if not isinstance(document, dict):
        raise Unavailable(
            "managed VM specification is not a mapping"
        )

    if document.get("name") != domain:
        raise Unavailable(
            "managed VM specification/domain mismatch"
        )

    network = document.get("network_profile")

    if network not in TRUST_IDENTITIES:
        raise Unavailable(
            f"unsupported managed network profile: {network}"
        )

    return _sha256(spec_path)


def _validate_existing_registry(
    path: Path,
) -> dict:
    if not path.exists():
        return {
            "version": REGISTRY_VERSION,
            "entries": [],
        }

    try:
        info = path.lstat()
    except OSError as exc:
        raise Unavailable(
            f"cannot inspect surface provenance registry: {path}"
        ) from exc

    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
    ):
        raise Unavailable(
            f"surface provenance registry is not trusted: {path}"
        )

    try:
        document = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as exc:
        raise Unavailable(
            f"invalid surface provenance registry: {path}"
        ) from exc

    if (
        not isinstance(document, dict)
        or set(document) != {"version", "entries"}
        or document.get("version") != REGISTRY_VERSION
        or not isinstance(document.get("entries"), list)
    ):
        raise Unavailable(
            "surface provenance registry structure changed"
        )

    return document


def _entry_alive(
    entry: dict,
    proc_root: Path,
) -> bool:
    try:
        pid = entry["pid"]
        expected = entry["process_start_ticks"]

        if (
            not isinstance(pid, int)
            or isinstance(pid, bool)
            or not isinstance(expected, str)
        ):
            return False

        return (
            _process_start_ticks(
                proc_root,
                pid,
            )
            == expected
        )
    except (
        KeyError,
        TypeError,
        Unavailable,
    ):
        return False


def _write_atomic(
    path: Path,
    payload: dict,
) -> None:
    directory = path.parent

    fd, temporary_name = tempfile.mkstemp(
        prefix=".surface-provenance.",
        dir=directory,
    )

    temporary = Path(temporary_name)

    try:
        os.fchmod(fd, 0o600)

        with os.fdopen(
            fd,
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                payload,
                handle,
                separators=(",", ":"),
                sort_keys=True,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

        os.replace(
            temporary,
            path,
        )
    except Exception:
        try:
            temporary.unlink()
        except OSError:
            pass
        raise


def register_managed_surface(
    *,
    spec_path: Path,
    domain: str,
    surface_kind: str,
    executable: str,
    runtime_root: Path | None = None,
    proc_root: Path = Path("/proc"),
    pid: int | None = None,
) -> Path:
    if surface_kind not in EXPECTED_EXECUTABLES:
        raise Unavailable(
            f"unsupported managed surface kind: {surface_kind}"
        )

    expected_executable = EXPECTED_EXECUTABLES[
        surface_kind
    ]

    if executable != expected_executable:
        raise Unavailable(
            (
                "managed surface executable differs from "
                f"reviewed path: {executable}"
            )
        )

    spec_digest = _validate_spec(
        spec_path,
        domain,
    )

    process_id = (
        os.getpid()
        if pid is None
        else pid
    )

    if (
        not isinstance(process_id, int)
        or isinstance(process_id, bool)
        or process_id <= 0
    ):
        raise Unavailable(
            "invalid managed-surface process id"
        )

    start_ticks = _process_start_ticks(
        proc_root,
        process_id,
    )

    root = _runtime_root(
        runtime_root,
    )

    directory = _registry_directory(
        root,
    )

    registry_path = (
        directory
        / "surface-provenance.json"
    )

    registry = _validate_existing_registry(
        registry_path,
    )

    # Keep only registrations whose original process identity is still alive.
    # The process executable is checked later by the resolver, after exec.
    entries = [
        entry
        for entry in registry["entries"]
        if (
            isinstance(entry, dict)
            and entry.get("pid") != process_id
            and _entry_alive(
                entry,
                proc_root,
            )
        )
    ]

    entries.append(
        {
            "pid": process_id,
            "process_start_ticks": start_ticks,
            "executable": expected_executable,
            "surface_kind": surface_kind,
            "domain": domain,
            "spec_sha256": spec_digest,
            "registered_by": "hyperlabctl",
        }
    )

    payload = {
        "version": REGISTRY_VERSION,
        "entries": entries,
    }

    try:
        _write_atomic(
            registry_path,
            payload,
        )
    except OSError as exc:
        raise Unavailable(
            (
                "cannot publish managed surface provenance: "
                f"{registry_path}"
            )
        ) from exc

    return registry_path
