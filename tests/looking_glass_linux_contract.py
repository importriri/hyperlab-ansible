#!/usr/bin/env python3
"""Contracts for the opt-in Linux Looking Glass sender experiment."""
from __future__ import annotations

import hashlib
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
    assert plan["memory_request"] == 16384
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
            guest_resolved_memory_mb=16384,
            guest_vfio=vfio,
            hyperlab_looking_glass_spice_socket_dir=looking[
                "hyperlab_looking_glass_spice_socket_dir"
            ],
        )
        assert "ivshmem-plain" in rendered
        assert "/dev/kvmfr0" in rendered
        assert 'listen type="socket"' in rendered
        assert "/run/hyperlab-spice/" in rendered
        assert "<vcpupin" in rendered

    defaults = yaml.safe_load(
        (ROOT / "roles/guest_looking_glass_linux/defaults/main.yml").read_text()
    )
    tasks = (ROOT / "roles/guest_looking_glass_linux/tasks/main.yml").read_text()
    patch_path = (
        ROOT
        / "roles/guest_looking_glass_linux/files/portal-gcc16-autoptr.patch"
    )
    patch_sha256 = hashlib.sha256(patch_path.read_bytes()).hexdigest()
    graph = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text())
    assert defaults["guest_looking_glass_linux_experimental"] is False
    assert defaults["guest_looking_glass_linux_commit"] == (
        "{{ hyperlab_looking_glass_commit }}"
    )
    assert defaults["guest_looking_glass_linux_packages"] == [
        "dkms",
        "{{ guest_looking_glass_linux_headers_package }}",
        "git",
        "cmake",
        "gcc",
        "make",
        "pkgconf",
        "glib2",
        "libpipewire",
    ]
    assert defaults["guest_looking_glass_linux_compat_patch"] == (
        "portal-gcc16-autoptr.patch"
    )
    assert defaults["guest_looking_glass_linux_compat_patch_sha256"] == patch_sha256
    assert patch_sha256 == (
        "868d7e1dc49ae9c583bed300f2a7f73221c84310fe16a5463fa79f8725a1c7e2"
    )
    assert "guest_looking_glass_linux_compat_patch_sha256" in tasks
    assert "compat_patch_sha256:" in tasks
    assert "--check" in tasks
    assert "checkout" in tasks
    assert "register: guest_looking_glass_linux_compat_patch_apply" in tasks
    assert "guest_looking_glass_linux_compat_patch_apply is defined" in tasks
    assert "guest_looking_glass_linux_compat_patch_apply.rc" in tasks
    assert "| default(1) == 0" in tasks
    assert "-Wno-error" not in tasks
    assert defaults["guest_looking_glass_linux_kvmfr_version"] == "0.0.12"
    assert defaults["guest_looking_glass_linux_kvmfr_device"] == "/dev/kvmfr0"
    assert defaults["guest_looking_glass_linux_kvmfr_pci_id"] == "1af4:1110"
    assert defaults["guest_looking_glass_linux_capture_output"] == "HEADLESS-0"
    assert defaults["guest_looking_glass_linux_capture_max_fps"] == 144
    assert defaults["guest_looking_glass_linux_xdph_picker"] == (
        "/usr/local/bin/privatestack-looking-glass-xdph-picker"
    )
    assert defaults["guest_looking_glass_linux_xdph_config"] == (
        "/home/{{ admin_user }}/.config/hypr/xdph.conf"
    )
    assert "static_size_mb" in tasks
    assert "/etc/modules-load.d/kvmfr.conf" in tasks
    assert '- "{{ guest_looking_glass_linux_kvmfr_version }}"' in tasks
    assert '- "{{ ansible_facts[\'kernel\'] }}"' in tasks
    assert "': installed'" in tasks
    assert "70-kvmfr-guest.rules.j2" in tasks
    assert "Kernel driver in use: kvmfr" in tasks
    assert "--subsystem-match=kvmfr" in tasks
    sender_config = (
        ROOT
        / "roles/guest_looking_glass_linux/templates/looking-glass-host.ini.j2"
    ).read_text()
    assert "shmFile={{ guest_looking_glass_linux_kvmfr_device }}" in sender_config
    guest_rule = (
        ROOT
        / "roles/guest_looking_glass_linux/templates/70-kvmfr-guest.rules.j2"
    ).read_text()
    assert 'OWNER="{{ admin_user }}"' in guest_rule
    assert 'MODE="0600"' in guest_rule
    assert "\\n" not in guest_rule
    assert guest_rule.endswith("\n")
    assert "-DUSE_XCB=OFF" in tasks
    assert "-DUSE_PIPEWIRE=ON" in tasks
    assert "runtime_enabled: false" in tasks
    assert "systemd_service" not in tasks
    assert "xdph-headless-picker.sh.j2" in tasks
    assert "xdph.conf.j2" in tasks
    assert 'mode: "0755"' in tasks
    assert 'mode: "0600"' in tasks

    portal_env = Environment(
        loader=FileSystemLoader(
            str(ROOT / "roles/guest_looking_glass_linux/templates")
        ),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    portal_vars = {
        "guest_looking_glass_linux_capture_output": "HEADLESS-0",
        "guest_looking_glass_linux_capture_max_fps": 144,
        "guest_looking_glass_linux_xdph_picker": (
            "/usr/local/bin/privatestack-looking-glass-xdph-picker"
        ),
    }
    picker = portal_env.get_template("xdph-headless-picker.sh.j2").render(
        **portal_vars
    )
    assert "/usr/bin/hyprctl -j monitors" in picker
    assert "json.load(sys.stdin)" in picker
    assert "monitor.get(\"name\") == wanted" in picker
    assert "and not monitor.get(\"disabled\", False)" in picker
    assert "[SELECTION]/screen:%s\\n" in picker
    assert "guest_looking_glass_linux_capture_output='HEADLESS-0'" in picker
    portal_config = portal_env.get_template("xdph.conf.j2").render(
        **portal_vars
    )
    assert "max_fps = 144" in portal_config
    assert (
        "custom_picker_binary = "
        "/usr/local/bin/privatestack-looking-glass-xdph-picker"
        in portal_config
    )
    assert "brick_guard_brick: guest_looking_glass_linux" in tasks
    assert graph["brick_requires"]["guest_looking_glass_linux"] == [
        "guest_desktop_hyprland"
    ]

    print("Linux Looking Glass experiment contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
