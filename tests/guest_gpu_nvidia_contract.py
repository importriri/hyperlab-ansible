#!/usr/bin/env python3
"""Static contract for the opt-in NVIDIA VFIO guest driver brick."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    defaults = yaml.safe_load(
        (ROOT / "roles/guest_gpu_nvidia/defaults/main.yml").read_text()
    )
    tasks = (ROOT / "roles/guest_gpu_nvidia/tasks/main.yml").read_text()
    handlers = (ROOT / "roles/guest_gpu_nvidia/handlers/main.yml").read_text()
    graph = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text())

    assert defaults["guest_gpu_nvidia_probe_packages"] == ["pciutils"]
    assert defaults["guest_gpu_nvidia_packages"] == [
        "nvidia-open-dkms",
        "nvidia-utils",
        "nvidia-settings",
        "egl-wayland",
        "vulkan-icd-loader",
    ]
    assert defaults["guest_gpu_nvidia_modules"] == [
        "nvidia",
        "nvidia_modeset",
        "nvidia_uvm",
        "nvidia_drm",
    ]
    assert "'hypervisor' not in group_names" in tasks
    assert "ansible_facts['virtualization_role'] == 'guest'" in tasks
    assert "No NVIDIA PCI function is visible inside this guest" in tasks
    assert tasks.index("Detect NVIDIA PCI functions") < tasks.index(
        "Install the official NVIDIA Wayland guest stack"
    )
    assert "/etc/modules-load.d/privatestack-nvidia.conf" in tasks
    assert "/etc/modprobe.d/privatestack-nvidia.conf" in tasks
    assert "/etc/modprobe.d/privatestack-nouveau.conf" in tasks
    assert "brick_guard_brick: guest_gpu_nvidia" in tasks
    assert "/usr/bin/mkinitcpio" in handlers and "-P" in handlers

    nvidia_options = (
        ROOT / "roles/guest_gpu_nvidia/files/privatestack-nvidia.conf"
    ).read_text()
    nouveau_options = (
        ROOT / "roles/guest_gpu_nvidia/files/privatestack-nouveau.conf"
    ).read_text()
    assert "modeset=1" in nvidia_options and "fbdev=1" in nvidia_options
    assert "blacklist nouveau" in nouveau_options

    assert graph["brick_requires"]["guest_gpu_nvidia"] == [
        "guest_desktop_hyprland"
    ]
    assert graph["brick_playbooks"]["guest_gpu_nvidia"] == (
        "playbooks/guest-gpu-nvidia.yml"
    )

    vfio_roles = yaml.safe_load(
        (ROOT / "playbooks/guest-arch-dev-vfio.yml").read_text()
    )[0]["roles"]
    assert vfio_roles == [
        "workstation_kernel",
        "workstation_access",
        "guest_desktop_hyprland",
        "dev_ide",
        "guest_gpu_nvidia",
    ]

    print("guest NVIDIA contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
