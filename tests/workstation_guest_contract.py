#!/usr/bin/env python3
"""Host-independent contracts for the Arch Hyprland workstation roles."""
from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def mapping(relative: str) -> dict[str, object]:
    data = yaml.safe_load(text(relative))
    assert isinstance(data, dict), f"{relative} must contain a mapping"
    return data


def main() -> int:
    graph = mapping("group_vars/all/bricks.yml")
    requires = graph["brick_requires"]
    playbooks = graph["brick_playbooks"]

    assert requires["workstation_kernel"] == []
    assert requires["workstation_access"] == []
    assert requires["guest_desktop_hyprland"] == [
        "workstation_kernel",
        "workstation_access",
    ]
    assert requires["dev_ide"] == ["guest_desktop_hyprland"]
    assert playbooks["guest_desktop_hyprland"] == (
        "playbooks/guest-arch-hyprland.yml"
    )

    base_roles = yaml.safe_load(text("playbooks/guest-arch-hyprland.yml"))[0][
        "roles"
    ]
    dev_roles = yaml.safe_load(text("playbooks/guest-arch-dev.yml"))[0]["roles"]
    compat_roles = yaml.safe_load(text("playbooks/dev.yml"))[0]["roles"]
    assert base_roles == [
        "workstation_kernel",
        "workstation_access",
        "guest_desktop_hyprland",
    ]
    assert dev_roles == base_roles + ["dev_ide"]
    assert compat_roles == dev_roles

    access = text("roles/workstation_access/tasks/main.yml")
    assert "passwd" in access
    assert "workstation_access_password_hash_pattern" in access
    assert "^root (L|NP)( |$)" in access
    assert "brick_guard_brick: workstation_access" in access

    kernel = text("roles/workstation_kernel/tasks/arch-zen.yml")
    assert "/boot/vmlinuz-linux-zen" in kernel
    assert "'-zen' in ansible_facts['kernel']" in kernel
    assert "workstation_kernel_remove_fallback" in kernel

    kernel_tasks = yaml.safe_load(kernel)
    assert isinstance(kernel_tasks, list)

    kernel_task_names = [
        task.get("name")
        for task in kernel_tasks
        if isinstance(task, dict)
    ]

    sync_name = "Fully synchronize the Arch workstation package state"
    install_name = "Install the Zen kernel contract"

    assert sync_name in kernel_task_names
    assert install_name in kernel_task_names
    assert kernel_task_names.index(sync_name) < kernel_task_names.index(
        install_name
    )

    sync_task = next(
        task
        for task in kernel_tasks
        if isinstance(task, dict) and task.get("name") == sync_name
    )

    sync_pacman = sync_task["community.general.pacman"]
    assert sync_pacman["update_cache"] is True
    assert sync_pacman["upgrade"] is True
    assert (
        "workstation_kernel_system_upgrade.packages"
        in sync_task["changed_when"]
    )

    assert "brick_guard_brick: workstation_kernel" in text(
        "roles/workstation_kernel/tasks/main.yml"
    )

    defaults = mapping("roles/guest_desktop_hyprland/defaults/main.yml")
    themes = defaults["guest_desktop_hyprland_theme_order"]
    palettes = defaults["guest_desktop_hyprland_palettes"]
    assert themes == [
        "sakura-circuit",
        "neon-terminal",
        "moon-library",
        "glitch-lab",
    ]
    assert set(palettes) == set(themes)
    assert defaults["guest_desktop_hyprland_nvidia_only"] is False
    assert defaults["guest_desktop_hyprland_headless_monitor"] is False
    assert defaults["guest_desktop_hyprland_headless_output"] == "HEADLESS-0"
    assert defaults["guest_desktop_hyprland_headless_mode"] == "1920x1080@144"
    assert defaults["guest_desktop_hyprland_headless_position"] == "0x0"
    assert defaults["guest_desktop_hyprland_headless_scale"] == 1

    vfio_play = yaml.safe_load(
        text("playbooks/guest-arch-dev-vfio.yml")
    )[0]
    assert vfio_play["vars"]["guest_desktop_hyprland_nvidia_only"] is True
    assert (
        vfio_play["vars"]["guest_desktop_hyprland_headless_monitor"]
        is True
    )

    guest_tasks = text("roles/guest_desktop_hyprland/tasks/main.yml")
    assert "'workstations' in group_names" in guest_tasks
    assert "'hypervisor' not in group_names" in guest_tasks
    assert "Remove legacy Sway and host-only guest packages" in guest_tasks
    assert "brick_guard_brick: guest_desktop_hyprland" in guest_tasks

    hyprland = text(
        "roles/guest_desktop_hyprland/templates/hyprland.lua.j2"
    )
    assert "dwindle.pseudotile" not in hyprland
    assert '"pidof hyprlock || hyprlock"' in hyprland
    assert 'require("theme")' in hyprland
    assert "guest_desktop_hyprland_headless_monitor" in hyprland
    assert "guest_desktop_hyprland_headless_output" in hyprland
    assert "guest_desktop_hyprland_headless_mode" in hyprland
    assert "guest_desktop_hyprland_headless_position" in hyprland
    assert "guest_desktop_hyprland_headless_scale" in hyprland
    assert "hyprctl output create headless" in hyprland
    assert (
        "{% if guest_desktop_hyprland_headless_monitor %}"
        in hyprland
    )

    controller = text(
        "roles/guest_desktop_hyprland/files/privatestack-guest-theme.py"
    )
    assert "history_desktop = (" in controller
    assert "history_lock = (" in controller
    assert "if rotate" in controller
    assert "GUEST_THEME_READY" in controller

    desktop_pool = (
        "/usr/share/backgrounds/privatestack-guest/"
        "{{ item.0 }}/{{ item.1 }}/bootstrap.png"
    )
    assert desktop_pool in guest_tasks

    ide_defaults = mapping("roles/dev_ide/defaults/main.yml")
    assert "jdtls" not in ide_defaults["dev_ide_packages"]
    assert ide_defaults["dev_ide_jdtls_version"] == "1.60.0"
    assert ide_defaults["dev_ide_jdtls_build"] == "202606262232"
    jdtls = text("roles/dev_ide/tasks/jdtls.yml")
    assert 'checksum: "sha256:{{ dev_ide_jdtls_checksum_url }}"' in jdtls
    assert "dev_ide_java_specification.stdout | int >= 21" in jdtls
    assert "/usr/local/bin/jdtls" in jdtls

    print("workstation guest contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
