#!/usr/bin/env python3
"""Contract for Host Hyprland prerequisites and non-active config rendering."""

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
    hypr_idle = text(
        "roles/host_desktop_hyprland/templates/hypridle.conf.j2"
    )
    hypr_lock = text(
        "roles/host_desktop_hyprland/templates/hyprlock.conf.j2"
    )
    hypr_paper = text(
        "roles/host_desktop_hyprland/templates/hyprpaper.conf.j2"
    )
    adapter = text(
        "roles/host_desktop_common/files/"
        "privatestack-compositor-adapter.sh"
    )

    require(
        defaults["host_desktop_hyprland_phase"] == "prerequisites",
        "Host Hyprland phase is not prerequisite-only",
    )
    require(
        defaults["host_desktop_hyprland_runtime_enabled"] is False,
        "prerequisite phase unexpectedly enables Hyprland runtime",
    )
    require(
        defaults[
            "host_desktop_hyprland_session_activation_enabled"
        ]
        is False,
        "prerequisite phase unexpectedly activates a Hyprland session",
    )
    require(
        defaults["host_desktop_hyprland_manage_ly"] is False,
        "prerequisite phase unexpectedly manages Ly",
    )
    require(
        defaults["host_desktop_hyprland_preserve_sway_fallback"] is True,
        "Sway fallback is no longer mandatory",
    )
    require(
        defaults["host_desktop_hyprland_preserve_waybar_fallback"] is True,
        "Waybar fallback is no longer mandatory",
    )

    packages = defaults[
        "host_desktop_hyprland_prerequisite_packages"
    ]
    require(
        packages
        == [
            "hyprland",
            "hypridle",
            "hyprlock",
            "hyprpaper",
            "hyprshutdown",
            "hyprpolkitagent",
            "xdg-desktop-portal",
            "xdg-desktop-portal-hyprland",
            "xdg-desktop-portal-gtk",
        ],
        "official prerequisite package set changed",
    )
    require(
        "quickshell" not in packages,
        "Quickshell leaked into the prerequisite phase",
    )
    require(
        "uwsm" not in packages,
        "uwsm was selected before session lifecycle review",
    )

    prerequisite_paths = {
        item["path"]: item["executable"]
        for item in defaults[
            "host_desktop_hyprland_prerequisite_paths"
        ]
    }

    require(
        prerequisite_paths
        == {
            "/usr/bin/Hyprland": True,
            "/usr/bin/hyprctl": True,
            "/usr/bin/hypridle": True,
            "/usr/bin/hyprlock": True,
            "/usr/bin/hyprpaper": True,
            "/usr/bin/hyprshutdown": True,
            "/usr/lib/hyprpolkitagent/hyprpolkitagent": True,
            "/usr/lib/xdg-desktop-portal-hyprland": True,
            "/usr/share/wayland-sessions/hyprland.desktop": False,
            "/usr/share/hypr/hyprland.lua": False,
            (
                "/usr/share/xdg-desktop-portal/"
                "hyprland-portals.conf"
            ): False,
        },
        "package-owned prerequisite artifact contract changed",
    )

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
            (
                "prerequisite phase contains forbidden "
                f"mutation module: {marker}"
            ),
        )

    for marker in (
        "community.general.pacman:",
        "ansible.builtin.package_facts:",
        "ansible.builtin.stat:",
        "ansible.builtin.assert:",
    ):
        require(
            marker in tasks,
            f"prerequisite role missing required module: {marker}",
        )

    require(
        "host_desktop_hyprland_prerequisite_packages" in tasks,
        "package installation is not driven by reviewed defaults",
    )

    parsed_tasks = yaml.safe_load(tasks)

    live_verification_names = {
        "Read installed package facts after prerequisite installation",
        "Verify every Host Hyprland prerequisite package is installed",
        "Inspect package-owned Host Hyprland prerequisite artifacts",
        "Verify package-owned Host Hyprland prerequisite artifacts",
    }

    parsed_by_name = {
        item.get("name"): item
        for item in parsed_tasks
        if isinstance(item, dict)
    }

    require(
        live_verification_names <= parsed_by_name.keys(),
        "live prerequisite verification task set changed",
    )

    for name in sorted(live_verification_names):
        require(
            parsed_by_name[name].get("when")
            == "not ansible_check_mode",
            (
                "live prerequisite verification is not "
                f"check-mode guarded: {name}"
            ),
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
        "targeted prerequisite mount playbook is missing",
    )

    mount = yaml.safe_load(
        mount_path.read_text(encoding="utf-8")
    )

    require(
        len(mount) == 1
        and mount[0].get("hosts") == "hypervisor"
        and mount[0].get("become") is True,
        "prerequisite mount lost its privileged host-only boundary",
    )

    mount_roles = mount[0].get("roles", [])

    require(
        len(mount_roles) == 2
        and isinstance(mount_roles[0], dict)
        and mount_roles[0].get("role") == "brick_guard"
        and mount_roles[0].get("vars", {}).get(
            "brick_guard_brick"
        )
        == "host_desktop_hyprland"
        and mount_roles[1] == "host_desktop_hyprland",
        "prerequisite playbook lost its brick guard or role order",
    )


    for active_path in (
        "playbooks/foundation.yml",
        "playbooks/lab.yml",
        "playbooks/host-desktop-sway.yml",
    ):
        require(
            "host_desktop_hyprland" not in text(active_path),
            f"Hyprland prerequisite role leaked into active path: {active_path}",
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

    for template_name in (
        "hyprland.lua.j2",
        "hyprland-input.lua.j2",
        "hypridle.conf.j2",
        "hyprlock.conf.j2",
        "hyprpaper.conf.j2",
    ):
        require(
            (
                role
                / "templates"
                / template_name
            ).is_file(),
            f"non-active render candidate missing: {template_name}",
        )

    for marker in (
        "hl.monitor({",
        'output = ""',
        'mode = "preferred"',
        'position = "auto"',
        'scale = "auto"',
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

    require(
        'hl.on("hyprland.start"' not in hypr,
        "non-active candidate gained Hyprland startup actions",
    )

    for marker in (
        "HYPERLAB_NON_ACTIVE_RENDER: hyprpaper",
        "HYPERLAB_NON_ACTIVE_RENDER: hypridle",
        "HYPERLAB_NON_ACTIVE_RENDER: hyprpolkitagent",
    ):
        require(
            marker in hypr,
            f"non-active lifecycle marker missing: {marker}",
        )

    for marker in (
        "lock_cmd = /usr/local/bin/privatestack-lock",
        "timeout = 600",
        "timeout = 900",
        (
            "on-timeout = /usr/local/bin/"
            "privatestack-compositor-adapter dpms disable"
        ),
        (
            "on-resume = /usr/local/bin/"
            "privatestack-compositor-adapter dpms enable"
        ),
    ):
        require(
            marker in hypr_idle,
            f"hypridle render contract missing: {marker}",
        )

    require(
        "hyprctl" not in hypr_idle,
        "hypridle regained direct Hyprland IPC",
    )

    for marker in (
        "hide_cursor = true",
        "immediate_render = true",
        (
            "path = /usr/share/backgrounds/"
            "privatestack/lockscreen.png"
        ),
        "text = HyperLab host",
    ):
        require(
            marker in hypr_lock,
            f"hyprlock render contract missing: {marker}",
        )

    require(
        "swaylock" not in hypr_lock,
        "Hyprland lock candidate depends on swaylock",
    )

    require(
        "splash = false" in hypr_paper
        and "ipc = true" in hypr_paper,
        "hyprpaper IPC-only candidate changed",
    )
    require(
        "wallpaper {" not in hypr_paper
        and "preload =" not in hypr_paper,
        "hyprpaper candidate stole dynamic wallpaper policy",
    )

    theme_helper = text(
        "roles/host_desktop_sway/files/privatestack-theme.sh"
    )
    require(
        "hyperlab-palette-hyprland.lua" in theme_helper
        and "hyperlab_palette.lua" in theme_helper,
        "theme controller no longer publishes the active Hyprland palette",
    )

    sway_tasks = text(
        "roles/host_desktop_sway/tasks/main.yml"
    )
    require(
        (
            "dest: "
            "/usr/share/backgrounds/privatestack/lockscreen.png"
        )
        in sway_tasks,
        "Hyprlock candidate references an unmanaged lockscreen asset",
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
        adapter_contract["high_level_helpers_rewired"] is True,
        "accepted high-level helper rewire disappeared",
    )

    require(
        defaults["host_desktop_hyprland_compositor_coupled_helpers"] == [],
        "accepted helpers regained direct compositor coupling",
    )

    for marker in (
        "switchxkblayout",
        "hyprpaper",
        "hl.dsp.window.fullscreen",
        "hl.dsp.window.set_prop",
        "hl.dsp.dpms",
        "focused-window",
        "hyprshutdown",
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
        "/usr/local/bin/privatestack-lock",
        "HYPERLAB_QUICKSHELL_PHASE=2",
    ):
        require(
            marker in hypr,
            f"Hyprland parity marker missing: {marker}",
        )

    for boundary in (
        "keyboard-cycle",
        "machine-theme-key",
        "theme-cycle",
        "wallpaper-mode",
        "controls-menu",
        "opacity-toggle",
        "bar-toggle",
    ):
        require(
            f"HYPERLAB_PARITY_ADAPTER_READY: {boundary}"
            in hypr,
            f"accepted adapter route missing: {boundary}",
        )

    for boundary in (
        "wallpaper-daemon",
        "idle-dpms",
    ):
        require(
            f"HYPERLAB_PARITY_ADAPTER_REQUIRED: {boundary}"
            in hypr,
            f"pending runtime adapter gate disappeared: {boundary}",
        )

    # High-level policy helpers must no longer own compositor IPC.
    helper_sources = {
        "keyboard": text(
            "roles/host_desktop_sway/files/privatestack-keyboard.sh"
        ),
        "theme": text(
            "roles/host_desktop_sway/files/privatestack-theme.sh"
        ),
        "controls": text(
            "roles/host_desktop_sway/files/privatestack-controls.sh"
        ),
        "opacity": text(
            "roles/host_desktop_sway/files/privatestack-opacity-toggle.sh"
        ),
        "waybar": text(
            "roles/host_desktop_sway/files/privatestack-waybar.sh"
        ),
        "power": text(
            "roles/host_desktop_sway/files/privatestack-powermenu.sh"
        ),
    }

    for name, source in helper_sources.items():
        require(
            "swaymsg" not in source and "hyprctl" not in source,
            f"{name} regained direct compositor IPC",
        )

    legacy_lock = text(
        "roles/host_desktop_sway/files/privatestack-swaylock.sh"
    )
    generic_lock = text(
        "roles/host_desktop_sway/files/privatestack-lock.sh"
    )
    require(
        "privatestack-lock" in legacy_lock,
        "Sway lock compatibility route disappeared",
    )
    require(
        "swaylock" in generic_lock and "hyprlock" in generic_lock,
        "generic lock lost one compositor backend",
    )

    qml = list(role.rglob("*.qml"))
    require(
        not qml,
        "prerequisite phase unexpectedly contains Quickshell/QML",
    )

    print(
        "HyperLab host Hyprland Lua static parity contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
