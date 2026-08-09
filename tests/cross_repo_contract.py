#!/usr/bin/env python3
"""The cross-repository half of ADR 0006, which the ADR described as if it
already existed.

hyperlab-ansible owns what the pipeline configures. arch-hypervisor-lab
owns what has been proven. The overlap is the profile name and the VFIO IDs,
and nothing compared them: each repository could rename a profile or correct a
device ID on its own and both suites stayed green.

Takes the path to the other checkout and skips loudly when it is absent, so a
single-repo clone still runs green without pretending it checked anything. The
dedicated CI job passes the path and treats a missing sibling as a failure.

    python tests/cross_repo_contract.py ../arch-hypervisor-lab
    CROSS_REPO_REQUIRED=1 python tests/cross_repo_contract.py ../arch-hypervisor-lab
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SIBLING_FILE = Path("hardware/compatibility.yml")


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def sibling_path(argv: list[str]) -> Path | None:
    if len(argv) > 1:
        return Path(argv[1]).expanduser()
    env = os.environ.get("ARCH_HYPERVISOR_LAB")
    if env:
        return Path(env).expanduser()
    default = ROOT.parent / "arch-hypervisor-lab"
    return default if (default / SIBLING_FILE).is_file() else None


def main() -> int:
    required = os.environ.get("CROSS_REPO_REQUIRED") == "1"
    sibling = sibling_path(sys.argv)

    if sibling is None or not (sibling / SIBLING_FILE).is_file():
        where = sibling if sibling else "../arch-hypervisor-lab"
        message = "no arch-hypervisor-lab checkout at %s" % where
        if required:
            print("CROSS-REPO CONTRACT FAILED\n- %s" % message)
            print("  the dedicated job must check out both repositories")
            return 1
        print("cross-repo contract: SKIPPED - %s" % message)
        print("  nothing was checked. Pass the path to check it:")
        print("  python tests/cross_repo_contract.py ../arch-hypervisor-lab")
        return 0

    profiles = load(ROOT / "group_vars/all/hardware.yml").get("host_profiles", {})
    systems = load(sibling / SIBLING_FILE).get("systems", {})
    errors: list[str] = []

    for name, profile in sorted(profiles.items()):
        if "status" in profile:
            errors.append("%s: status belongs to arch-hypervisor-lab (ADR 0006), "
                          "a repository cannot certify itself" % name)
        system = systems.get(name)
        if system is None:
            errors.append("%s: configured here, absent from the compatibility record" % name)
            continue
        ours = list(profile.get("vfio_ids") or [])
        theirs = list(system.get("vfio_ids") or [])
        if ours != theirs:
            errors.append("%s: VFIO IDs disagree - configured %s, recorded %s"
                          % (name, ours, theirs))
        label = profile.get("label", "")
        for field in ("vendor", "family"):
            value = system.get(field)
            if value and value not in label:
                errors.append("%s: recorded %s %r is missing from the configured label %r"
                              % (name, field, value, label))

    for name in sorted(set(systems) - set(profiles)):
        errors.append("%s: recorded as compatible, absent from host_profiles" % name)

    if errors:
        print("CROSS-REPO CONTRACT FAILED")
        for error in errors:
            print("- %s" % error)
        return 1

    print("cross-repo contract: OK (%d profiles against %s)" % (len(profiles), sibling))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
