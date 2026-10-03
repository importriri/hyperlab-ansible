"""Persistent host-side registry for user-created HyperLab Machine intent.

The registry contains declarative product intent only. It never becomes
authority for libvirt state, trust, provenance, GPU ownership or transport
availability.

Persistent records live below:

    $XDG_STATE_HOME/hyperlab/machines

or, when XDG_STATE_HOME is unset:

    ~/.local/state/hyperlab/machines

The registry is intentionally outside the Git checkout.
"""

from __future__ import annotations

import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

import yaml

from .errors import ContractError, Unavailable


MACHINE_SCHEMA_VERSION = 1
MAX_RECORD_BYTES = 64 * 1024

MACHINE_ID_RE = re.compile(
    r"^[a-z0-9][a-z0-9-]{1,30}$"
)
OWNER_RE = re.compile(
    r"^[a-z_][a-z0-9_-]{0,30}$"
)
SHA256_RE = re.compile(
    r"^[a-f0-9]{64}$"
)
NETWORK_RE = re.compile(
    r"^[a-z][a-z0-9-]*$"
)
CREATED_AT_RE = re.compile(
    r"^[0-9]{4}-[0-9]{2}-[0-9]{2}"
    r"T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"
)

REQUIRED_KEYS = {
    "schema_version",
    "id",
    "display_name",
    "template",
    "image",
    "lifecycle",
    "device_capability",
    "gpu_handoff_profile",
    "network_profile",
    "resources",
    "presentation",
    "owner",
    "created_at",
}

OPTIONAL_KEYS = {
    "purpose",
}

RUNTIME_AUTHORITY_KEYS = {
    "state",
    "trust",
    "provenance",
    "gpu_owner",
    "transport_available",
}


def _require_mapping(
    value: Any,
    label: str,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ContractError(
            f"{label} must be a mapping"
        )
    return value


def _require_exact_keys(
    value: dict[str, Any],
    required: set[str],
    optional: set[str],
    label: str,
) -> None:
    keys = set(value)
    missing = required - keys
    unknown = keys - required - optional

    if missing:
        raise ContractError(
            f"{label} is missing fields: "
            + ", ".join(sorted(missing))
        )

    if unknown:
        raise ContractError(
            f"{label} contains unsupported fields: "
            + ", ".join(sorted(unknown))
        )


def _require_string(
    value: Any,
    label: str,
    *,
    pattern: re.Pattern[str] | None = None,
) -> str:
    if not isinstance(value, str) or not value:
        raise ContractError(
            f"{label} must be a non-empty string"
        )

    if any(
        ord(character) < 32
        or ord(character) == 127
        for character in value
    ):
        raise ContractError(
            f"{label} contains control characters"
        )

    if pattern is not None and pattern.fullmatch(value) is None:
        raise ContractError(
            f"{label} has an invalid format"
        )

    return value


def _require_integer(
    value: Any,
    label: str,
    minimum: int,
    maximum: int,
) -> int:
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or not minimum <= value <= maximum
    ):
        raise ContractError(
            f"{label} must be an integer between "
            f"{minimum} and {maximum}"
        )

    return value


