#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

TARGET = (
    ROOT
    / "roles"
    / "host_desktop_hyprland"
    / "files"
    / "hyperlab-sway-session.target"
)

TASKS = (
    ROOT
    / "roles"
    / "host_desktop_hyprland"
    / "tasks"
    / "main.yml"
)

WRAPPER = (
    ROOT
    / "roles"
    / "host_desktop_common"
    / "files"
    / "privatestack-session-lifecycle.sh"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require(
    TARGET.is_file(),
    "HyperLab Sway session target source is missing",
)

target = TARGET.read_text(encoding="utf-8")
tasks = TASKS.read_text(encoding="utf-8")
wrapper = WRAPPER.read_text(encoding="utf-8")

for marker in (
    "[Unit]",
    "Description=HyperLab managed Sway session",
    "Requires=graphical-session.target",
    "After=graphical-session.target",
    "PartOf=graphical-session.target",
):
    require(
        marker in target,
        f"Sway session target missing contract: {marker}",
    )

require(
    "Install the HyperLab Sway session target" in tasks,
    "Ansible does not install the Sway session target",
)

require(
    "src: hyperlab-sway-session.target" in tasks,
    "Sway session target source is not wired into Ansible",
)

require(
    (
        "dest: "
        "/etc/systemd/user/hyperlab-sway-session.target"
    )
    in tasks,
    "Sway session target destination is incorrect",
)

require(
    (
        "readonly sway_target="
        "hyperlab-sway-session.target"
    )
    in wrapper,
    "session controller does not name the Sway owner target",
)

require(
    "stop_hyperlab_sway_target() {" in wrapper,
    "session controller cannot stop the Sway owner target",
)

clear_start = wrapper.index("clear_session_environment() {")
clear_end = wrapper.index(
    "\npublish_base_environment() {",
    clear_start,
)
clear_body = wrapper[clear_start:clear_end]

require(
    "stop_hyperlab_hyprland_target" in clear_body,
    "cleanup lost the Hyprland session target",
)

require(
    "stop_hyperlab_sway_target" in clear_body,
    "cleanup does not stop the Sway session target",
)

publish_start = wrapper.index("publish_sway_runtime() {")
publish_end = wrapper.index(
    "\nwait_for_sway_runtime() {",
    publish_start,
)
publish_body = wrapper[publish_start:publish_end]

require(
    'systemctl --user start "${sway_target}"'
    in publish_body,
    "managed Sway does not activate its owner target",
)

require(
    "systemctl --user start graphical-session.target"
    not in publish_body,
    (
        "managed Sway must not directly start the passive "
        "graphical-session.target"
    ),
)

require(
    "hyperlab-hyprland-session.target" in wrapper,
    "Hyprland session target ownership was lost",
)

print("HyperLab Sway session target contract: OK")
