#!/usr/bin/env python3
"""Contracts for named, runtime-selectable VM resource profiles."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "tools/guest_plan.py"
PROFILES = ROOT / "group_vars/all/vm-resource-profiles.yml"
SPEC = ROOT / "vm-specs/arch-dev.yml"
STORE = Path("/var/lib/privatestack/hyperlab")


def plan(profile: str | None = None) -> subprocess.CompletedProcess[str]:
    argv = [
        sys.executable,
        str(PLAN),
        "--root",
        str(ROOT),
        "--spec",
        str(SPEC),
        "--store",
        str(STORE),
        "--resource-profiles",
        str(PROFILES),
    ]
    if profile is not None:
        argv.extend(["--resource-profile", profile])
    return subprocess.run(argv, text=True, capture_output=True, check=False)


def main() -> int:
    profile_root = yaml.safe_load(PROFILES.read_text(encoding="utf-8"))
    profiles = profile_root["vm_resource_profiles"]["arch-dev"]
    assert profiles == {
        "balanced": {"memory_mb": 8192, "vcpus": 4},
        "heavy": {"memory_mb": 16384, "vcpus": 4},
    }

    spec = yaml.safe_load(SPEC.read_text(encoding="utf-8"))
    assert spec["resource_profile"] == "balanced"
    assert spec["resources"]["memory_mb"] == 8192
    assert spec["resources"]["vcpus"] == 4

    balanced = plan()
    assert balanced.returncode == 0, balanced.stderr
    balanced_data = json.loads(balanced.stdout)
    assert balanced_data["resource_profile"] == "balanced"
    assert balanced_data["memory_request"] == 8192
    assert balanced_data["vcpus"] == 4

    heavy = plan("heavy")
    assert heavy.returncode == 0, heavy.stderr
    heavy_data = json.loads(heavy.stdout)
    assert heavy_data["resource_profile"] == "heavy"
    assert heavy_data["memory_request"] == 16384
    assert heavy_data["vcpus"] == 4
    assert heavy_data["disk_gib"] == balanced_data["disk_gib"]
    assert heavy_data["device_profile"] == balanced_data["device_profile"]

    refused = plan("maximum")
    assert refused.returncode == 2
    assert "balanced or heavy" in refused.stderr

    role = (ROOT / "roles/guest/tasks/main.yml").read_text(encoding="utf-8")
    state = (ROOT / "roles/guest/templates/state.yml.j2").read_text(encoding="utf-8")
    validate = (ROOT / "roles/guest/tasks/validate.yml").read_text(encoding="utf-8")
    assert "--resource-profile" in role
    assert "guest_resource_profiles_file" in role
    assert "resource_profile:" in state
    assert "guest_existing_state.resource_profile" in validate

    print("VM resource profile contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