def validate_machine_record(
    record: Any,
) -> dict[str, Any]:
    record = _require_mapping(
        record,
        "Machine record",
    )

    forbidden = (
        set(record)
        & RUNTIME_AUTHORITY_KEYS
    )

    if forbidden:
        raise ContractError(
            "Machine record may not claim runtime authority: "
            + ", ".join(sorted(forbidden))
        )

    _require_exact_keys(
        record,
        REQUIRED_KEYS,
        OPTIONAL_KEYS,
        "Machine record",
    )

    if record["schema_version"] != MACHINE_SCHEMA_VERSION:
        raise ContractError(
            "unsupported Machine record schema_version"
        )

    machine_id = _require_string(
        record["id"],
        "Machine id",
        pattern=MACHINE_ID_RE,
    )

    _require_string(
        record["display_name"],
        "Machine display_name",
    )

    template = _require_mapping(
        record["template"],
        "Machine template",
    )

    _require_exact_keys(
        template,
        {"id", "version"},
        set(),
        "Machine template",
    )

    _require_string(
        template["id"],
        "Machine template id",
        pattern=NETWORK_RE,
    )

    _require_string(
        template["version"],
        "Machine template version",
    )

    image = _require_mapping(
        record["image"],
        "Machine image",
    )

    _require_exact_keys(
        image,
        {"id", "sha256"},
        set(),
        "Machine image",
    )

    _require_string(
        image["id"],
        "Machine image id",
        pattern=NETWORK_RE,
    )

    _require_string(
        image["sha256"],
        "Machine image sha256",
        pattern=SHA256_RE,
    )

    if record["lifecycle"] not in {
        "permanent",
        "disposable",
    }:
        raise ContractError(
            "Machine lifecycle is unsupported"
        )

    if record["device_capability"] not in {
        "standard",
        "vfio",
    }:
        raise ContractError(
            "Machine device_capability is unsupported"
        )

    gpu_handoff_profile = record[
        "gpu_handoff_profile"
    ]

    if record["device_capability"] == "vfio":
        if gpu_handoff_profile not in {
            "clean",
            "dev",
            "dirty",
            "lab",
        }:
            raise ContractError(
                "VFIO Machine requires an explicit "
                "gpu_handoff_profile"
            )
    elif gpu_handoff_profile is not None:
        raise ContractError(
            "standard Machine cannot carry "
            "gpu_handoff_profile"
        )

    _require_string(
        record["network_profile"],
        "Machine network_profile",
        pattern=NETWORK_RE,
    )

    resources = _require_mapping(
        record["resources"],
        "Machine resources",
    )

    _require_exact_keys(
        resources,
        {
            "memory_mb",
            "vcpus",
            "disk_gib",
        },
        set(),
        "Machine resources",
    )

    memory = resources["memory_mb"]

    if memory != "auto":
        _require_integer(
            memory,
            "Machine resources.memory_mb",
            512,
            1048576,
        )

    _require_integer(
        resources["vcpus"],
        "Machine resources.vcpus",
        1,
        256,
    )

    _require_integer(
        resources["disk_gib"],
        "Machine resources.disk_gib",
        1,
        4096,
    )

    presentation = _require_mapping(
        record["presentation"],
        "Machine presentation",
    )

    _require_exact_keys(
        presentation,
        {
            "looking_glass_mode",
            "recovery_console",
            "workspace_profile",
        },
        set(),
        "Machine presentation",
    )

    if presentation["looking_glass_mode"] not in {
        "disabled",
        "windows",
        "linux-experimental",
    }:
        raise ContractError(
            "Machine presentation.looking_glass_mode "
            "is unsupported"
        )

    if not isinstance(
        presentation["recovery_console"],
        bool,
    ):
        raise ContractError(
            "Machine presentation.recovery_console "
            "must be boolean"
        )

    _require_string(
        presentation["workspace_profile"],
        "Machine presentation.workspace_profile",
        pattern=NETWORK_RE,
    )

    _require_string(
        record["owner"],
        "Machine owner",
        pattern=OWNER_RE,
    )

    _require_string(
        record["created_at"],
        "Machine created_at",
        pattern=CREATED_AT_RE,
    )

    if "purpose" in record:
        _require_string(
            record["purpose"],
            "Machine purpose",
        )

    if record["id"] != machine_id:
        raise ContractError(
            "Machine id changed during validation"
        )

    return record


def _state_home(
    override: Path | None = None,
) -> Path:
    if override is not None:
        path = Path(override)
    else:
        configured = os.environ.get(
            "XDG_STATE_HOME"
        )

        path = (
            Path(configured)
            if configured
            else Path.home()
            / ".local"
            / "state"
        )

    path = path.expanduser()

    if not path.is_absolute():
        raise Unavailable(
            "Machine state home must be absolute"
        )

    return path


def _inspect_directory(
    path: Path,
    label: str,
    *,
    exact_mode: int | None = None,
) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise Unavailable(
            f"cannot inspect {label}: {path}"
        ) from exc

    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
    ):
        raise Unavailable(
            f"{label} is not a trusted "
            f"user-owned directory: {path}"
        )

    if (
        exact_mode is not None
        and stat.S_IMODE(info.st_mode)
        != exact_mode
    ):
        raise Unavailable(
            f"{label} has unsafe mode: {path}"
        )

    return True


def _create_directory(
    path: Path,
    label: str,
    *,
    mode: int,
    exact_mode: int | None = None,
) -> None:
    try:
        path.mkdir(
            mode=mode,
            parents=True,
            exist_ok=True,
        )
    except OSError as exc:
        raise Unavailable(
            f"cannot create {label}: {path}"
        ) from exc

    if not _inspect_directory(
        path,
        label,
        exact_mode=exact_mode,
    ):
        raise Unavailable(
            f"{label} disappeared: {path}"
        )


def _registry_directory(
    state_home: Path | None = None,
    *,
    create: bool,
) -> Path | None:
    state = _state_home(
        state_home,
    )

    if not _inspect_directory(
        state,
        "Machine state home",
    ):
        if not create:
            return None

        _create_directory(
            state,
            "Machine state home",
            mode=0o700,
        )

    hyperlab = state / "hyperlab"

    if not _inspect_directory(
        hyperlab,
        "HyperLab state directory",
    ):
        if not create:
            return None

        _create_directory(
            hyperlab,
            "HyperLab state directory",
            mode=0o700,
        )

    machines = hyperlab / "machines"

    if not _inspect_directory(
        machines,
        "Machine registry directory",
        exact_mode=0o700,
    ):
        if not create:
            return None

        _create_directory(
            machines,
            "Machine registry directory",
            mode=0o700,
            exact_mode=0o700,
        )

    return machines


def _machine_path(
    directory: Path,
    machine_id: str,
) -> Path:
    machine_id = _require_string(
        machine_id,
        "Machine id",
        pattern=MACHINE_ID_RE,
    )

    return directory / (
        machine_id + ".yml"
    )


