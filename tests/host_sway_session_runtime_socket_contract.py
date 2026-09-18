#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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


text = WRAPPER.read_text(encoding="utf-8")

start = text.index("wait_for_sway_runtime() {")
end = text.index("\nlaunch_hyprland() {", start)
body = text[start:end]

require(
    'local socket="${runtime_dir}/sway-ipc.${user_id}.${sway_pid}.sock"'
    in body,
    "managed Sway selects the IPC socket belonging to its launched PID",
)

require(
    "local -a sway_sockets" not in body,
    "managed Sway does not count historical IPC sockets",
)

require(
    '-name "sway-ipc.${user_id}.*.sock"' not in body,
    "managed Sway does not use a global Sway socket wildcard",
)

require(
    "refusing ambiguous Sway runtime sockets" not in body,
    "stale Sway sockets cannot reject the fresh session",
)

require(
    '[ -S "${socket}" ]' in body,
    "PID-owned Sway socket must exist before publication",
)

require(
    'SWAYSOCK="${socket}"' in body
    and "swaymsg -r -t get_version" in body,
    "PID-owned Sway socket is validated over IPC",
)

require(
    "local -a wayland_sockets" in body
    and '[ "${#wayland_sockets[@]}" -eq 1 ]' in body,
    "Wayland display publication remains unambiguous",
)

require(
    'publish_sway_runtime \\\n'
    '                    "${socket}" \\\n'
    '                    "${wayland_display}"'
    in body,
    "validated Sway and Wayland endpoints are published together",
)

require(
    "launch_hyprland() {" in text,
    "Hyprland launcher remains present after the Sway patch",
)

require(
    "HYPRLAND_NO_SD_TARGET=1" in text,
    "Hyprland remains under the HyperLab-owned session target model",
)

print("Host Sway PID-owned runtime socket contract: OK")
