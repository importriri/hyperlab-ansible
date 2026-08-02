#!/usr/bin/env python3
"""Verify one offline M7 service backup directory and provenance receipt."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml


class BackupError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise BackupError(message)


def regular_file(path: Path, label: str) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise BackupError(f"{label} does not exist: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be one regular non-symlink file")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def qemu_info(path: Path, binary: str) -> dict[str, Any]:
    info = subprocess.run(
        [binary, "info", "--output=json", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    require(info.returncode == 0, f"qemu-img info failed: {info.stderr.strip()}")
    try:
        data = json.loads(info.stdout)
    except json.JSONDecodeError as exc:
        raise BackupError(f"qemu-img info returned invalid JSON: {exc}") from exc
    require(isinstance(data, dict), "qemu-img info root must be a mapping")
    check = subprocess.run(
        [binary, "check", "-f", "qcow2", str(path)],
        text=True,
        capture_output=True,
        check=False,
    )
    require(check.returncode == 0, f"qemu-img check failed: {check.stderr.strip()}")
    return data


def verify(context: dict[str, Any], receipt_path: Path, disk_path: Path, qemu_img: str) -> dict[str, Any]:
    regular_file(receipt_path, "service backup receipt")
    regular_file(disk_path, "service backup disk")
    try:
        receipt = yaml.safe_load(receipt_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise BackupError(f"service backup receipt cannot be parsed: {exc}") from exc
    require(isinstance(receipt, dict), "service backup receipt root must be a mapping")
    info = qemu_info(disk_path, qemu_img)
    require(info.get("format") == "qcow2", "service backup disk format must be qcow2")
    require(info.get("backing-filename") is None, "service backup disk must not have a backing file")
    virtual_size = info.get("virtual-size")
    require(isinstance(virtual_size, int) and virtual_size > 0, "service backup virtual size is invalid")
    disk_sha256 = sha256(disk_path)
    expected = {
        "schema_version": 1,
        "service_id": context.get("id"),
        "vm": context.get("vm"),
        "backup_id": context.get("backup_id"),
        "service_spec_sha256": context.get("spec_sha256"),
        "service_vm_spec_sha256": context.get("vm_spec_sha256"),
        "service_receipt_sha256": context.get("service_receipt_sha256"),
        "source_disk_path": context.get("disk_path"),
        "disk_sha256": disk_sha256,
        "virtual_size_bytes": virtual_size,
        "qemu_img_check": "pass",
    }
    require(set(receipt) == set(expected), "service backup receipt fields drift from schema v1")
    for key, value in expected.items():
        require(receipt.get(key) == value,
                f"service backup receipt {key}={receipt.get(key)!r} != expected {value!r}")
    return {
        "service_id": receipt["service_id"],
        "backup_id": receipt["backup_id"],
        "disk_sha256": disk_sha256,
        "virtual_size_bytes": virtual_size,
        "verified": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--disk", required=True)
    parser.add_argument("--qemu-img", required=True)
    args = parser.parse_args()
    try:
        context = json.load(sys.stdin)
        require(isinstance(context, dict), "service backup context JSON root must be a mapping")
        result = verify(context, Path(args.receipt), Path(args.disk), args.qemu_img)
    except (OSError, json.JSONDecodeError, BackupError) as exc:
        print(f"service backup refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
