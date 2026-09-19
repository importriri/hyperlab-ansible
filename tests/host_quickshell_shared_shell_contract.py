#!/usr/bin/env python3
"""Contract for the non-active shared HyperLab Quickshell foundation."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab shared shell contract: {message}"
        )


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    shared = yaml.safe_load(
        text("group_vars/all/host-desktop.yml")
    )

    product = shared["host_desktop_common_product_contract"]
    stage = shared["host_desktop_common_shell_stage"]

    require(
        product["supported_compositors"]
        == ["hyprland", "sway"],
        "shared shell lost one supported compositor",
    )
    require(
        product["shell"]["primary"] == "quickshell",
        "Quickshell is not the product shell target",
    )
    require(
        product["shell"]["scope"] == "shared",
        "shell became compositor-specific",
    )

    require(
        stage
        == {
            "implementation": "quickshell",
            "config_name": "hyperlab",
            "config_root": "/etc/xdg/quickshell/hyperlab",
            "package": "quickshell",
            "reviewed_api_series": "0.3",
            "runtime_enabled": False,
            "replacement_enabled": False,
            "waybar_fallback_required": True,
            "gtk_surface_fallback_required": True,
            "compositor_specific_imports_allowed": False,
        },
        "Phase 2A deployment contract changed",
    )

    shell = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/shell.qml"
    )
    bar = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/HyperLabBar.qml"
    )
    tasks = text(
        "roles/host_desktop_common/tasks/main.yml"
    )

    for marker in (
        "//@ pragma ShellId hyperlab",
        "import Quickshell",
        "ShellRoot",
        "Variants",
        "model: Quickshell.screens",
        "HyperLabBar",
    ):
        require(
            marker in shell,
            f"root shell marker missing: {marker}",
        )

    for marker in (
        "PanelWindow",
        "implicitHeight: 37",
        "exclusiveZone: 37",
        "top: true",
        "left: true",
        "right: true",
        'text: "HYPERLAB"',
        'text: "Hyprland · Sway"',
    ):
        require(
            marker in bar,
            f"shared bar foundation marker missing: {marker}",
        )

    require(
        "property var modelData" in bar,
        "Variants delegate lost its modelData injection property",
    )
    require(
        "required property var modelData" not in bar,
        (
            "Quickshell 0.3 runtime-incompatible required modelData "
            "contract returned"
        ),
    )

    combined = shell + "\n" + bar

    for forbidden in (
        "Quickshell.Hyprland",
        "Quickshell.I3",
        "hyprctl",
        "swaymsg",
        "execDetached",
        "Process {",
        "MouseArea",
        "TapHandler",
        "ShellCommand",
        '["sh", "-c"',
    ):
        require(
            forbidden not in combined,
            f"Phase 2A gained forbidden behavior: {forbidden}",
        )

    for marker in (
        "Install the reviewed shared Quickshell runtime",
        "Verify the reviewed Quickshell API series",
        "Create the shared HyperLab Quickshell config directory",
        "Install the non-active shared HyperLab Quickshell source",
        "Preserve recovery surfaces while Quickshell remains non-active",
        "community.general.pacman:",
        "/etc/xdg/quickshell/hyperlab",
    ):
        require(
            marker in tasks,
            f"common role deployment marker missing: {marker}",
        )

    for forbidden in (
        "systemctl --user enable quickshell",
        "systemctl --user start quickshell",
        "qs -c hyperlab",
        "quickshell -c hyperlab",
    ):
        require(
            forbidden not in tasks,
            f"non-active stage gained runtime activation: {forbidden}",
        )

    require(
        not list(
            (
                ROOT / "roles/host_desktop_hyprland"
            ).rglob("*.qml")
        ),
        "shared QML leaked into the Hyprland-specific role",
    )

    require(
        not list(
            (
                ROOT / "roles/host_desktop_sway"
            ).rglob("*.qml")
        ),
        "shared QML leaked into the Sway-specific role",
    )

    print(
        "HyperLab shared Quickshell Phase 2A contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
