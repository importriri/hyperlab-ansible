#!/usr/bin/env python3
"""Reconcile one C10 managed-Machine GPU handoff policy.

The caller must already be privileged. This helper never reads the user-owned
Machine registry. It consumes the validated guest plan produced by the existing
lifecycle and writes only the root-owned qemu-hook policy boundary.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path
from typing import Any


NAME_RE = re.compile(
    r"^[a-z0-9][a-z0-9-]{1,30}$"
)

PROFILE_RE = re.compile(
    r"^(clean|dev|dirty|lab)$"
)

MAX_POLICY_BYTES = 4096


class PolicyError(ValueError):
    """The requested root-owned GPU policy is unsafe or inconsistent."""


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise PolicyError(
            message
        )


def parse_trust_levels(
    raw: str,
) -> dict[str, int]:
    try:
        value = json.loads(
            raw
        )
    except json.JSONDecodeError as exc:
        raise PolicyError(
            "GPU trust levels are not valid JSON"
        ) from exc

    require(
        isinstance(value, dict),
        "GPU trust levels must be a mapping",
    )

    result: dict[str, int] = {}

    for name, level in value.items():
        require(
            isinstance(name, str)
            and PROFILE_RE.fullmatch(name)
            is not None,
            f"invalid GPU handoff profile {name!r}",
        )

        require(
            isinstance(level, int)
            and not isinstance(level, bool)
            and level >= 0,
            f"GPU trust level for {name} "
            "must be a non-negative integer",
        )

        result[name] = level

    require(
        bool(result),
        "GPU trust levels are empty",
    )

    return result


def validate_directory(
    directory: Path,
) -> None:
    try:
        info = directory.lstat()
    except FileNotFoundError as exc:
        raise PolicyError(
            f"managed GPU policy directory "
            f"does not exist: {directory}"
        ) from exc
    except OSError as exc:
        raise PolicyError(
            f"cannot inspect managed GPU "
            f"policy directory: {directory}"
        ) from exc

    require(
        stat.S_ISDIR(
            info.st_mode
        )
        and not stat.S_ISLNK(
            info.st_mode
        ),
        "managed GPU policy path "
        "must be a real directory",
    )

    require(
        info.st_uid == os.geteuid(),
        "managed GPU policy directory "
        "must be owned by the effective user",
    )

    require(
        stat.S_IMODE(
            info.st_mode
        )
        == 0o755,
        "managed GPU policy directory "
        "must have mode 0755",
    )


def inspect_regular(
    path: Path,
    label: str,
    *,
    mode: int | None = None,
) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise PolicyError(
            f"{label} does not exist: {path}"
        ) from exc
    except OSError as exc:
        raise PolicyError(
            f"cannot inspect {label}: {path}"
        ) from exc

    require(
        stat.S_ISREG(
            info.st_mode
        )
        and not stat.S_ISLNK(
            info.st_mode
        ),
        f"{label} must be a real regular file",
    )

    require(
        info.st_uid == os.geteuid(),
        f"{label} must be owned "
        "by the effective user",
    )

    if mode is not None:
        require(
            stat.S_IMODE(
                info.st_mode
            )
            == mode,
            f"{label} must have mode "
            f"{mode:04o}",
        )

    require(
        info.st_size <= MAX_POLICY_BYTES,
        f"{label} exceeds the size limit",
    )

    return info


def static_domains(
    path: Path,
    trust_levels: dict[str, int],
) -> dict[str, str]:
    inspect_regular(
        path,
        "static GPU domain policy",
    )

    try:
        text = path.read_text(
            encoding="utf-8"
        )
    except (
        OSError,
        UnicodeDecodeError,
    ) as exc:
        raise PolicyError(
            "cannot read static GPU domain policy"
        ) from exc

    result: dict[str, str] = {}

    for line_number, raw in enumerate(
        text.splitlines(),
        start=1,
    ):
        line = raw.strip()

        if not line or line.startswith("#"):
            continue

        parts = line.split()

        require(
            len(parts) == 2,
            "invalid static GPU domain policy "
            f"at line {line_number}",
        )

        name, profile = parts

        require(
            NAME_RE.fullmatch(name)
            is not None,
            f"invalid static domain {name!r}",
        )

        require(
            profile in trust_levels,
            f"static domain {name} uses "
            f"unknown profile {profile}",
        )

        require(
            name not in result,
            f"duplicate static GPU domain {name}",
        )

        result[name] = profile

    require(
        bool(result),
        "static GPU domain policy is empty",
    )

    return result


def validate_payload(
    payload: Any,
    trust_levels: dict[str, int] | None = None,
) -> tuple[str, str]:
    require(
        isinstance(payload, dict),
        "guest plan JSON root must be a mapping",
    )

    name = payload.get(
        "name"
    )

    require(
        isinstance(name, str)
        and NAME_RE.fullmatch(name)
        is not None,
        "guest plan has an invalid name",
    )

    require(
        payload.get(
            "device_profile"
        )
        == "vfio",
        "managed GPU policy requires "
        "device_profile=vfio",
    )

    tags = payload.get(
        "tags"
    )

    require(
        isinstance(tags, list)
        and all(
            isinstance(tag, str)
            for tag in tags
        )
        and "managed-machine" in tags,
        "GPU policy materialization is reserved "
        "for C10 managed-machine specs",
    )

    profile = payload.get(
        "gpu_handoff_profile"
    )

    require(
        isinstance(profile, str)
        and PROFILE_RE.fullmatch(profile)
        is not None,
        "guest plan requires an explicit "
        "gpu_handoff_profile",
    )

    if trust_levels is not None:
        # Removal needs only the name; granting or verifying a policy must
        # not trust the plan's own provenance tag. A handoff class may lower,
        # never raise, the class a ranked network identity implies.
        network = payload.get(
            "network_profile"
        )

        require(
            isinstance(network, str)
            and NAME_RE.fullmatch(network)
            is not None,
            "guest plan requires a network_profile",
        )

        require(
            profile in trust_levels,
            f"gpu_handoff_profile {profile} is not a reviewed trust level",
        )

        require(
            network not in trust_levels
            or trust_levels[profile]
            <= trust_levels[network],
            f"gpu_handoff_profile {profile} ranks above "
            f"network {network}",
        )

    return name, profile


def target_path(
    directory: Path,
    name: str,
) -> Path:
    return directory / (
        name + ".conf"
    )


def existing_target(
    path: Path,
) -> os.stat_result | None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise PolicyError(
            f"cannot inspect managed GPU policy: {path}"
        ) from exc

    require(
        stat.S_ISREG(
            info.st_mode
        )
        and not stat.S_ISLNK(
            info.st_mode
        ),
        "managed GPU policy target "
        "must be a real regular file",
    )

    require(
        info.st_uid == os.geteuid(),
        "managed GPU policy target "
        "must be owned by the effective user",
    )

    require(
        stat.S_IMODE(
            info.st_mode
        )
        == 0o644,
        "managed GPU policy target "
        "must have mode 0644",
    )

    require(
        info.st_size <= MAX_POLICY_BYTES,
        "managed GPU policy target "
        "exceeds the size limit",
    )

    return info


def read_target(
    path: Path,
) -> str:
    existing_target(
        path
    )

    try:
        return path.read_text(
            encoding="utf-8"
        )
    except (
        OSError,
        UnicodeDecodeError,
    ) as exc:
        raise PolicyError(
            "cannot read managed GPU policy"
        ) from exc


def fsync_directory(
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
            descriptor
        )
    finally:
        os.close(
            descriptor
        )


def create_policy(
    directory: Path,
    static_file: Path,
    trust_levels: dict[str, int],
    name: str,
    profile: str,
    *,
    dry_run: bool,
) -> bool:
    """Create policy only when this transaction owns a new target."""

    require(
        profile in trust_levels,
        f"GPU handoff profile {profile} "
        "is not reviewed by the host",
    )

    fixed = static_domains(
        static_file,
        trust_levels,
    )

    require(
        name not in fixed,
        f"{name} already belongs to the "
        "checked-in fixture GPU policy",
    )

    destination = target_path(
        directory,
        name,
    )

    require(
        existing_target(
            destination
        )
        is None,
        "managed GPU policy already exists; "
        "a new Machine transaction may not claim it",
    )

    if dry_run:
        return True

    wanted = (
        f"{name} {profile}\n"
    )

    descriptor, temporary_name = (
        tempfile.mkstemp(
            prefix=f".{name}.",
            suffix=".claim",
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
            0o644,
        )

        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(
                wanted
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
            )
        except FileExistsError as exc:
            raise PolicyError(
                "managed GPU policy appeared while "
                "the transaction was claiming it"
            ) from exc

        published = True

        fsync_directory(
            directory
        )

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

    require(
        published,
        "managed GPU policy claim was not published",
    )

    require(
        read_target(
            destination
        )
        == wanted,
        "managed GPU policy changed "
        "during create-only publication",
    )

    return True


def ensure_policy(
    directory: Path,
    static_file: Path,
    trust_levels: dict[str, int],
    name: str,
    profile: str,
    *,
    dry_run: bool,
) -> bool:
    require(
        profile in trust_levels,
        f"GPU handoff profile {profile} "
        "is not reviewed by the host",
    )

    fixed = static_domains(
        static_file,
        trust_levels,
    )

    require(
        name not in fixed,
        f"{name} already belongs to the "
        "checked-in fixture GPU policy",
    )

    destination = target_path(
        directory,
        name,
    )

    wanted = (
        f"{name} {profile}\n"
    )

    info = existing_target(
        destination
    )

    if info is not None:
        current = read_target(
            destination
        )

        if current == wanted:
            return False

    if dry_run:
        return True

    descriptor, temporary_name = (
        tempfile.mkstemp(
            prefix=f".{name}.",
            suffix=".tmp",
            dir=directory,
        )
    )

    temporary = Path(
        temporary_name
    )

    try:
        os.fchmod(
            descriptor,
            0o644,
        )

        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as handle:
            handle.write(
                wanted
            )
            handle.flush()
            os.fsync(
                handle.fileno()
            )

        descriptor = -1

        os.replace(
            temporary,
            destination,
        )

        fsync_directory(
            directory
        )

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

    require(
        read_target(
            destination
        )
        == wanted,
        "managed GPU policy changed "
        "during publication",
    )

    return True


def verify_policy(
    directory: Path,
    static_file: Path,
    trust_levels: dict[str, int],
    name: str,
    profile: str,
) -> bool:
    require(
        profile in trust_levels,
        f"GPU handoff profile {profile} "
        "is not reviewed by the host",
    )

    fixed = static_domains(
        static_file,
        trust_levels,
    )

    require(
        name not in fixed,
        f"{name} collides with the "
        "checked-in fixture GPU policy",
    )

    destination = target_path(
        directory,
        name,
    )

    wanted = (
        f"{name} {profile}\n"
    )

    require(
        read_target(
            destination
        )
        == wanted,
        "root-owned managed GPU policy "
        "does not match the guest plan",
    )

    return False


def remove_policy(
    directory: Path,
    name: str,
    *,
    dry_run: bool,
) -> bool:
    destination = target_path(
        directory,
        name,
    )

    info = existing_target(
        destination
    )

    if info is None:
        return False

    if dry_run:
        return True

    try:
        destination.unlink()
    except OSError as exc:
        raise PolicyError(
            "cannot remove managed GPU policy"
        ) from exc

    fsync_directory(
        directory
    )

    return True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "action",
        choices=(
            "create",
            "ensure",
            "verify",
            "remove",
        ),
    )

    parser.add_argument(
        "--directory",
        required=True,
    )

    parser.add_argument(
        "--static-domains",
        required=True,
    )

    parser.add_argument(
        "--trust-levels-json",
        required=True,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
    )

    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
        directory = Path(
            args.directory
        )

        static_file = Path(
            args.static_domains
        )

        validate_directory(
            directory
        )

        trust_levels = parse_trust_levels(
            args.trust_levels_json
        )

        payload = json.load(
            sys.stdin
        )

        name, profile = validate_payload(
            payload,
            (
                None
                if args.action == "remove"
                else trust_levels
            ),
        )

        if args.action == "create":
            changed = create_policy(
                directory,
                static_file,
                trust_levels,
                name,
                profile,
                dry_run=args.dry_run,
            )
            status = "created"

        elif args.action == "ensure":
            changed = ensure_policy(
                directory,
                static_file,
                trust_levels,
                name,
                profile,
                dry_run=args.dry_run,
            )
            status = "present"

        elif args.action == "verify":
            changed = verify_policy(
                directory,
                static_file,
                trust_levels,
                name,
                profile,
            )
            status = "verified"

        else:
            changed = remove_policy(
                directory,
                name,
                dry_run=args.dry_run,
            )
            status = "absent"

    except (
        OSError,
        json.JSONDecodeError,
        PolicyError,
    ) as exc:
        print(
            f"GPU handoff policy refused: {exc}",
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            {
                "changed": changed,
                "name": name,
                "profile": profile,
                "status": status,
            },
            sort_keys=True,
        )
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
