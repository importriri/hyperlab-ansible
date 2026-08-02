#!/usr/bin/env python3
"""Derive safe offline backup, restore and deletion paths for one M7 service."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

BACKUP_ID_RE = re.compile(r"^[0-9]{8}T[0-9]{6}Z$")


class RecoveryPlanError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RecoveryPlanError(message)


def within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def build(plan: dict[str, Any], operation: str, backup_id: str) -> dict[str, Any]:
    require(operation in {"backup", "restore", "delete-backup"}, "unsupported service recovery operation")
    require(BACKUP_ID_RE.fullmatch(backup_id) is not None,
            "service backup id must be an explicit UTC stamp YYYYMMDDTHHMMSSZ")
    service_id = plan.get("id")
    vm = plan.get("vm")
    backup_root = Path(str(plan.get("backup_dir", ""))).resolve(strict=False)
    disk_path = Path(str(plan.get("disk_path", ""))).resolve(strict=False)
    require(service_id == vm and isinstance(service_id, str) and service_id.startswith("svc-"),
            "service recovery plan identity is invalid")
    require(str(backup_root) not in {"", "/"}, "service backup root is invalid")
    require(str(disk_path) not in {"", "/"}, "service disk path is invalid")
    final_dir = (backup_root / backup_id).resolve(strict=False)
    staging_dir = (backup_root / f"{backup_id}.new").resolve(strict=False)
    require(within(final_dir, backup_root) and within(staging_dir, backup_root),
            "service backup path escaped its managed root")
    return {
        "operation": operation,
        "service_id": service_id,
        "vm": vm,
        "backup_id": backup_id,
        "backup_root": str(backup_root),
        "backup_dir": str(final_dir),
        "backup_staging_dir": str(staging_dir),
        "backup_disk": str(final_dir / "disk.qcow2"),
        "backup_receipt": str(final_dir / "receipt.yml"),
        "backup_staging_disk": str(staging_dir / "disk.qcow2"),
        "backup_staging_receipt": str(staging_dir / "receipt.yml"),
        "disk_path": str(disk_path),
        "restore_new_path": str(disk_path) + ".restore-new",
        "restore_rollback_path": str(disk_path) + ".pre-restore",
        "confirmation": f"{service_id}:{backup_id}",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--operation", choices=["backup", "restore", "delete-backup"], required=True)
    parser.add_argument("--backup-id", required=True)
    args = parser.parse_args()
    try:
        plan = json.load(sys.stdin)
        require(isinstance(plan, dict), "service plan JSON root must be a mapping")
        result = build(plan, args.operation, args.backup_id)
    except (OSError, json.JSONDecodeError, RecoveryPlanError) as exc:
        print(f"service recovery plan refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
