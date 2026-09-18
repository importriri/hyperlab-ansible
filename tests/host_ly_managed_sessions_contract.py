#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TASKS = (
    ROOT
    / "roles"
    / "host_desktop_hyprland"
    / "tasks"
    / "main.yml"
)

FILES = (
    ROOT
    / "roles"
    / "host_desktop_hyprland"
    / "files"
)

HYPR = FILES / "hyperlab-hyprland.desktop"
SWAY = FILES / "hyperlab-sway.desktop"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


tasks = TASKS.read_text(encoding="utf-8")
hypr = HYPR.read_text(encoding="utf-8")
sway = SWAY.read_text(encoding="utf-8")

for marker in (
    "Create the private HyperLab Ly session catalog",
    "/etc/ly/hyperlab-sessions",
    (
        "Install only managed HyperLab sessions "
        "into the Ly catalog"
    ),
    (
        "Restrict Ly discovery to the managed "
        "HyperLab session catalog"
    ),
    'key: custom_sessions, value: "/etc/ly/hyperlab-sessions"',
    'key: waylandsessions, value: "null"',
    'key: xsessions, value: "null"',
    'key: xinitrc, value: "null"',
    'key: shell, value: "false"',
):
    require(
        marker in tasks,
        f"Ly managed-session contract missing: {marker}",
    )

require(
    "Name=HyperLab Hyprland" in hypr,
    "managed Hyprland session has wrong visible name",
)

require(
    (
        "Exec=/usr/local/bin/"
        "privatestack-session-lifecycle launch hyprland"
    )
    in hypr,
    "managed Hyprland session bypasses lifecycle controller",
)

require(
    "Name=HyperLab Sway" in sway,
    "managed Sway session has wrong visible name",
)

require(
    (
        "Exec=/usr/local/bin/"
        "privatestack-session-lifecycle launch sway"
    )
    in sway,
    "managed Sway session bypasses lifecycle controller",
)

print("HyperLab Ly managed-session catalog contract: OK")
