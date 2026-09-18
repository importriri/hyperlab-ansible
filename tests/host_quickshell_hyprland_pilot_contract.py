#!/usr/bin/env python3
"""Contract for the Hyprland-first HyperLab Quickshell pilot."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab Hyprland Quickshell pilot contract: {message}"
        )


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    shared = yaml.safe_load(
        text("group_vars/all/host-desktop.yml")
    )
    defaults = yaml.safe_load(
        text("roles/host_desktop_hyprland/defaults/main.yml")
    )

    stage = shared["host_desktop_common_shell_stage"]
    product = shared["host_desktop_common_product_contract"]

    require(
        product["shell"]["primary"] == "quickshell",
        "Quickshell stopped being the shared shell target",
    )
    require(
        product["shell"]["scope"] == "shared",
        "Quickshell became Hyprland-owned",
    )

    # The product-wide replacement gate remains closed. This milestone only
    # arms the already-shared shell inside the preferred Hyprland lifecycle.
    require(
        stage["runtime_enabled"] is False,
        "shared runtime gate was globally opened",
    )
    require(
        stage["replacement_enabled"] is False,
        "legacy recovery surfaces were globally replaced",
    )
    require(
        stage["waybar_fallback_required"] is True
        and stage["gtk_surface_fallback_required"] is True,
        "recovery surfaces stopped being mandatory",
    )

    services = defaults[
        "host_desktop_hyprland_session_services"
    ]

    require(
        services
        == [
            "hyperlab-hypridle.service",
            "hyperlab-hyprpaper.service",
            "hyperlab-mako.service",
            "hyperlab-quickshell.service",
        ],
        "managed Hyprland helper set changed unexpectedly",
    )

    service = text(
        "roles/host_desktop_hyprland/files/"
        "hyperlab-quickshell.service"
    )

    for marker in (
        "Description=HyperLab shared Quickshell presentation for Hyprland",
        "PartOf=hyperlab-hyprland-session.target",
        "After=graphical-session.target",
        "ExecStart=/usr/bin/qs -c hyperlab",
        "Restart=on-failure",
    ):
        require(
            marker in service,
            f"service marker missing: {marker}",
        )

    for forbidden in (
        "WantedBy=",
        "hyperlab-sway-session.target",
        "swaymsg",
        "hyprctl",
        "sudo",
        "pkexec",
        "/sys/",
    ):
        require(
            forbidden not in service,
            f"forbidden service behavior: {forbidden}",
        )

    root = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/shell.qml"
    )
    bar = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/HyperLabBar.qml"
    )

    require(
        "import Quickshell" in root
        and "HyperLabBar" in root,
        "shared shell root disappeared",
    )
    require(
        "PanelWindow" in bar
        and "implicitHeight: 37" in bar,
        "shared shell bar foundation changed",
    )

    # Shared QML remains compositor-neutral even though Hyprland is the
    # first compositor that will physically exercise it.
    combined = root + "\n" + bar

    # Human-facing compositor names are presentation text and are allowed.
    # What shared QML must never gain is compositor-specific API/import or
    # direct backend IPC.
    for forbidden in (
        "import Quickshell.Hyprland",
        "import Quickshell.I3",
        "Quickshell.Hyprland.",
        "Quickshell.I3.",
        "swaymsg",
        "hyprctl",
    ):
        require(
            forbidden not in combined,
            f"shared QML gained backend coupling: {forbidden}",
        )

    require(
        'text: "Hyprland · Sway"' in bar,
        "shared product presentation lost dual-compositor identity",
    )

    sway_role = ROOT / "roles/host_desktop_sway"

    require(
        not (
            sway_role
            / "files"
            / "hyperlab-quickshell.service"
        ).exists(),
        "pilot service leaked into Sway ownership",
    )

    print(
        "HyperLab Hyprland-first Quickshell pilot contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
