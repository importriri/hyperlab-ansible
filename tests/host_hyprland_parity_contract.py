#!/usr/bin/env python3
"""Static contract for the non-active physical-host Hyprland migration."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"host Hyprland parity contract: {message}")


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def main() -> int:
    role = ROOT / "roles/host_desktop_hyprland"
    require(role.is_dir(), "host_desktop_hyprland role is missing")

    defaults = yaml.safe_load(text("roles/host_desktop_hyprland/defaults/main.yml"))
    tasks = text("roles/host_desktop_hyprland/tasks/main.yml")
    hypr = text("roles/host_desktop_hyprland/templates/hyprland.conf.j2")
    hypr_input = text(
        "roles/host_desktop_hyprland/templates/hyprland-input.conf.j2"
    )

    require(defaults["host_desktop_hyprland_phase"] == "static",
            "Phase 1 must remain static")
    require(defaults["host_desktop_hyprland_runtime_enabled"] is False,
            "Phase 1 unexpectedly enables runtime integration")
    require(defaults["host_desktop_hyprland_preserve_sway_fallback"] is True,
            "Sway fallback is no longer mandatory")
    require(defaults["host_desktop_hyprland_preserve_waybar_fallback"] is True,
            "Waybar fallback is no longer mandatory")

    packages = defaults["host_desktop_hyprland_future_packages"]
    for package in (
        "hyprland",
        "hypridle",
        "hyprlock",
        "hyprpolkitagent",
        "xdg-desktop-portal-hyprland",
        "waybar",
        "mako",
    ):
        require(package in packages, f"future package missing: {package}")

    input_defaults = defaults["host_desktop_hyprland_input_defaults"]
    require(input_defaults["keyboard_layout"] == "it",
            "Italian must remain the default keyboard layout")
    require(input_defaults["keyboard_layout_cycle"] == ["it", "us", "ara"],
            "keyboard cycle changed")

    trust = defaults["host_desktop_hyprland_trust_contract"]
    require(trust["owner"] == "host", "trust identity is not host-owned")
    require(trust["guest_self_assignment"] is False,
            "guest trust self-assignment became possible")
    require(
        {
            name: value["level"]
            for name, value in trust["classes"].items()
            if name != "services"
        }
        == {"clean": 3, "dev": 2, "dirty": 1, "lab": 0},
        "trust rung map changed",
    )
    require(trust["classes"]["services"]["gpu_trust_rung"] is False,
            "services became a GPU trust rung")
    require(trust["dirty_seamless_window_requires_host_badge"] is True,
            "dirty seamless windows lost the host-owned identity requirement")

    shell = defaults["host_desktop_hyprland_shell_target"]
    require(shell["primary"] == "quickshell",
            "Quickshell is no longer the target host shell")
    require(shell["phase"] == 2,
            "Quickshell moved into the static Phase 1 unexpectedly")
    require(shell["fake_controls_allowed"] is False,
            "fake Quickshell controls became allowed")
    require(shell["backend_authority"] == ["hyperlabctl", "specs", "contracts"],
            "presentation layer gained backend authority")

    # A Phase 1 role must be safe even if somebody includes it accidentally:
    # assertions only, no package installation, file writes or service changes.
    forbidden_task_modules = (
        "community.general.pacman:",
        "ansible.builtin.copy:",
        "ansible.builtin.template:",
        "ansible.builtin.file:",
        "ansible.builtin.lineinfile:",
        "ansible.builtin.systemd_service:",
        "ansible.builtin.command:",
        "ansible.builtin.shell:",
    )
    for marker in forbidden_task_modules:
        require(marker not in tasks, f"static role contains mutation module: {marker}")
    require("ansible.builtin.assert:" in tasks,
            "static role lost its validation-only tasks")

    # Repository policy requires every role brick to exist in the dependency
    # graph and to name its narrowest mounting playbook. The Phase 1 mount is
    # contract-only and is not part of foundation.yml or lab.yml.
    bricks = yaml.safe_load(text("group_vars/all/bricks.yml"))
    require(
        bricks["brick_requires"]["host_desktop_hyprland"]
        == ["host_desktop_sway"],
        "Phase 1 must preserve the proven Sway cockpit as its prerequisite",
    )
    require(
        bricks["brick_playbooks"]["host_desktop_hyprland"]
        == "playbooks/host-desktop-hyprland.yml",
        "Phase 1 brick must name its dedicated contract-only mount",
    )

    mount_path = ROOT / "playbooks/host-desktop-hyprland.yml"
    require(mount_path.is_file(), "contract-only mount playbook is missing")

    mount = yaml.safe_load(mount_path.read_text(encoding="utf-8"))
    require(
        len(mount) == 1
        and mount[0].get("hosts") == "hypervisor"
        and mount[0].get("become") is False
        and mount[0].get("roles") == ["host_desktop_hyprland"],
        "Phase 1 mount must contain only the static host contract role",
    )

    for active_path in (
        "playbooks/foundation.yml",
        "playbooks/lab.yml",
        "playbooks/host-desktop-sway.yml",
    ):
        require(
            "host_desktop_hyprland" not in text(active_path),
            f"Phase 1 role leaked into active path: {active_path}",
        )

    # Proven Sway recovery surface remains checked in.
    require((ROOT / "roles/host_desktop_sway").is_dir(),
            "proven Sway role disappeared")
    require((ROOT / "playbooks/host-desktop-sway.yml").is_file(),
            "Sway recovery playbook disappeared")

    # The new role must not execute Sway IPC. Comments are allowed to name
    # the old coupling because they document exactly why an adapter is needed.
    def uncommented(source: str) -> str:
        return "\n".join(
            line
            for line in source.splitlines()
            if not line.lstrip().startswith("#")
        )

    executable_role_text = "\n".join(
        (
            defaults.__repr__(),
            uncommented(tasks),
            uncommented(hypr),
            uncommented(hypr_input),
        )
    )
    for forbidden in ("swaymsg", "SWAYSOCK", "xdg-desktop-portal-wlr"):
        require(
            forbidden not in executable_role_text,
            f"new Hyprland role executes Sway coupling: {forbidden}",
        )

    for marker in (
        "bind = $mainMod, 1, workspace, 1",
        "bind = $mainMod SHIFT, 9, movetoworkspace, 9",
        "movefocus",
        "movewindow",
        "resizeactive",
        "fullscreen, 0",
        "togglefloating",
        "privatestack-hyperlab-domains --surface drawer --section vms",
        "privatestack-hyperlab-domains --surface drawer --section diagnostics",
        "privatestack-hyperlab-domains --surface overlay --section vms",
        "hyperlabctl doctor",
        "hyperlabctl open looking-glass",
        "hyperlabctl open console",
        "wpctl set-volume -l 1.25 @DEFAULT_AUDIO_SINK@ 5%+",
        "wpctl set-mute @DEFAULT_AUDIO_SINK@ toggle",
        "brightnessctl set +5%",
        "privatestack-screenshot full",
        "privatestack-screenshot region",
        "exec, hyprlock",
        "HYPERLAB_QUICKSHELL_PHASE=2",
    ):
        require(marker in hypr, f"Hyprland parity marker missing: {marker}")

    for adapter in (
        "keyboard-cycle",
        "machine-theme-key",
        "theme-cycle",
        "wallpaper-mode",
        "wallpaper-daemon",
        "controls-menu",
        "bar-toggle",
    ):
        require(
            f"HYPERLAB_PARITY_ADAPTER_REQUIRED: {adapter}" in hypr
            or f"HYPERLAB_PARITY_ADAPTER_REQUIRED: {adapter}" in hypr_input,
            f"missing explicit compositor-adapter boundary: {adapter}",
        )

    # Existing implementations really are Sway-coupled. This guards against
    # silently pretending those helpers can be reused unchanged.
    keyboard = text(
        "roles/host_desktop_sway/files/privatestack-keyboard.sh"
    )
    theme = text("roles/host_desktop_sway/files/privatestack-theme.sh")
    controls = text("roles/host_desktop_sway/files/privatestack-controls.sh")
    require("swaymsg" in keyboard,
            "keyboard helper is no longer demonstrably Sway-coupled")
    require("swaymsg" in theme and "SWAYSOCK" in theme,
            "theme helper coupling changed; review adapter boundary")
    require("swaymsg" in controls,
            "controls helper coupling changed; review adapter boundary")

    # Quickshell is Phase 2 and therefore absent from the implementation tree.
    qml = list(role.rglob("*.qml"))
    require(not qml, "Phase 1 unexpectedly contains Quickshell/QML payload")

    print("HyperLab host Hyprland static parity contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
