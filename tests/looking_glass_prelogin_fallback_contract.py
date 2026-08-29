#!/usr/bin/env python3
"""Linux VFIO PRIMARY access must hand off SPICE login to Looking Glass."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPEN = (ROOT / "tools/hyperlabctl/hyperlabctl/commands/open.py").read_text(
    encoding="utf-8"
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


require(
    "_LINUX_LOOKING_GLASS_PRELOGIN_EXIT = 20" in OPEN,
    "guest pre-login state lost its dedicated result",
)
require(
    "HYPERLAB_LG_WAIT_FOR_SESSION" not in OPEN
    and "hyperlab-looking-glass-prelogin.lock" not in OPEN,
    "detached pre-login watcher survived the PRIMARY handoff redesign",
)
require(
    "_LINUX_LOOKING_GLASS_SESSION_WAIT" in OPEN
    and "for _ in $(seq 1 240)" in OPEN
    and "sleep 0.5" in OPEN,
    "SPICE login wait is not explicitly bounded",
)
require(
    'pgrep -u "$uid" -x Hyprland' in OPEN
    and "HYPRLAND_INSTANCE_SIGNATURE" in OPEN
    and "WAYLAND_DISPLAY" in OPEN
    and "Monitor HEADLESS-0" in OPEN
    and "1920x1080@144" in OPEN
    and "hyprctl monitors" in OPEN,
    "handoff does not wait for the reviewed Hyprland capture output",
)
require(
    'viewer_argv = [\n        "virt-viewer",\n'
    '        "--connect",\n        "qemu:///system",\n'
    '        "--wait",\n        domain,\n    ]'
    in OPEN,
    "PRIMARY path does not reuse the proven virt-viewer console argv",
)
require(
    "viewer = subprocess.Popen(" in OPEN
    and "start_new_session=True" in OPEN
    and "_stop_owned_process(viewer)" in OPEN,
    "temporary login console is not process-owned by the PRIMARY action",
)
require(
    "temporary SPICE login console closed before" in OPEN,
    "closing the temporary login console is not an explicit failure",
)
require(
    "sender_ready = _prepare_linux_looking_glass(" in OPEN
    and "_wait_for_linux_looking_glass_login(" in OPEN
    and "guest graphical session disappeared before" in OPEN,
    "PRIMARY path does not require a post-login sender preparation",
)
require(
    "sender_pid=$!" in OPEN
    and 'pgrep -u "$(id -u)" -x Hyprland' in OPEN
    and 'kill "$sender_pid"' in OPEN
    and "trap cleanup EXIT INT TERM HUP" in OPEN,
    "Linux sender is not owned by a Hyprland-bound supervisor",
)
require(
    "systemctl --user start" not in OPEN
    and "pkill" not in OPEN,
    "PRIMARY path introduced a persistent service or broad process kill",
)

run_start = OPEN.index("    def run(self, args, ctx):")
run_text = OPEN[run_start:]
require(
    run_text.index("sender_ready = _prepare_linux_looking_glass(")
    < run_text.index('"app:shmFile=/dev/kvmfr0"'),
    "Looking Glass can launch before the Linux sender handoff completes",
)

print("Looking Glass Linux PRIMARY handoff contract: OK")
