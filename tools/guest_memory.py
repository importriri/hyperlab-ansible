#!/usr/bin/env python3
"""Resolve one guest's memory against live libvirt and M7 service commitments."""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from typing import Any


class BudgetError(ValueError):
    pass


def parse_domstats(text: str) -> tuple[int, int]:
    active_mb = 0
    count = 0
    for block in re.split(r"(?=^Domain:)", text, flags=re.MULTILINE):
        if not block.startswith("Domain:"):
            continue
        count += 1
        match = re.search(r"^\s*balloon\.maximum=(\d+)\s*$", block, re.MULTILINE)
        if match is None:
            raise BudgetError("an active domain lacks balloon.maximum in virsh domstats")
        active_mb += math.ceil(int(match.group(1)) / 1024)
    return active_mb, count


def positive_int(mapping: dict[str, Any], key: str) -> int:
    value = mapping.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise BudgetError(f"host profile memory.{key} must be a non-negative integer")
    return value


def service_reservation(value: str) -> tuple[int, dict[str, int]]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise BudgetError(f"service reservations JSON is invalid: {exc}") from exc
    if not isinstance(data, dict):
        raise BudgetError("service reservations JSON root must be a mapping")
    reserved = data.get("reserved_mb", 0)
    reservations = data.get("reservations", {})
    if not isinstance(reserved, int) or isinstance(reserved, bool) or reserved < 0:
        raise BudgetError("service reserved_mb must be a non-negative integer")
    if not isinstance(reservations, dict):
        raise BudgetError("service reservations must be a mapping")
    if any(not isinstance(name, str) or not isinstance(memory, int) or isinstance(memory, bool) or memory < 512
           for name, memory in reservations.items()):
        raise BudgetError("service reservation entries are invalid")
    if sum(reservations.values()) != reserved:
        raise BudgetError("service reserved_mb differs from reservation entries")
    return reserved, reservations


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-json", required=True)
    parser.add_argument("--memtotal-mb", required=True, type=int)
    parser.add_argument("--request", required=True)
    parser.add_argument("--floor-mb", required=True, type=int)
    parser.add_argument("--overcommit", choices=["true", "false"], required=True)
    parser.add_argument("--device-profile", choices=["standard", "vfio"], required=True)
    parser.add_argument("--service-reservations-json", default='{"reserved_mb":0,"reservations":{}}')
    parser.add_argument("--candidate-name", default="")
    args = parser.parse_args()
    try:
        profile = json.loads(args.profile_json)
        if not isinstance(profile, dict):
            raise BudgetError("profile JSON must be a mapping")
        active_guest_mb, active_domain_count = parse_domstats(sys.stdin.read())
        host_reserved_mb = positive_int(profile, "host_reserved_mb")
        qemu_overhead_mb = positive_int(profile, "qemu_overhead_per_domain_mb")
        legacy_services_reserved_mb = positive_int(profile, "services_reserved_mb")
        vfio_fixed_overhead_mb = positive_int(profile, "vfio_fixed_overhead_mb")
        max_auto_mb = positive_int(profile, "max_auto_memory_mb")
        ratio = profile.get("standard_overcommit_ratio")
        if not isinstance(ratio, (int, float)) or isinstance(ratio, bool) or ratio < 1.0:
            raise BudgetError("standard_overcommit_ratio must be >= 1.0")
        if legacy_services_reserved_mb != 0:
            raise BudgetError("profile services_reserved_mb must stay 0; M7 uses registered service receipts")
        dynamic_services_reserved_mb, service_reservations = service_reservation(args.service_reservations_json)
        overcommit = args.overcommit == "true"
        if args.device_profile == "vfio" and overcommit:
            raise BudgetError("VFIO memory cannot be overcommitted because the IOMMU pins it")

        candidate_fixed_mb = vfio_fixed_overhead_mb if args.device_profile == "vfio" else 0
        overhead_mb = (active_domain_count + 1) * qemu_overhead_mb + candidate_fixed_mb
        base_pool_mb = (
            args.memtotal_mb
            - host_reserved_mb
            - legacy_services_reserved_mb
            - dynamic_services_reserved_mb
            - overhead_mb
        )
        physical_remaining_mb = base_pool_mb - active_guest_mb
        if physical_remaining_mb < 0:
            raise BudgetError("host commitments already exceed the physical guest budget")
        if overcommit:
            commit_limit_mb = math.floor(base_pool_mb * float(ratio))
            selected_remaining_mb = commit_limit_mb - active_guest_mb
        else:
            commit_limit_mb = base_pool_mb
            selected_remaining_mb = physical_remaining_mb
        if args.request == "auto":
            resolved_mb = min(selected_remaining_mb, max_auto_mb)
            resolved_mb = (resolved_mb // 1024) * 1024
        else:
            try:
                resolved_mb = int(args.request)
            except ValueError as exc:
                raise BudgetError("memory request must be auto or an integer") from exc
        if resolved_mb < args.floor_mb:
            raise BudgetError(
                f"resolved memory {resolved_mb} MiB is below image floor {args.floor_mb} MiB; "
                f"remaining={selected_remaining_mb} MiB"
            )
        if resolved_mb > selected_remaining_mb:
            raise BudgetError(
                f"requested memory {resolved_mb} MiB exceeds remaining budget {selected_remaining_mb} MiB"
            )
        print(json.dumps({
            "resolved_memory_mb": resolved_mb,
            "candidate_name": args.candidate_name,
            "device_profile": args.device_profile,
            "memtotal_mb": args.memtotal_mb,
            "host_reserved_mb": host_reserved_mb,
            "services_reserved_mb": legacy_services_reserved_mb,
            "dynamic_services_reserved_mb": dynamic_services_reserved_mb,
            "service_reservations": service_reservations,
            "active_guest_mb": active_guest_mb,
            "active_domain_count": active_domain_count,
            "qemu_overhead_per_domain_mb": qemu_overhead_mb,
            "vfio_fixed_overhead_mb": candidate_fixed_mb,
            "overhead_mb": overhead_mb,
            "base_pool_mb": base_pool_mb,
            "physical_remaining_mb": physical_remaining_mb,
            "standard_overcommit_ratio": ratio,
            "commit_limit_mb": commit_limit_mb,
            "selected_remaining_mb": selected_remaining_mb,
        }, sort_keys=True))
    except (BudgetError, json.JSONDecodeError) as exc:
        print(f"guest memory refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
