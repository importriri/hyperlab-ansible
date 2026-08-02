#!/usr/bin/env python3
"""Generate exact scalar gate payloads without hand-editing campaign JSON."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

from release_acceptance import (
    AcceptanceError,
    BOOL_FIELDS,
    HEX64_RE,
    load_yaml,
    require,
    validate_manifest,
)
from bootstrap_storage_guard import (
    normalized_observation,
    read_contract,
    validate_contract,
)

ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
RECAP_RE = re.compile(
    r"(?m)^(?P<host>[^\s:]+)\s*:\s+"
    r"ok=(?P<ok>\d+)\s+"
    r"changed=(?P<changed>\d+)\s+"
    r"unreachable=(?P<unreachable>\d+)\s+"
    r"failed=(?P<failed>\d+)"
    r"(?:\s+skipped=(?P<skipped>\d+))?"
    r"(?:\s+rescued=(?P<rescued>\d+))?"
    r"(?:\s+ignored=(?P<ignored>\d+))?\s*$"
)


def regular_file_info(path: Path) -> os.stat_result:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise AcceptanceError(f"evidence file is missing: {path}") from exc
    require(
        stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
        f"evidence file must be one regular non-symlink file: {path}",
    )
    return info


def hash_regular_file(path: Path) -> str:
    regular_file_info(path)
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise AcceptanceError(f"cannot hash evidence file {path}: {exc}") from exc
    return digest.hexdigest()


def read_regular_text(path: Path) -> str:
    regular_file_info(path)
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        raise AcceptanceError(f"cannot read evidence file {path}: {exc}") from exc


def parse_assignment(raw: str, option: str) -> tuple[str, str]:
    require("=" in raw, f"{option} requires FIELD=VALUE")
    field, value = raw.split("=", 1)
    require(
        re.fullmatch(r"[a-z][a-z0-9_]+", field) is not None,
        f"{option} field is invalid: {field}",
    )
    require(value != "", f"{option} value is empty for {field}")
    return field, value


def gate_contract(manifest: dict[str, Any], gate_id: str) -> dict[str, Any]:
    validate_manifest(manifest)
    gate = next((item for item in manifest["gates"] if item["id"] == gate_id), None)
    require(gate is not None, f"unknown acceptance gate: {gate_id}")
    assert gate is not None
    return gate


def build_payload(
    manifest: dict[str, Any],
    gate_id: str,
    values: list[str],
    true_fields: list[str],
    false_fields: list[str],
    hash_files: list[str],
) -> dict[str, Any]:
    gate = gate_contract(manifest, gate_id)
    payload: dict[str, Any] = {}

    def set_once(field: str, value: Any) -> None:
        require(field not in payload, f"gate field supplied more than once: {field}")
        payload[field] = value

    for raw in values:
        field, value = parse_assignment(raw, "--value")
        require(field not in BOOL_FIELDS, f"boolean field {field} needs --true or --false")
        if field.endswith("sha256"):
            require(
                HEX64_RE.fullmatch(value) is not None,
                f"field {field} must be one SHA-256 or use --hash-file",
            )
        set_once(field, value)

    for field in true_fields:
        require(field in BOOL_FIELDS, f"field {field} is not a reviewed boolean")
        set_once(field, True)
    for field in false_fields:
        require(field in BOOL_FIELDS, f"field {field} is not a reviewed boolean")
        set_once(field, False)

    for raw in hash_files:
        field, value = parse_assignment(raw, "--hash-file")
        require(field.endswith("sha256"), f"hash target is not a SHA-256 field: {field}")
        set_once(field, hash_regular_file(Path(value)))

    required = set(gate["required_evidence"])
    require(
        set(payload) == required,
        f"gate {gate_id} fields differ: missing={sorted(required - set(payload))} "
        f"extra={sorted(set(payload) - required)}",
    )
    return payload


def command_json(argv: list[str], label: str) -> dict[str, Any]:
    result = subprocess.run(
        argv,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "LC_ALL": "C"},
    )
    require(result.returncode == 0, f"{label} failed: {result.stderr.strip()}")
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"{label} did not return JSON: {exc}") from exc
    require(isinstance(data, dict), f"{label} JSON root must be a mapping")
    return data


def findmnt_observation(target: Path) -> dict[str, Any]:
    return command_json(
        [
            "/usr/bin/findmnt",
            "-J",
            "-T",
            str(target),
            "-o",
            "TARGET,SOURCE,FSTYPE,FSROOT,OPTIONS",
        ],
        f"findmnt for {target}",
    )


def lsattr_text(target: Path) -> str:
    result = subprocess.run(
        ["/usr/bin/lsattr", "-d", "--", str(target)],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "LC_ALL": "C"},
    )
    require(result.returncode == 0, f"lsattr for {target} failed: {result.stderr.strip()}")
    return result.stdout


def storage_payload(
    contract_path: Path,
    mountpoint: Path,
    hyperlab_root: Path,
    mount_observation: dict[str, Any],
    hyperlab_observation: dict[str, Any],
    attributes: str,
) -> dict[str, Any]:
    require(str(mountpoint) == "/var/lib/libvirt/images", "storage probe mountpoint drift")
    require(
        str(hyperlab_root).startswith(str(mountpoint) + "/"),
        "Hyperlab root is outside the canonical VM store",
    )
    try:
        mounted = normalized_observation(mount_observation["filesystems"][0])
        hyperlab = normalized_observation(hyperlab_observation["filesystems"][0])
    except (KeyError, IndexError, TypeError) as exc:
        raise AcceptanceError("findmnt evidence must describe one filesystem") from exc

    contract = read_contract(contract_path)
    verified = validate_contract(contract, mounted, str(hyperlab_root))
    attribute_fields = attributes.split()
    require(attribute_fields and "C" in attribute_fields[0], "VM store lacks inherited NOCOW")
    require(
        hyperlab["source"] == verified["mapper"],
        "Hyperlab root is not backed by the verified mapper",
    )
    require(
        hyperlab["fstype"] == verified["fstype"],
        "Hyperlab root filesystem differs from the verified store",
    )
    require(
        hyperlab["fsroot"] == verified["fsroot"]
        or hyperlab["fsroot"].startswith(verified["fsroot"].rstrip("/") + "/"),
        "Hyperlab root filesystem root differs from the verified store",
    )
    return {
        "topology": verified["topology"],
        "mapper": verified["mapper"],
        "fsroot": verified["fsroot"],
        "fstype": verified["fstype"],
        "nocow": True,
        "contract_sha256": hash_regular_file(contract_path),
        "hyperlab_device_match": True,
    }


def parse_ansible_recap(path: Path) -> list[dict[str, int | str]]:
    text = ANSI_RE.sub("", read_regular_text(path))
    require("PLAY RECAP" in text, f"Ansible log has no PLAY RECAP: {path}")
    recap_text = text.rsplit("PLAY RECAP", 1)[1]
    recaps: list[dict[str, int | str]] = []
    for match in RECAP_RE.finditer(recap_text):
        recaps.append(
            {
                "host": match.group("host"),
                "ok": int(match.group("ok")),
                "changed": int(match.group("changed")),
                "unreachable": int(match.group("unreachable")),
                "failed": int(match.group("failed")),
            }
        )
    require(recaps, f"Ansible log has no parseable recap: {path}")
    return recaps


def require_successful_recap(path: Path, *, changed_zero: bool) -> None:
    recaps = parse_ansible_recap(path)
    for recap in recaps:
        require(
            recap["unreachable"] == 0 and recap["failed"] == 0,
            f"Ansible recap is not successful for {recap['host']}: {path}",
        )
        if changed_zero:
            require(
                recap["changed"] == 0,
                f"second Ansible apply is not idempotent for {recap['host']}: {path}",
            )


def idempotence_payload(
    check_log: Path,
    first_apply_log: Path,
    second_apply_log: Path,
) -> dict[str, Any]:
    require_successful_recap(check_log, changed_zero=False)
    require_successful_recap(first_apply_log, changed_zero=False)
    require_successful_recap(second_apply_log, changed_zero=True)
    return {
        "check_mode_sha256": hash_regular_file(check_log),
        "first_apply_sha256": hash_regular_file(first_apply_log),
        "second_apply_sha256": hash_regular_file(second_apply_log),
        "second_apply_changed_zero": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    payload_parser = subparsers.add_parser("payload")
    payload_parser.add_argument("--gate", required=True)
    payload_parser.add_argument("--value", action="append", default=[])
    payload_parser.add_argument("--true", dest="true_fields", action="append", default=[])
    payload_parser.add_argument("--false", dest="false_fields", action="append", default=[])
    payload_parser.add_argument("--hash-file", action="append", default=[])

    storage_parser = subparsers.add_parser("storage")
    storage_parser.add_argument(
        "--contract",
        default="/etc/privatestack/bootstrap-storage.yml",
    )
    storage_parser.add_argument(
        "--mountpoint",
        default="/var/lib/libvirt/images",
    )
    storage_parser.add_argument(
        "--hyperlab-root",
        default="/var/lib/libvirt/images/hyperlab",
    )

    idempotence_parser = subparsers.add_parser("idempotence")
    idempotence_parser.add_argument("--check-log", required=True)
    idempotence_parser.add_argument("--first-apply-log", required=True)
    idempotence_parser.add_argument("--second-apply-log", required=True)

    args = parser.parse_args()
    try:
        manifest = load_yaml(Path(args.manifest))
        if args.operation == "payload":
            result = build_payload(
                manifest,
                args.gate,
                args.value,
                args.true_fields,
                args.false_fields,
                args.hash_file,
            )
        elif args.operation == "storage":
            gate_contract(manifest, "storage-handoff")
            mountpoint = Path(args.mountpoint)
            hyperlab_root = Path(args.hyperlab_root)
            result = storage_payload(
                Path(args.contract),
                mountpoint,
                hyperlab_root,
                findmnt_observation(mountpoint),
                findmnt_observation(hyperlab_root),
                lsattr_text(mountpoint),
            )
        else:
            gate_contract(manifest, "host-idempotence")
            result = idempotence_payload(
                Path(args.check_log),
                Path(args.first_apply_log),
                Path(args.second_apply_log),
            )
    except (AcceptanceError, OSError, ValueError) as exc:
        print(f"release probe refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
