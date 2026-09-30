#!/usr/bin/env python3
"""C9.2 native-shell legacy-route isolation contract."""

from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

BRIDGE = ROOT / (
    "roles/host_desktop_common/files/"
    "privatestack-shell-actions.py"
)

EXPECTED_ACTIONS = {
    "keyboard-cycle",
    "wallpaper-mode-toggle",
    "rgb-mode-toggle",
    "theme-cycle",
    "workspace-window-focus",
    "session-lock",
    "session-suspend",
    "session-logout",
    "session-reboot",
    "session-poweroff",
    "audio-mute-toggle",
    "audio-volume-up",
    "audio-volume-down",
}

LEGACY_ACTIONS = {
    "vms-drawer-open",
    "diagnostics-drawer-open",
    "vms-control-center-open",
    "diagnostics-control-center-open",
}


def mapping(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))

    for node in tree.body:
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == name
        ):
            return ast.literal_eval(node.value)

    raise SystemExit(name + " missing")


def require(value: bool, message: str) -> None:
    if not value:
        raise SystemExit(message)


def main() -> int:
    actions = mapping(BRIDGE, "ACTIONS")

    require(
        set(actions) == EXPECTED_ACTIONS,
        "shared shell action boundary changed",
    )

    require(
        LEGACY_ACTIONS.isdisjoint(actions),
        "legacy detached route re-entered the shell bridge",
    )

    bridge = BRIDGE.read_text(encoding="utf-8")

    require(
        "privatestack-hyperlab-route" not in bridge,
        "shared shell bridge still depends on detached route launcher",
    )

    print(
        "HyperLab C9.2 native-shell legacy-route isolation contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
