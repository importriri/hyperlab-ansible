#!/usr/bin/env python3
"""Verify a committed base image and its provenance receipt."""
from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any

import yaml

from image_inspect import InspectError, inspect

SHA_RE = re.compile(r"^[a-f0-9]{64}$")


class ReceiptError(ValueError):
    """The committed image transaction is incomplete or inconsistent."""


def load_receipt(path: Path) -> dict[str, Any]:
    try:
        lst = path.lstat()
    except FileNotFoundError as exc:
        raise ReceiptError(f"receipt does not exist: {path}") from exc
    except OSError as exc:
        raise ReceiptError(f"receipt cannot be inspected: {exc}") from exc
    if stat.S_ISLNK(lst.st_mode) or not stat.S_ISREG(lst.st_mode):
        raise ReceiptError(f"receipt must be one regular non-symlink file: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ReceiptError(f"receipt cannot be read as YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ReceiptError("receipt root must be a mapping")
    return data


def require_equal(receipt: dict[str, Any], key: str, expected: Any) -> None:
    if receipt.get(key) != expected:
        raise ReceiptError(f"receipt {key}={receipt.get(key)!r} != expected {expected!r}")


def require_safe_basename(value: Any) -> None:
    if not isinstance(value, str) or not value or Path(value).name != value:
        raise ReceiptError("receipt source_basename must be one non-empty basename")


def verify(plan: dict[str, Any], receipt: dict[str, Any], inspection: dict[str, Any], mode: str) -> dict[str, Any]:
    require_equal(receipt, "schema_version", 1)
    require_equal(receipt, "id", plan.get("id"))
    require_equal(receipt, "policy_sha256", plan.get("policy_sha256"))
    require_equal(receipt, "base_path", plan.get("base_path"))
    require_equal(receipt, "artifact_sha256", inspection.get("sha256"))
    require_equal(receipt, "format", inspection.get("format"))
    require_equal(receipt, "virtual_size_bytes", inspection.get("virtual_size_bytes"))
    require_equal(receipt, "source_type", plan.get("source_type"))
    planned_basename = plan.get("source_basename")
    if planned_basename:
        require_equal(receipt, "source_basename", planned_basename)
    else:
        require_safe_basename(receipt.get("source_basename"))
    require_equal(receipt, "source_sha256", plan.get("source_sha256"))
    require_equal(receipt, "private", plan.get("private"))
    require_equal(
        receipt,
        "looking_glass_host_build_required",
        plan.get("looking_glass_host_build_required"),
    )
    require_equal(
        receipt,
        "looking_glass_host_build_observed",
        plan.get("looking_glass_host_build_observed"),
    )
    workshop_keys = (
        "windows_workshop_policy_sha256",
        "windows_workshop_receipt_sha256",
    )
    for key in workshop_keys:
        require_equal(receipt, key, plan.get(key))
    workshop_values = [plan.get(key) for key in workshop_keys]
    if any(value is not None for value in workshop_values):
        if plan.get("os_family") != "windows":
            raise ReceiptError("non-Windows plan must not claim Windows workshop provenance")
        if not all(SHA_RE.fullmatch(str(value or "")) is not None for value in workshop_values):
            raise ReceiptError("Windows workshop provenance must contain two lowercase SHA-256 values")
    elif any(receipt.get(key) is not None for key in workshop_keys):
        raise ReceiptError("receipt claims Windows workshop provenance absent from the plan")
    expected_url = None if plan.get("private") else plan.get("source_url")
    require_equal(receipt, "source_url", expected_url)
    if "local_source" in receipt:
        raise ReceiptError("receipt must never retain a host-local source path")
    if receipt.get("qemu_img_check") != "pass":
        raise ReceiptError("receipt does not record a passing qemu-img check")
    if mode == "sealed":
        if plan.get("manifest_status") != "sealed":
            raise ReceiptError("checked-in manifest is not sealed")
        if plan.get("manifest_artifact_sha256") != inspection.get("sha256"):
            raise ReceiptError("checked-in manifest sha256 differs from the committed base")
    return {
        "id": plan.get("id"),
        "status": "sealed" if mode == "sealed" else "prepared",
        "artifact_sha256": inspection.get("sha256"),
        "receipt_path": plan.get("receipt_path"),
        "windows_workshop_receipt_sha256": plan.get("windows_workshop_receipt_sha256"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--base", required=True)
    parser.add_argument("--qemu-img", required=True)
    parser.add_argument("--mode", choices=["prepared", "sealed"], required=True)
    args = parser.parse_args()
    try:
        plan = json.load(sys.stdin)
        if not isinstance(plan, dict):
            raise ReceiptError("plan JSON root must be a mapping")
        receipt = load_receipt(Path(args.receipt))
        inspection = inspect(
            Path(args.base),
            args.qemu_img,
            str(plan.get("format")),
            int(plan.get("virtual_size_gib")),
        )
        result = verify(plan, receipt, inspection, args.mode)
    except (OSError, json.JSONDecodeError, TypeError, ValueError, InspectError, ReceiptError) as exc:
        print(f"image receipt refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
