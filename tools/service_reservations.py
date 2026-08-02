#!/usr/bin/env python3
"""Sum inactive M7 service reservations without double-counting active VMs."""
from __future__ import annotations

import argparse
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any

import yaml

DOMAIN_RE = re.compile(r"^Domain:\s+'?([^'\n]+)'?\s*$", re.MULTILINE)
SERVICE_RE = re.compile(r"^svc-[a-z0-9][a-z0-9-]*$")


class ReservationError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ReservationError(message)


def active_domains(text: str) -> set[str]:
    return {match.group(1).strip() for match in DOMAIN_RE.finditer(text)}


def read_receipt(path: Path) -> dict[str, Any]:
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"service reservation receipt must be regular and non-symlink: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ReservationError(f"cannot parse service receipt {path}: {exc}") from exc
    require(isinstance(data, dict), f"service receipt root must be a mapping: {path}")
    return data


def calculate(root: Path, candidate_name: str, domstats: str) -> dict[str, Any]:
    active = active_domains(domstats)
    if not root.exists():
        return {
            "reserved_mb": 0,
            "reservations": {},
            "active_service_names": sorted(name for name in active if name.startswith("svc-")),
            "excluded": sorted({candidate_name} - {""}),
        }
    require(root.is_dir() and not root.is_symlink(), "service receipt root must be a non-symlink directory")
    reservations: dict[str, int] = {}
    excluded: set[str] = set()
    seen_vm: set[str] = set()
    for path in sorted(root.glob("*.yml")):
        receipt = read_receipt(path)
        service_id = receipt.get("id")
        vm = receipt.get("vm")
        memory = receipt.get("memory_reservation_mb")
        require(isinstance(service_id, str) and SERVICE_RE.fullmatch(service_id) is not None,
                f"invalid service id in {path}")
        require(path.stem == service_id, f"service receipt filename differs from id: {path}")
        require(isinstance(vm, str) and SERVICE_RE.fullmatch(vm) is not None,
                f"invalid service VM in {path}")
        require(vm not in seen_vm, f"duplicate service VM reservation: {vm}")
        seen_vm.add(vm)
        require(isinstance(memory, int) and not isinstance(memory, bool) and memory >= 512,
                f"invalid memory reservation in {path}")
        require(receipt.get("registered") is True, f"service receipt is not registered: {path}")
        if vm == candidate_name or vm in active:
            excluded.add(vm)
            continue
        reservations[vm] = memory
    return {
        "reserved_mb": sum(reservations.values()),
        "reservations": dict(sorted(reservations.items())),
        "active_service_names": sorted(name for name in active if name.startswith("svc-")),
        "excluded": sorted(excluded),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt-root", required=True)
    parser.add_argument("--candidate-name", default="")
    args = parser.parse_args()
    try:
        result = calculate(Path(args.receipt_root), args.candidate_name, sys.stdin.read())
    except (OSError, ReservationError) as exc:
        print(f"service reservations refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
