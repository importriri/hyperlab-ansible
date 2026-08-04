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
    source = re.sub(r"(?m)^\s*//.*$", "", text("roles/desktop/files/waybar.jsonc"))
    return json.loads(source)


def main() -> int:
    bar = waybar()
    right = bar["modules-right"]
    for module in (
        "temperature",
        "custom/keyboard-layout",
        "custom/wallpaper-mode",
        "custom/controls",
    ):
        require(module in right, f"Waybar module missing: {module}")
    require(bar["temperature"]["format"] == " {temperatureC}°C",
            "CPU temperature format is not visible")
    require(bar["custom/keyboard-layout"]["signal"] == 10,
            "keyboard status signal changed")
    require(bar["custom/controls"]["signal"] == 11,
            "controls status signal changed")
    require(right.index("custom/controls") < right.index("custom/wallpaper-mode"),
            "Controls must have a distinct hit target before wallpaper mode")
    for mouse_action in ("on-click", "on-click-right", "on-click-middle"):
        require("--surface drawer" in bar["custom/brand"][mouse_action],
                f"brand {mouse_action} does not open the compact drawer")
    require("--surface overlay" not in json.dumps(bar["custom/brand"]),
            "the Waybar brand still exposes the full center directly")

    defaults = yaml.safe_load(text("roles/desktop/defaults/main.yml"))
    cycle = defaults["desktop_input_defaults"]["keyboard_layout_cycle"]
    require(cycle == ["it", "us", "ara"], "keyboard cycle must be Italian, English, Arabic")
    require(defaults["desktop_input_defaults"]["keyboard_layout"] == "it",
            "Italian must remain the default layout")

    template = text("roles/desktop/templates/sway-input.conf.j2")
    require("keyboard_layout_cycle | join(',')" in template,
            "Sway input template does not render the three-layout keymap")

    keyboard = text("roles/desktop/files/privatestack-keyboard.sh")
    for marker in (
        "readonly layouts=(it us ara)",
        'xkb_layout "${layout}"',
        "status-json",
        "Keyboard layout:",
    ):
        require(marker in keyboard, f"keyboard controller missing: {marker}")

    controls = text("roles/desktop/files/privatestack-controls.sh")
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

    sway = text("roles/desktop/files/sway.config")
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

    for route in (
        "--surface drawer --section vms",
        "--surface drawer --section diagnostics",
        "--surface overlay --section vms",
    ):
        require(route in controls, f"controls menu route missing: {route}")

    fallback = text("roles/desktop/files/privatestack-swaybar-status.py")
    for marker in ('block("keyboard"', 'block("controls"', 'block("temperature"'):
        require(marker in fallback, f"native Swaybar fallback missing: {marker}")

    for variant in ("green", "violet", "blue", "red"):
        lock = text(f"roles/desktop/files/palette/{variant}/hyperlab-palette-swaylock.conf")
        require("\\n" not in lock, f"{variant} Swaylock theme contains literal newline escapes")
        require(lock.count("\n") > 20, f"{variant} Swaylock theme is not a real multi-line file")

    manager = text("roles/desktop/files/privatestack-hyperlab-domains.py")
    require("Gtk.STYLE_PROVIDER_PRIORITY_USER + 1" in manager,
            "resident HyperLab surfaces cannot override the process-cached GTK user palette")
    for phrase in (
        "Overview",
        "Ready images",
        "Manage VMs",
        "Review images",
        "Control Center session history",
        "Problems, providers and technical tools",
    ):
        require(phrase in manager, f"English control-plane text missing: {phrase}")

    print("HyperLab desktop controls contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
