#!/usr/bin/env python3
"""Reviewed CPU-isolation contract for VFIO guests on the Nitro 5."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    hardware = yaml.safe_load((ROOT / "group_vars/all/hardware.yml").read_text())
    pinning = hardware["host_profiles"]["nitro-3060"]["cpu_pinning"]
    assert pinning["host_cpu_threads"] == 8
    assert pinning["plans"]["4"] == {
        "vcpu_pins": [2, 6, 3, 7],
        "emulator_cpus": [0, 4],
        "iothread_cpus": [1, 5],
        "topology": {"sockets": 1, "dies": 1, "cores": 2, "threads": 2},
    }
    assert pinning["plans"]["6"] == {
        "vcpu_pins": [1, 5, 2, 6, 3, 7],
        "emulator_cpus": [0, 4],
        "iothread_cpus": [0, 4],
        "topology": {"sockets": 1, "dies": 1, "cores": 3, "threads": 2},
    }

    planner = (ROOT / "tools/vfio_plan.py").read_text()
    assert "reviewed CPU pinning does not match" in planner
    assert "no reviewed CPU pinning plan exists" in planner
    assert "guest CPU pins must be disjoint" in planner

    domain = (ROOT / "roles/guest/templates/domain.xml.j2").read_text()
    for fragment in (
        "<iothreads>1</iothreads>",
        "<vcpupin",
        "<emulatorpin",
        "<iothreadpin",
        "<topology",
        'iothread="1"',
    ):
        assert fragment in domain

    vfio_tasks = (ROOT / "roles/guest/tasks/vfio.yml").read_text()
    assert vfio_tasks.count("when: guest_vfio.looking_glass_enabled | bool") == 4

    print("VFIO CPU pinning contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
