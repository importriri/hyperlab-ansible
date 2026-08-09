#!/usr/bin/env python3
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load(relative: str):
    return yaml.safe_load(
        (ROOT / relative).read_text(encoding="utf-8")
    )


def main() -> None:
    defaults = load("roles/guest_gpu_nvidia/defaults/main.yml")
    tasks = load("roles/guest_gpu_nvidia/tasks/main.yml")
    tasks_text = (
        ROOT / "roles/guest_gpu_nvidia/tasks/main.yml"
    ).read_text(encoding="utf-8")
    handlers_text = (
        ROOT / "roles/guest_gpu_nvidia/handlers/main.yml"
    ).read_text(encoding="utf-8")
    graph = load("group_vars/all/bricks.yml")

    assert defaults["guest_gpu_nvidia_packages"] == [
        "nvidia-open-dkms",
        "nvidia-utils",
        "nvidia-settings",
        "egl-wayland",
        "vulkan-icd-loader",
    ]

    assert defaults["guest_gpu_nvidia_probe_packages"] == ["pciutils"]
    assert defaults["guest_gpu_nvidia_modules"] == [
        "nvidia",
        "nvidia_modeset",
        "nvidia_uvm",
        "nvidia_drm",
    ]
    assert "'hypervisor' not in group_names" in tasks_text
    assert "ansible_facts['virtualization_role'] == 'guest'" in tasks_text
    assert "No NVIDIA PCI function is visible inside this guest" in tasks_text
    assert tasks_text.index("Detect NVIDIA PCI functions") < tasks_text.index(
        "Install the official NVIDIA Wayland guest stack"
    )
    assert "/etc/modules-load.d/privatestack-nvidia.conf" in tasks_text
    assert "/etc/modprobe.d/privatestack-nvidia.conf" in tasks_text
    assert "/etc/modprobe.d/privatestack-nouveau.conf" in tasks_text
    assert "brick_guard_brick: guest_gpu_nvidia" in tasks_text
    assert "/usr/bin/mkinitcpio" in handlers_text
    assert "-P" in handlers_text

    nvidia_options = (
        ROOT / "roles/guest_gpu_nvidia/files/privatestack-nvidia.conf"
    ).read_text(encoding="utf-8")
    nouveau_options = (
        ROOT / "roles/guest_gpu_nvidia/files/privatestack-nouveau.conf"
    ).read_text(encoding="utf-8")
    assert "modeset=1" in nvidia_options
    assert "fbdev=1" in nvidia_options
    assert "blacklist nouveau" in nouveau_options

    assert graph["brick_requires"]["guest_gpu_nvidia"] == [
        "guest_desktop_hyprland"
    ]
    assert graph["brick_playbooks"]["guest_gpu_nvidia"] == (
        "playbooks/guest-gpu-nvidia.yml"
    )

    vfio_roles = load("playbooks/guest-arch-dev-vfio.yml")[0]["roles"]
    assert vfio_roles[:5] == [
        "workstation_kernel",
        "workstation_access",
        "guest_desktop_hyprland",
        "dev_ide",
        "guest_gpu_nvidia",
    ]
    assert vfio_roles[5] == {
        "role": "guest_looking_glass_linux",
        "vars": {"guest_looking_glass_linux_experimental": True},
    }

    by_name = {
        task.get("name"): task
        for task in tasks
        if isinstance(task, dict)
    }

    module_task = by_name[
        "Load the NVIDIA module set at guest boot"
    ]
    module_content = module_task["ansible.builtin.copy"]["content"]

    assert "{% for module in guest_gpu_nvidia_modules" in module_content
    assert "{{ module }}" in module_content
    assert "join(" not in module_content

    resolve_task = by_name[
        "Resolve the built NVIDIA kernel module path"
    ]
    argv = resolve_task["ansible.builtin.command"]["argv"]

    assert argv[:2] == ["/usr/bin/readlink", "-f"]
    assert "guest_gpu_nvidia_modinfo.stdout" in argv[2]

    verify_task = by_name[
        "Require the built NVIDIA module to belong to the running kernel"
    ]
    assertions = verify_task["ansible.builtin.assert"]["that"]

    assert any(
        "guest_gpu_nvidia_modinfo_canonical.stdout" in item
        and "^/usr/lib/modules/" in item
        for item in assertions
    )

    print("guest NVIDIA contract: OK")


if __name__ == "__main__":
    main()
