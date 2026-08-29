#!/usr/bin/env python3
"""Contract for English desktop controls, keyboard layouts and bar telemetry."""
from __future__ import annotations

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"desktop controls contract: {message}")


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def waybar() -> dict:
    source = re.sub(r"(?m)^\s*//.*$", "", text("roles/host_desktop_sway/files/waybar.jsonc"))
    return json.loads(source)


def main() -> int:
    bar = waybar()
    require(bar["modules-left"] == ["sway/workspaces", "custom/brand", "group/hyperlab", "sway/mode"],
            "Waybar left zone must mirror the definitive mockup order")
    require(bar["modules-center"] == ["clock"],
            "clock must remain the only centered Waybar module")
    require(bar["modules-right"] == ["group/telemetry", "group/session"],
            "Waybar right side must be telemetry followed by session controls")
    telemetry = bar["group/telemetry"]["modules"]
    session = bar["group/session"]["modules"]
    require(telemetry == ["temperature", "network", "pulseaudio", "battery"],
            "telemetry pod order changed")
    require(session == ["custom/keyboard-layout", "custom/wallpaper-mode", "custom/controls"],
            "session-control pod order changed")
    for module in (
        "temperature",
        "custom/keyboard-layout",
        "custom/wallpaper-mode",
        "custom/controls",
    ):
        require(module in telemetry + session, f"Waybar module missing: {module}")
    require(bar["temperature"]["format"] == " {temperatureC}°C",
            "CPU temperature format is not visible")
    require(bar["custom/keyboard-layout"]["signal"] == 10,
            "keyboard status signal changed")
    require(bar["custom/controls"]["signal"] == 11,
            "controls status signal changed")
    require(session.index("custom/wallpaper-mode") < session.index("custom/controls"),
            "Controls must remain the final, distinct session hit target")
    for mouse_action in ("on-click", "on-click-right"):
        require("--surface drawer" in bar["custom/brand"][mouse_action],
                f"brand {mouse_action} does not open the compact drawer")
    require("--surface overlay --section vms" in bar["custom/brand"]["on-click-middle"],
            "brand middle click does not open the full Control Center")

    defaults = yaml.safe_load(text("roles/host_desktop_sway/defaults/main.yml"))
    cycle = defaults["host_desktop_sway_input_defaults"]["keyboard_layout_cycle"]
    require(cycle == ["it", "us", "ara"], "keyboard cycle must be Italian, English, Arabic")
    require(defaults["host_desktop_sway_input_defaults"]["keyboard_layout"] == "it",
            "Italian must remain the default layout")
    require(defaults["host_desktop_sway_input_defaults"]["theme_cycle_binding"] is None,
            "generic hosts must not inherit the Nitro theme key")

    hardware = yaml.safe_load(text("group_vars/all/hardware.yml"))["host_profiles"]
    nitro_binding = hardware["nitro-3060"]["desktop"]["theme_cycle_binding"]
    require(nitro_binding == {
        "input_device": "1:1:AT_Translated_Set_2_keyboard",
        "keysym": "XF86Presentation",
    }, "Nitro theme key does not match the hardware gate")
    require("theme_cycle_binding" not in hardware["predator-3070"]["desktop"],
            "unverified Predator profile inherited the Nitro theme key")

    template = text("roles/host_desktop_sway/templates/sway-input.conf.j2")
    require("keyboard_layout_cycle | join(',')" in template,
            "Sway input template does not render the three-layout keymap")
    for marker in ("--no-repeat", "--input-device=", "theme_cycle_binding.keysym"):
        require(marker in template, f"hardware theme-key binding missing: {marker}")

    keyboard = text("roles/host_desktop_sway/files/privatestack-keyboard.sh")
    for marker in (
        "readonly layouts=(it us ara)",
        'xkb_layout "${layout}"',
        "status-json",
        "Keyboard layout:",
    ):
        require(marker in keyboard, f"keyboard controller missing: {marker}")

    controls = text("roles/host_desktop_sway/files/privatestack-controls.sh")
    for marker in (
        "Theme ·",
        "Wallpaper ·",
        "Keyboard ·",
        "Terminal opacity · Toggle",
        "Current window fullscreen · Toggle",
        "Bar visibility · Toggle",
        "HyperLab quick VM drawer",
        "HyperLab quick diagnostics",
        "HyperLab full Control Center",
    ):
        require(marker in controls, f"controls menu missing: {marker}")

    sway = text("roles/host_desktop_sway/files/sway.config")
    for marker in (
        "bindsym $mod+Ctrl+space exec /usr/local/bin/privatestack-keyboard cycle",
        "bindsym $mod+Shift+p exec $controls",
        "exec_always /usr/local/bin/privatestack-keyboard session-start",
    ):
        require(marker in sway, f"Sway integration missing: {marker}")
    require("bindsym $mod+Shift+k exec /usr/local/bin/privatestack-keyboard cycle" not in sway,
            "keyboard cycle still collides with the Vim-style move-up binding")
    require("unbindsym $mod+Shift+k" not in sway and "unbindsym $mod+Ctrl+k" not in sway,
            "Sway config uses failing unbind directives for bindings that do not exist")
    require("xkb_switch_layout" not in keyboard,
            "keyboard controller still depends on a fragile layout index")
    require("bindsym $mod+Shift+$up move up" in sway,
            "Vim-style move-up binding was removed instead of resolving the collision")
    require(
        "wpctl set-volume -l 1.25 @DEFAULT_AUDIO_SINK@ 5%+" in sway,
        "host volume-up must expose the reviewed 125 percent software ceiling",
    )
    require(
        '["wpctl", "set-volume", "-l", "1.25", "@DEFAULT_AUDIO_SINK@", "5%+"]'
        in text("roles/host_desktop_sway/files/privatestack-swaybar-status.py"),
        "Swaybar volume scroll must share the reviewed software ceiling",
    )
    require(
        '"max-volume": 125' in text("roles/host_desktop_sway/files/waybar.jsonc"),
        "Waybar volume scroll must expose the reviewed software ceiling",
    )

    for route in (
        "--surface drawer --section vms",
        "--surface drawer --section diagnostics",
        "--surface overlay --section vms",
    ):
        require(route in controls, f"controls menu route missing: {route}")

    fallback = text("roles/host_desktop_sway/files/privatestack-swaybar-status.py")
    for marker in ('block("keyboard"', 'block("controls"', 'block("temperature"'):
        require(marker in fallback, f"native Swaybar fallback missing: {marker}")

    for variant in ("green", "violet", "blue", "red"):
        lock = text(f"roles/host_desktop_sway/files/palette/{variant}/hyperlab-palette-swaylock.conf")
        require("\\n" not in lock, f"{variant} Swaylock theme contains literal newline escapes")
        require(lock.count("\n") > 20, f"{variant} Swaylock theme is not a real multi-line file")

    manager = text("roles/host_desktop_sway/files/privatestack-hyperlab-domains.py")
    require("Gtk.STYLE_PROVIDER_PRIORITY_USER + 1" in manager,
            "resident HyperLab surfaces cannot override the process-cached GTK user palette")
    for phrase in (
        "Machines",
        "Create",
        "Networks",
        "GPU",
        "GOLDEN IMAGE",
        "SPEC PREVIEW",
        "WHAT HAPPENS WHEN YOU CREATE",
    ):
        require(phrase in manager, f"definitive English mockup text missing: {phrase}")

    print("HyperLab desktop controls contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
