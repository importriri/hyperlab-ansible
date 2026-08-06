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

    guest_tasks = text("roles/guest_desktop_hyprland/tasks/main.yml")
    assert "'workstations' in group_names" in guest_tasks
    assert "'hypervisor' not in group_names" in guest_tasks
    assert "Remove legacy Sway and host-only guest packages" in guest_tasks
    assert "brick_guard_brick: guest_desktop_hyprland" in guest_tasks

    hyprland = text("roles/guest_desktop_hyprland/files/hyprland.lua")
    assert "dwindle.pseudotile" not in hyprland
    assert '"pidof hyprlock || hyprlock"' in hyprland
    assert 'require("theme")' in hyprland

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