def _inspect_record_file(
    path: Path,
) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise Unavailable(
            f"Machine record does not exist: {path}"
        ) from exc
    except OSError as exc:
        raise Unavailable(
            f"cannot inspect Machine record: {path}"
        ) from exc

    if (
        stat.S_ISLNK(info.st_mode)
        or not stat.S_ISREG(info.st_mode)
        or info.st_uid != os.getuid()
        or stat.S_IMODE(info.st_mode) != 0o600
        or info.st_size > MAX_RECORD_BYTES
    ):
        raise Unavailable(
            f"Machine record is not trusted: {path}"
        )

    return info


def _fsync_directory(
    directory: Path,
) -> None:
    flags = (
        os.O_RDONLY
        | getattr(
            os,
            "O_DIRECTORY",
            0,
        )
        | getattr(
            os,
            "O_CLOEXEC",
            0,
        )
    )

    descriptor = os.open(
        directory,
        flags,
    )

    try:
        os.fsync(
            descriptor,
        )
    finally:
        os.close(
            descriptor,
        )


def create_machine(
    record: dict[str, Any],
    *,
    state_home: Path | None = None,
) -> Path:
    record = validate_machine_record(
        record,
    )

    directory = _registry_directory(
        state_home,
        create=True,
    )

    if directory is None:
        raise Unavailable(
            "Machine registry directory "
            "could not be created"
        )

    destination = _machine_path(
        directory,
        record["id"],
    )

    try:
        existing = destination.lstat()
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise Unavailable(
            "cannot inspect Machine destination"
        ) from exc

    if existing is not None:
        if (
            stat.S_ISLNK(existing.st_mode)
            or not stat.S_ISREG(
                existing.st_mode
            )
            or existing.st_uid
            != os.getuid()
        ):
            raise Unavailable(
                "existing Machine destination "
                "is not trusted"
            )

        raise ContractError(
            f"Machine {record['id']} "
            "already exists"
        )

    payload = yaml.safe_dump(
        record,
        sort_keys=False,
        explicit_start=True,
    )

    encoded = payload.encode(
        "utf-8"
    )

    if len(encoded) > MAX_RECORD_BYTES:
        raise ContractError(
            "Machine record exceeds size limit"
        )

    descriptor, temporary_name = (
        tempfile.mkstemp(
            prefix=(
                "."
                + record["id"]
                + "."
            ),
            suffix=".tmp",
            dir=directory,
        )
    )

    temporary = Path(
        temporary_name
    )

    published = False

    try:
        os.fchmod(
            descriptor,
            0o600,
        )

        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(
                payload
            )
            handle.flush()
            os.fsync(
                handle.fileno()
            )

        descriptor = -1

        try:
            os.link(
                temporary,
                destination,
                follow_symlinks=False,
            )
        except FileExistsError as exc:
            raise ContractError(
                f"Machine {record['id']} "
                "already exists"
            ) from exc

        published = True

    except (
        ContractError,
        OSError,
    ) as exc:
        if isinstance(
            exc,
            ContractError,
        ):
            raise

        raise Unavailable(
            "cannot publish Machine record"
        ) from exc

    finally:
        if descriptor >= 0:
            try:
                os.close(
                    descriptor
                )
            except OSError:
                pass

        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            if not published:
                raise

    if not published:
        raise Unavailable(
            "Machine record publication failed"
        )

    _inspect_record_file(
        destination,
    )

    try:
        _fsync_directory(
            directory,
        )
    except OSError as exc:
        raise Unavailable(
            "Machine record directory "
            "durability is uncertain"
        ) from exc

    return destination


def read_machine(
    machine_id: str,
    *,
    state_home: Path | None = None,
) -> dict[str, Any]:
    directory = _registry_directory(
        state_home,
        create=False,
    )

    if directory is None:
        raise Unavailable(
            "Machine registry does not exist"
        )

    path = _machine_path(
        directory,
        machine_id,
    )

    _inspect_record_file(
        path,
    )

    try:
        document = yaml.safe_load(
            path.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        UnicodeDecodeError,
        yaml.YAMLError,
    ) as exc:
        raise Unavailable(
            f"cannot read Machine record: {path}"
        ) from exc

    record = validate_machine_record(
        document,
    )

    if record["id"] != machine_id:
        raise Unavailable(
            "Machine record filename/id mismatch"
        )

    return record


def list_machines(
    *,
    state_home: Path | None = None,
) -> list[dict[str, Any]]:
    directory = _registry_directory(
        state_home,
        create=False,
    )

    if directory is None:
        return []

    result = []

    for path in sorted(
        directory.glob("*.yml")
    ):
        machine_id = path.stem

        _require_string(
            machine_id,
            "Machine id",
            pattern=MACHINE_ID_RE,
        )

        result.append(
            read_machine(
                machine_id,
                state_home=state_home,
            )
        )

    return result
