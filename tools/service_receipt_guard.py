#!/usr/bin/env python3
"""Verify a root-owned M7 service registration receipt against its plan."""
from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any

import yaml

SHA_RE = re.compile(r"^[a-f0-9]{64}$")


class ReceiptError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReceiptError(message)


def load_receipt(path: Path) -> dict[str, Any]:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ReceiptError(f"service receipt does not exist: {path}") from exc
    except OSError as exc:
        raise ReceiptError(f"service receipt cannot be inspected: {exc}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            "service receipt must be one regular non-symlink file")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ReceiptError(f"service receipt cannot be read as YAML: {exc}") from exc
    require(isinstance(data, dict), "service receipt root must be a mapping")
    return data


def verify(plan: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "schema_version": 1,
        "id": plan.get("id"),
        "vm": plan.get("vm"),
        "spec_sha256": plan.get("spec_sha256"),
        "vm_spec_sha256": plan.get("vm_spec_sha256"),
        "network_profile": plan.get("network_profile"),
        "memory_reservation_mb": plan.get("memory_reservation_mb"),
        "dhcp": plan.get("dhcp"),
        "exposures": plan.get("exposures"),
        "backup_policy": plan.get("backup_policy"),
        "restore_policy": plan.get("restore_policy"),
        "disk_path": plan.get("disk_path"),
        "registered": True,
    }
    require(set(receipt) == set(expected), "service receipt fields drift from schema v1")
    for key, value in expected.items():
        require(receipt.get(key) == value,
                f"service receipt {key}={receipt.get(key)!r} != expected {value!r}")
    for key in ("spec_sha256", "vm_spec_sha256"):
        require(SHA_RE.fullmatch(str(receipt.get(key, ""))) is not None,
                f"service receipt {key} is not a lowercase SHA-256")
    require(isinstance(receipt.get("memory_reservation_mb"), int)
            and not isinstance(receipt.get("memory_reservation_mb"), bool)
            and receipt["memory_reservation_mb"] >= 512,
            "service receipt memory reservation is invalid")
    forbidden = {"password", "secret", "token", "private_key", "credentials"}
    require(not (forbidden & set(receipt)), "service receipt contains forbidden secret fields")
    return {
        "id": receipt["id"],
        "vm": receipt["vm"],
        "memory_reservation_mb": receipt["memory_reservation_mb"],
        "dhcp": receipt["dhcp"],
        "registered": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    args = parser.parse_args()
    try:
        plan = json.load(sys.stdin)
        require(isinstance(plan, dict), "service plan JSON root must be a mapping")
        result = verify(plan, load_receipt(Path(args.receipt)))
    except (OSError, json.JSONDecodeError, ReceiptError) as exc:
        print(f"service receipt refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
