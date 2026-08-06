#!/usr/bin/env python3
"""Contracts for the opt-in Linux Looking Glass sender experiment."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "tools/guest_plan.py"
VFIO_PLAN = ROOT / "tools/vfio_plan.py"
SPEC = ROOT / "vm-specs/arch-dev-vfio.yml"
PROFILES = ROOT / "group_vars/all/vm-resource-profiles.yml"
STORE = Path("/var/lib/privatestack/hyperlab")


def run(*argv: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
    )


def main() -> int:
    plan_result = run(
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
    )
    assert plan_result.returncode == 0, plan_result.stderr
    plan = json.loads(plan_result.stdout)
    assert plan["name"] == "arch-dev-vfio"
    assert plan["os_family"] == "linux"
    assert plan["device_profile"] == "vfio"
    assert plan["looking_glass"] is True
    assert plan["looking_glass_mode"] == "linux-experimental"
    assert plan["looking_glass_host_build_required"] is None
    assert plan["memory_request"] == 8192
    assert plan["vcpus"] == 4

    hardware = yaml.safe_load((ROOT / "group_vars/all/hardware.yml").read_text())
    trust = yaml.safe_load((ROOT / "group_vars/all/networks.yml").read_text())[
        "gpu_trust_levels"
    ]
    looking = yaml.safe_load(
        (ROOT / "group_vars/all/looking-glass.yml").read_text()
    )
    with tempfile.TemporaryDirectory() as temporary:
        report = Path(temporary) / "hardware-profile.yml"
        report.write_text(
            yaml.safe_dump(
                {
                    "host_profile": "nitro-3060",
                    "vfio_ids": ["10de:2520", "10de:228e"],
                    "vfio_devices": [
                        {"id": "10de:2520", "pci": "01:00.0"},
                        {"id": "10de:228e", "pci": "01:00.1"},
                    ],
                    "gpu_pci": "01:00.0",
                    "gpu_audio_pci": "01:00.1",
                    "cpu_threads": 8,
                },
                sort_keys=False,
            )
        )
        vfio_result = run(
            sys.executable,
            str(VFIO_PLAN),
            "--report",
            str(report),
            "--profiles-json",
            json.dumps(hardware["host_profiles"]),
            "--trust-levels-json",
            json.dumps(trust),
            "--looking-glass-build",
            str(looking["hyperlab_looking_glass_build"]),
            "--looking-glass-device",
            str(looking["hyperlab_looking_glass_device"]),
            "--looking-glass-shm-mb",
            "64",
            "--spice-host",
            str(looking["hyperlab_looking_glass_spice_host"]),
            "--spice-port",
            str(looking["hyperlab_looking_glass_spice_port"]),
            stdin=json.dumps(plan),
        )
        assert vfio_result.returncode == 0, vfio_result.stderr
        vfio = json.loads(vfio_result.stdout)
        assert vfio["looking_glass_enabled"] is True
        assert vfio["looking_glass_mode"] == "linux-experimental"
        assert vfio["looking_glass_shm_bytes"] == 64 * 1024 * 1024
        assert vfio["cpu_pinning"]["enabled"] is True

        env = Environment(
            loader=FileSystemLoader(str(ROOT / "roles/guest/templates")),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )
        rendered = env.get_template("domain.xml.j2").render(
            guest_plan=plan,
            guest_resolved_memory_mb=8192,
            guest_vfio=vfio,
        )
        assert "ivshmem-plain" in rendered
        assert "/dev/kvmfr0" in rendered
        assert 'port="5900" autoport="no"' in rendered
        assert "<vcpupin" in rendered

    defaults = yaml.safe_load(
        (ROOT / "roles/guest_looking_glass_linux/defaults/main.yml").read_text()
    )
    tasks = (ROOT / "roles/guest_looking_glass_linux/tasks/main.yml").read_text()
    graph = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text())
    assert defaults["guest_looking_glass_linux_experimental"] is False
    assert defaults["guest_looking_glass_linux_commit"] == (
        "{{ hyperlab_looking_glass_commit }}"
    )
    assert defaults["guest_looking_glass_linux_packages"] == [
        "git",
        "cmake",
        "gcc",
        "make",
        "pkgconf",
        "glib2",
        "libpipewire",
    ]
    assert "-DUSE_XCB=OFF" in tasks
    assert "-DUSE_PIPEWIRE=ON" in tasks
    assert "runtime_enabled: false" in tasks
    assert "systemd_service" not in tasks
    assert "brick_guard_brick: guest_looking_glass_linux" in tasks
    assert graph["brick_requires"]["guest_looking_glass_linux"] == [
        "guest_desktop_hyprland"
    ]

    print("Linux Looking Glass experiment contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
