#!/usr/bin/env python3
"""Contract for shared workspace state and semantic Quickshell theming."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

SURFACE_TOKENS = {
    "base",
    "mantle",
    "surface",
    "overlay",
    "text",
    "subtext",
    "accent",
    "accent2",
    "ok",
    "warn",
    "bad",
    "dom_clean",
    "dom_dev",
    "dom_lab",
    "dom_dirty",
    "dom_services",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            "HyperLab Quickshell workspace/theme contract: "
            + message
        )


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    shared = yaml.safe_load(
        text("group_vars/all/host-desktop.yml")
    )
    stage = shared["host_desktop_common_shell_stage"]

    require(
        stage["workspace_state_enabled"] is True,
        "workspace state gate is not enabled",
    )
    require(
        stage["workspace_state_bridge"]
        == "/usr/local/bin/privatestack-compositor-adapter",
        "workspace state escaped the compositor adapter",
    )
    require(
        stage["workspace_update_transport"]
        == "event-stream",
        "workspace state is not event-driven",
    )
    require(
        stage["semantic_palette_enabled"] is True,
        "semantic palette is not enabled",
    )
    require(
        stage["semantic_palette_user_path"]
        == ".config/hyperlab/palette-quickshell.json",
        "semantic palette path changed",
    )

    adapter = text(
        "roles/host_desktop_common/files/"
        "privatestack-compositor-adapter.sh"
    )

    for marker in (
        "workspaces-json",
        "workspace-watch",
        "workspace_snapshot_sway",
        "workspace_snapshot_hyprland",
        "workspace_watch_sway",
        "workspace_watch_hyprland",
        "get_workspaces",
        "activeworkspace -j",
        ".socket2.sock",
    ):
        require(
            marker in adapter,
            f"workspace adapter marker missing: {marker}",
        )

    for forbidden in (
        "sudo ",
        "pkexec",
        "/sys/",
    ):
        require(
            forbidden not in adapter,
            f"workspace adapter gained privilege surface: {forbidden}",
        )

    renderer = text("tools/palette/render_palette.py")

    require(
        "hyperlab-palette-quickshell.json" in renderer
        and "quickshell_json" in renderer,
        "palette renderer does not own Quickshell output",
    )

    defaults = text(
        "roles/host_desktop_sway/defaults/main.yml"
    )
    palette_tasks = text(
        "roles/host_desktop_sway/tasks/palette.yml"
    )
    theme = text(
        "roles/host_desktop_sway/files/privatestack-theme.sh"
    )

    require(
        "hyperlab-palette-quickshell.json" in defaults,
        "Quickshell palette is absent from runtime fragments",
    )
    require(
        "hyperlab/palette-quickshell.json" in palette_tasks,
        "active Quickshell palette is not deployed",
    )
    require(
        'palette-quickshell.json"' in theme,
        "theme switch does not publish the Quickshell palette",
    )

    domain_contract = None

    for variant in ("green", "violet", "blue", "red"):
        path = (
            ROOT
            / "roles/host_desktop_sway/files/palette"
            / variant
            / "hyperlab-palette-quickshell.json"
        )

        require(
            path.is_file(),
            f"Quickshell palette missing: {variant}",
        )

        payload = json.loads(
            path.read_text(encoding="utf-8")
        )

        require(
            payload.get("name") == variant,
            f"palette identity mismatch: {variant}",
        )

        require(
            set(payload)
            == SURFACE_TOKENS | {"name"},
            f"palette token set drifted: {variant}",
        )

        domains = {
            key: payload[key]
            for key in payload
            if key.startswith("dom_")
        }

        if domain_contract is None:
            domain_contract = domains
        else:
            require(
                domains == domain_contract,
                (
                    "theme variant redefined semantic "
                    f"domain identity: {variant}"
                ),
            )

    bar = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/HyperLabBar.qml"
    )

    for marker in (
        "FileView {",
        "watchChanges: true",
        "palette-quickshell.json",
        "HyperLab palette loaded:",
        '"workspace-watch"',
        "workspacePayload",
        "Repeater {",
        "model: 9",
        "workspaceNumber: index + 1",
        "root.palette.accent",
        "root.palette.surface",
        "root.palette.overlay",
        "root.palette.text",
        "root.palette.subtext",
        "semanticStatusColor",
    ):
        require(
            marker in bar,
            f"QML workspace/theme marker missing: {marker}",
        )

    require(
        not re.search(r"#[0-9a-fA-F]{6}", bar),
        "shared QML duplicated a palette colour literal",
    )

    for forbidden in (
        "Quickshell.Hyprland",
        "Quickshell.I3",
        "hyprctl",
        "swaymsg",
        "sudo",
        "pkexec",
        "/sys/",
        "MouseArea",
    ):
        require(
            forbidden not in bar,
            f"shared QML crossed backend boundary: {forbidden}",
        )

    print(
        "HyperLab shared Quickshell workspace/theme contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
