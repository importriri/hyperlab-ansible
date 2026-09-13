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

    defaults = yaml.safe_load(
        text("roles/host_desktop_hyprland/defaults/main.yml")
    )
    tasks = text("roles/host_desktop_hyprland/tasks/main.yml")
    hypr = text(
        "roles/host_desktop_hyprland/templates/hyprland.lua.j2"
    )
    hypr_input = text(
        "roles/host_desktop_hyprland/templates/hyprland-input.lua.j2"
    )
    adapter = text(
        "roles/host_desktop_hyprland/files/"
        "privatestack-compositor-adapter.sh"
    )

    require(
        defaults["host_desktop_hyprland_phase"] == "static",
        "Phase 1 must remain static",
    )
    require(
        defaults["host_desktop_hyprland_runtime_enabled"] is False,
        "Phase 1 unexpectedly enables runtime integration",
    )
    require(
        defaults["host_desktop_hyprland_preserve_sway_fallback"] is True,
        "Sway fallback is no longer mandatory",
    )
    require(
        defaults["host_desktop_hyprland_preserve_waybar_fallback"] is True,
        "Waybar fallback is no longer mandatory",
    )

    packages = defaults["host_desktop_hyprland_future_packages"]
    for package in (
        "hyprland",
        "hypridle",
        "hyprlock",
        "hyprpaper",
        "hyprpolkitagent",
        "xdg-desktop-portal-hyprland",
        "waybar",
        "mako",
    ):
        require(package in packages, f"future package missing: {package}")

    input_defaults = defaults[
        "host_desktop_hyprland_input_defaults"
    ]
    require(
        input_defaults["keyboard_layout"] == "it",
        "Italian must remain the default keyboard layout",
    )
    require(
        input_defaults["keyboard_layout_cycle"] == ["it", "us", "ara"],
        "keyboard cycle changed",
    )

    trust = defaults["host_desktop_hyprland_trust_contract"]
    require(
        trust["owner"] == "host",
        "trust identity is not host-owned",
    )
    require(
        trust["guest_self_assignment"] is False,
        "guest trust self-assignment became possible",
    )
    require(
        {
            name: value["level"]
            for name, value in trust["classes"].items()
            if name != "services"
        }
        == {
            "clean": 3,
            "dev": 2,
            "dirty": 1,
            "lab": 0,
        },
        "trust rung map changed",
    )
    require(
        trust["classes"]["services"]["gpu_trust_rung"] is False,
        "services became a GPU trust rung",
    )
    require(
        trust["dirty_seamless_window_requires_host_badge"] is True,
        "dirty seamless windows lost host-owned identity",
    )

    shell = defaults["host_desktop_hyprland_shell_target"]
    require(
        shell["primary"] == "quickshell",
        "Quickshell is no longer the target shell",
    )
    require(
        shell["phase"] == 2,
        "Quickshell moved into Phase 1",
    )
    require(
        shell["fake_controls_allowed"] is False,
        "fake Quickshell controls became allowed",
    )
    require(
        shell["backend_authority"]
        == ["hyperlabctl", "specs", "contracts"],
        "presentation layer gained backend authority",
    )

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
        require(
            marker not in tasks,
            f"static role contains mutation module: {marker}",
        )

    require(
        "ansible.builtin.assert:" in tasks,
        "static role lost validation-only tasks",
    )

    bricks = yaml.safe_load(text("group_vars/all/bricks.yml"))

    require(
        bricks["brick_requires"]["host_desktop_hyprland"]
        == ["host_desktop_sway"],
        "migration brick prerequisite changed",
    )
    require(
        bricks["brick_playbooks"]["host_desktop_hyprland"]
        == "playbooks/host-desktop-hyprland.yml",
        "migration brick mount changed",
    )

    mount_path = ROOT / "playbooks/host-desktop-hyprland.yml"
    require(
        mount_path.is_file(),
        "contract-only mount playbook is missing",
    )

    mount = yaml.safe_load(
        mount_path.read_text(encoding="utf-8")
    )

    require(
        len(mount) == 1
        and mount[0].get("hosts") == "hypervisor"
        and mount[0].get("become") is False
        and mount[0].get("roles")
        == ["host_desktop_hyprland"],
        "Phase 1 mount is not contract-only",
    )

    for active_path in (
        "playbooks/foundation.yml",
        "playbooks/lab.yml",
        "playbooks/host-desktop-sway.yml",
    ):
        require(
            "host_desktop_hyprland" not in text(active_path),
            f"Phase 1 leaked into active path: {active_path}",
        )

    require(
        (ROOT / "roles/host_desktop_sway").is_dir(),
        "proven Sway role disappeared",
    )
    require(
        (ROOT / "playbooks/host-desktop-sway.yml").is_file(),
        "Sway recovery playbook disappeared",
    )

    # Hyprland 0.55+ primary configuration is Lua.
    require(
        not (
            role
            / "templates"
            / "hyprland.conf.j2"
        ).exists(),
        "deprecated host hyprlang config returned",
    )
    require(
        not (
            role
            / "templates"
            / "hyprland-input.conf.j2"
        ).exists(),
        "deprecated host hyprlang input returned",
    )

    for marker in (
        "hl.config({",
        "hl.bind(",
        "hl.dsp.exec_cmd(",
        "hl.dsp.window.fullscreen({",
        "hl.dsp.window.float({",
        "hl.dsp.focus({",
        "hl.dsp.window.move({",
        "hl.dsp.window.resize({",
        "hl.dsp.submap(",
        "hl.define_submap(",
    ):
        require(
            marker in hypr,
            f"current Hyprland Lua API marker missing: {marker}",
        )

    for old_syntax in (
        "bind = ",
        "bindel = ",
        "bindl = ",
        "source = ",
        "$mainMod",
    ):
        require(
            old_syntax not in hypr,
            f"deprecated hyprlang syntax remains: {old_syntax}",
        )

    for marker in (
        'local palette = require("hyperlab_palette")',
        "active_border = palette.active_border",
        "inactive_border = palette.inactive_border",
    ):
        require(
            marker in hypr,
            f"single-source Hyprland palette marker missing: {marker}",
        )

    adapter_contract = defaults[
        "host_desktop_hyprland_compositor_adapter"
    ]
    require(
        adapter_contract["api_version"] == 1,
        "compositor adapter API version changed",
    )
    require(
        adapter_contract["future_installed_path"]
        == "/usr/local/bin/privatestack-compositor-adapter",
        "future compositor adapter path changed",
    )
    require(
        adapter_contract["high_level_helpers_rewired"] is False,
        "high-level helpers were rewired before adapter acceptance",
    )

    coupled = set(
        defaults[
            "host_desktop_hyprland_compositor_coupled_helpers"
        ]
    )
    require(
        "privatestack-opacity-toggle" in coupled,
        "opacity helper coupling is no longer explicit",
    )

    for marker in (
        "switchxkblayout",
        "hyprpaper",
        "hl.dsp.window.fullscreen",
        "hl.dsp.window.set_prop",
        "hl.dsp.dpms",
    ):
        require(
            marker in adapter,
            f"compositor adapter primitive missing: {marker}",
        )

    require(
        'keyboard_layout = '
        '"{{ host_desktop_hyprland_input_defaults.'
        "keyboard_layout_cycle | join(',') }}\""
        in hypr_input,
        "input Lua module no longer renders the reviewed layout cycle",
    )

    for marker in (
        'for workspace = 1, 9 do',
        'main_mod .. " + " .. key',
        'main_mod .. " + SHIFT + " .. key',
        "hl.dsp.window.resize({",
        "/usr/local/bin/privatestack-hyperlab-domains ",
        "--surface drawer --section diagnostics",
        "--surface overlay --section vms",
        "hyperlabctl doctor",
        "hyperlabctl open looking-glass",
        "hyperlabctl open console",
        "wpctl set-volume -l 1.25",
        "@DEFAULT_AUDIO_SINK@ 5%+",
        "wpctl set-mute",
        "brightnessctl set +5%",
        "privatestack-screenshot full",
        "privatestack-screenshot region",
        "pidof hyprlock || hyprlock",
        "HYPERLAB_QUICKSHELL_PHASE=2",
    ):
        require(
            marker in hypr,
            f"Hyprland parity marker missing: {marker}",
        )

    for adapter in (
        "keyboard-cycle",
        "machine-theme-key",
        "theme-cycle",
        "wallpaper-mode",
        "wallpaper-daemon",
        "controls-menu",
        "opacity-toggle",
        "bar-toggle",
        "idle-dpms",
    ):
        require(
            f"HYPERLAB_PARITY_ADAPTER_REQUIRED: {adapter}"
            in hypr,
            f"missing adapter boundary: {adapter}",
        )

    # Existing helpers really are compositor-coupled where documented.
    keyboard = text(
        "roles/host_desktop_sway/files/"
        "privatestack-keyboard.sh"
    )
    theme = text(
        "roles/host_desktop_sway/files/"
        "privatestack-theme.sh"
    )
    controls = text(
        "roles/host_desktop_sway/files/"
        "privatestack-controls.sh"
    )
    opacity = text(
        "roles/host_desktop_sway/files/"
        "privatestack-opacity-toggle.sh"
    )
    waybar = text(
        "roles/host_desktop_sway/files/"
        "privatestack-waybar.sh"
    )
    screenshot = text(
        "roles/host_desktop_sway/files/"
        "privatestack-screenshot.sh"
    )

    require(
        "swaymsg" in keyboard,
        "keyboard helper coupling changed",
    )
    require(
        "swaymsg" in theme and "SWAYSOCK" in theme,
        "theme helper coupling changed",
    )
    require(
        "swaymsg" in controls,
        "controls helper coupling changed",
    )
    require(
        "swaymsg" in opacity,
        "opacity helper coupling changed",
    )
    require(
        "swaymsg" in waybar,
        "Waybar supervisor coupling changed",
    )

    require(
        "swaymsg" not in screenshot
        and "SWAYSOCK" not in screenshot,
        "screenshot helper unexpectedly became compositor-coupled",
    )

    qml = list(role.rglob("*.qml"))
    require(
        not qml,
        "Phase 1 unexpectedly contains Quickshell/QML",
    )

    print(
        "HyperLab host Hyprland Lua static parity contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
