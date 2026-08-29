#!/usr/bin/env python3
"""Lock the native shell to the approved HyperLab definitive mockup."""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py"
WAYBAR = ROOT / "roles/host_desktop_sway/files/waybar.jsonc"
WAYBAR_CSS = ROOT / "roles/host_desktop_sway/files/waybar.css"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    manager = MANAGER.read_text(encoding="utf-8")
    waybar_source = re.sub(r"(?m)^\s*//.*$", "", WAYBAR.read_text(encoding="utf-8"))
    waybar = json.loads(waybar_source)
    waybar_css = WAYBAR_CSS.read_text(encoding="utf-8")

    for marker in (
        "panel.set_size_request(500, 560)",
        "panel.set_size_request(1180, 760)",
        "rail.set_size_request(170, -1)",
        "self.inspect_holder.set_size_request(300, -1)",
        "panel.set_margin_top(40)",
    ):
        require(marker in manager, f"mockup geometry drifted: {marker}")

    navigation = manager.split("navigation = [", 1)[1].split("]", 1)[0]
    for marker in (
        '("vms", "Machines")',
        '("create", "Create")',
        '("policies", "Networks")',
        '("gpu", "GPU")',
    ):
        require(marker in navigation, f"visible rail item missing: {marker}")
    for stale in ("Overview", "Trust domains", "Images", "Activity", "Diagnostics"):
        require(stale not in navigation, f"legacy visible rail item returned: {stale}")

    require(
        'content.append(self._build_vm_showcase(columns=2, compact=True))' in manager,
        "drawer no longer uses the two-column machine showcase",
    )
    require(
        "showcase = self._build_vm_showcase(columns=4)" in manager,
        "Control Center no longer uses the four-column machine showcase",
    )
    require(
        'self.inspect_holder.set_visible(section != "policies")' in manager
        and 'canvas.add_css_class("network-canvas")' in manager
        and 'dock.add_css_class("network-dock")' in manager,
        "Networks inspector is no longer docked below the full-width graph",
    )

    domain_colors = {
        "clean": "#72f2a5",
        "dev": "#5b8cff",
        "services": "#35e4dd",
        "dirty": "#ff9d45",
        "lab": "#b184ff",
    }
    for theme in ("green", "violet", "blue", "red"):
        palette = (
            Path(__file__).resolve().parents[1]
            / "roles/host_desktop_sway/files/palette"
            / theme
            / "hyperlab-palette-gtk.css"
        ).read_text(encoding="utf-8")
        for domain_id, color in domain_colors.items():
            marker = "@define-color hl_dom_%s %s;" % (domain_id, color)
            require(
                marker in palette,
                "immutable %s trust color drifted in %s palette"
                % (domain_id, theme),
            )
    for domain_id, color in domain_colors.items():
        cube = (
            Path(__file__).resolve().parents[1]
            / "roles/host_desktop_sway/files"
            / ("domain-%s.svg" % domain_id)
        ).read_text(encoding="utf-8")
        require(
            color in cube,
            "immutable %s trust color drifted in domain cube" % domain_id,
        )

    require(waybar["height"] == 37, "Waybar must remain exactly 37 px")
    require(
        waybar["modules-left"]
        == ["sway/workspaces", "custom/brand", "group/hyperlab", "sway/mode"],
        "Waybar left-zone order drifted from the definitive mockup",
    )
    require(waybar["modules-center"] == ["clock"], "clock lost the exact center")
    require(
        waybar["modules-right"] == ["group/telemetry", "group/session"],
        "Waybar right-zone pods drifted",
    )
    for marker in (
        'font-family: "Inter", "Adwaita Sans", "Cantarell", sans-serif',
        "#workspaces",
        "#custom-brand",
        "#hyperlab",
        "#clock",
        "#telemetry",
        "#session",
    ):
        require(marker in waybar_css, f"Waybar mockup token missing: {marker}")

    require("shell=True" not in manager and "os.system" not in manager, "shell boundary regressed")
    print("definitive HyperLab mockup geometry contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
