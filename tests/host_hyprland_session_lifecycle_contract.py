#!/usr/bin/env python3
"""Contract for staged physical-host compositor session lifecycle."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"host Hyprland session lifecycle contract: {message}"
        )


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    defaults = yaml.safe_load(
        text("roles/host_desktop_hyprland/defaults/main.yml")
    )
    tasks = yaml.safe_load(
        text("roles/host_desktop_hyprland/tasks/main.yml")
    )
    helper = text(
        "roles/host_desktop_common/files/"
        "privatestack-session-lifecycle.sh"
    )
    common_tasks = text(
        "roles/host_desktop_common/tasks/main.yml"
    )
    hypr = text(
        "roles/host_desktop_hyprland/templates/hyprland.lua.j2"
    )

    require(
        defaults[
            "host_desktop_hyprland_session_lifecycle_enabled"
        ]
        is False,
        "lifecycle staging became enabled by default",
    )
    require(
        defaults[
            "host_desktop_hyprland_session_activation_enabled"
        ]
        is False,
        "permanent session activation became enabled",
    )
    require(
        defaults["host_desktop_hyprland_manage_ly"] is False,
        "role started selecting Ly state",
    )
    require(
        defaults["host_desktop_hyprland_preserve_sway_fallback"]
        is True,
        "Sway recovery stopped being mandatory",
    )
    require(
        'hl.on("hyprland.start"' not in hypr,
        "lifecycle leaked into non-active compositor config",
    )

    require(
        defaults["host_desktop_hyprland_session_entries"]
        == [
            "hyperlab-hyprland.desktop",
            "hyperlab-sway.desktop",
        ],
        "managed session set changed",
    )

    for marker in (
        "clear_session_environment",
        "refuse_concurrent_compositor",
        "wait_for_hyprland_runtime",
        "wait_for_sway_runtime",
        "hyprctl instances -j",
        ".wl_socket",
        "HYPERLAB_SESSION_LIFECYCLE_MANAGED",
        "systemctl --user unset-environment",
        "systemctl --user set-environment",
        "dbus-update-activation-environment",
        "xdg-desktop-portal.service",
        "hyperlab-hyprland-session.target",
        "graphical-session.target",
        "HYPRLAND_NO_SD_TARGET=1",
        "/usr/bin/start-hyprland",
        "/usr/bin/sway",
    ):
        require(
            marker in helper,
            f"controller marker missing: {marker}",
        )

    for forbidden in ("eval ", "sudo ", "pkexec", "/sys/"):
        require(
            forbidden not in helper,
            f"forbidden controller primitive: {forbidden}",
        )

    require(
        "Install the shared host session lifecycle controller"
        in common_tasks,
        "common role does not deploy controller",
    )

    sessions = {
        "hyperlab-hyprland.desktop":
            "privatestack-session-lifecycle launch hyprland",
        "hyperlab-sway.desktop":
            "privatestack-session-lifecycle launch sway",
    }

    for name, marker in sessions.items():
        require(
            marker in text(
                "roles/host_desktop_hyprland/files/" + name
            ),
            f"session entry changed: {name}",
        )

    target = text(
        "roles/host_desktop_hyprland/files/"
        "hyperlab-hyprland-session.target"
    )

    require(
        "Requires=graphical-session.target" in target
        and "After=graphical-session.target" in target
        and "PartOf=graphical-session.target" in target,
        "managed target lost graphical-session coupling",
    )
    require(
        "hyprland-session.target" not in target,
        "managed target depends on an unshipped Hyprland target",
    )

    for service in defaults[
        "host_desktop_hyprland_session_services"
    ]:
        source = text(
            "roles/host_desktop_hyprland/files/" + service
        )
        require(
            "PartOf=hyperlab-hyprland-session.target" in source,
            f"{service} is not session-bound",
        )

    names = {
        task.get("name"): task
        for task in tasks
        if isinstance(task, dict)
    }

    lifecycle_names = {
        name
        for name in names
        if name
        and (
            "lifecycle" in name.lower()
            or name.startswith("Install selectable HyperLab")
            or name.startswith("Install the HyperLab Hyprland")
            or name.startswith("Install HyperLab Hyprland")
            or name.startswith("Create HyperLab Hyprland")
            or name.startswith("Couple HyperLab helpers")
            or name.startswith("Create hyprpolkitagent")
            or name.startswith("Couple package polkit")
        )
    }

    require(
        lifecycle_names,
        "lifecycle task set missing",
    )

    for name in lifecycle_names:
        require(
            names[name].get("when")
            == "host_desktop_hyprland_session_lifecycle_enabled",
            f"lifecycle task not opt-in guarded: {name}",
        )

    require(
        "uwsm"
        not in defaults[
            "host_desktop_hyprland_prerequisite_packages"
        ],
        "UWSM became an implicit dependency",
    )

    print("HyperLab host Hyprland session lifecycle contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
