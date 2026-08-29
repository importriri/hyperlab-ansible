#!/usr/bin/env python3
import re
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
    assert defaults["guest_gpu_nvidia_drm_alias"] == (
        "/dev/dri/privatestack-nvidia"
    )
    assert "'hypervisor' not in group_names" in tasks_text
    assert "ansible_facts['virtualization_role'] == 'guest'" in tasks_text
    assert "No NVIDIA PCI function is visible inside this guest" in tasks_text
    assert tasks_text.index("Detect NVIDIA PCI functions") < tasks_text.index(
        "Install the official NVIDIA Wayland guest stack"
    )
    assert "/etc/modules-load.d/privatestack-nvidia.conf" in tasks_text
    assert "/etc/modprobe.d/privatestack-nvidia.conf" in tasks_text
    assert "/etc/modprobe.d/privatestack-nouveau.conf" in tasks_text
    assert "/etc/udev/rules.d/95-privatestack-nvidia-drm.rules" in (
        tasks_text
    )
    assert "brick_guard_brick: guest_gpu_nvidia" in tasks_text
    assert "/usr/bin/mkinitcpio" in handlers_text
    assert "-P" in handlers_text
    assert "Reload guest NVIDIA udev rules" in handlers_text
    assert "--subsystem-match=drm" in handlers_text
    assert "--action=change" in handlers_text

    drm_rule = (
        ROOT
        / "roles/guest_gpu_nvidia/templates/95-privatestack-nvidia-drm.rules.j2"
    ).read_text(encoding="utf-8")
    assert 'ENV{DEVTYPE}=="drm_minor"' in drm_rule
    assert 'KERNEL=="card[0-9]*"' in drm_rule
    assert 'KERNELS=="{{ guest_gpu_nvidia_drm_pci_address }}"' in (
        drm_rule
    )
    assert 'ATTRS{vendor}=="0x{{ guest_gpu_nvidia_vendor_id }}"' in (
        drm_rule
    )
    assert "guest_gpu_nvidia_drm_alias" in drm_rule
    assert 'TAG+="uaccess"' in drm_rule

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

    identify_task = by_name[
        "Identify the passed NVIDIA display controller"
    ]
    identify_expression = identify_task["ansible.builtin.set_fact"][
        "guest_gpu_nvidia_drm_pci_addresses"
    ]
    assert "03(?:00|02)" in identify_expression
    assert "guest_gpu_nvidia_vendor_id" in identify_expression
    assert "[.]" in identify_expression
    assert "[ ]+" in identify_expression
    assert "multiline=true" in identify_expression
    assert "ignorecase=true" in identify_expression

    pattern_literals = re.findall(r"'([^']*)'", identify_expression)
    assert pattern_literals == [
        "^([0-9a-f]{4}:[0-9a-f]{2}:[0-9a-f]{2}[.][0-7])",
        "[ ]+03(?:00|02):[ ]+",
        ":",
    ]
    display_pattern = re.compile(
        pattern_literals[0]
        + pattern_literals[1]
        + "10de"
        + pattern_literals[2],
        flags=re.MULTILINE | re.IGNORECASE,
    )
    lspci_fixture = "\n".join(
        [
            "0000:05:00.0 0300: 10de:2520 (rev a1)",
            "0000:06:00.0 0403: 10de:228e (rev a1)",
        ]
    )
    assert display_pattern.findall(lspci_fixture) == ["0000:05:00.0"]

    alias_task = by_name["Persist the passed NVIDIA DRM alias"]
    assert alias_task["ansible.builtin.template"]["src"] == (
        "95-privatestack-nvidia-drm.rules.j2"
    )
    assert alias_task["notify"] == [
        "Reload guest NVIDIA udev rules",
        "Retrigger the guest NVIDIA DRM device",
    ]

    verify_rule_task = by_name[
        "Verify the persistent NVIDIA DRM alias rule"
    ]
    assert verify_rule_task["ansible.builtin.command"]["argv"] == [
        "/usr/bin/udevadm",
        "verify",
        "/etc/udev/rules.d/95-privatestack-nvidia-drm.rules",
    ]
    assert verify_rule_task["when"] == "not ansible_check_mode"

    alias_assert = by_name[
        "Require the persistent alias to select the passed NVIDIA card"
    ]["ansible.builtin.assert"]["that"]
    assert any(
        "guest_gpu_nvidia_drm_alias_canonical.stdout" in item
        and "guest_gpu_nvidia_drm_by_path_canonical.stdout" in item
        for item in alias_assert
    )

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
