#!/usr/bin/env python3
"""Contract for typed interactive controls in the shared HyperLab Shell."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab interactive shell contract: {message}"
        )


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    shared = yaml.safe_load(
        text("group_vars/all/host-desktop.yml")
    )
    stage = shared["host_desktop_common_shell_stage"]
    product = shared["host_desktop_common_product_contract"]

    require(
        product["shell"]["fake_controls_allowed"] is False,
        "fake controls became allowed",
    )
    require(
        stage["session_controls_enabled"] is True,
        "interactive session control gate is disabled",
    )
    require(
        stage["session_action_bridge"]
        == "/usr/local/bin/privatestack-shell-actions",
        "typed action bridge changed",
    )
    require(
        stage["session_state_transport"] == "file-watch",
        "session state stopped being event-driven",
    )
    require(
        stage["session_actions"]
        == [
            "keyboard-cycle",
            "wallpaper-mode-toggle",
            "controls-open",
        ],
        "session action allowlist changed",
    )

    bar = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/HyperLabBar.qml"
    )

    helper_path = (
        ROOT
        / "roles/host_desktop_common/files/"
        "privatestack-shell-actions.py"
    )
    helper = helper_path.read_text(encoding="utf-8")

    tasks = text(
        "roles/host_desktop_common/tasks/main.yml"
    )

    for marker in (
        '"/usr/local/bin/privatestack-shell-actions"',
        '"keyboard-cycle"',
        '"wallpaper-mode-toggle"',
        '"controls-open"',
        "keyboardStateFile",
        "wallpaperModeStateFile",
        '"keyboard-layout"',
        '"wallpaper-mode"',
        '"KEY "',
        '"WALL "',
        'text: "CTL"',
        "TapHandler {",
    ):
        require(
            marker in bar,
            f"interactive QML marker missing: {marker}",
        )

    require(
        bar.count("TapHandler {") == 3,
        "session surface must expose exactly three reviewed tap routes",
    )

    for forbidden in (
        "/usr/local/bin/privatestack-keyboard",
        "/usr/local/bin/privatestack-theme",
        "/usr/local/bin/privatestack-controls",
        "hyprctl",
        "swaymsg",
        "sudo",
        "pkexec",
        "/bin/sh",
        '["sh", "-c"',
        '["bash", "-c"',
        "execDetached",
        "Quickshell.execDetached",
        "MouseArea",
    ):
        require(
            forbidden not in bar,
            f"QML bypassed the typed action bridge: {forbidden}",
        )

    for marker in (
        '"keyboard-cycle"',
        '"wallpaper-mode-toggle"',
        '"controls-open"',
        '"/usr/local/bin/privatestack-keyboard"',
        '"/usr/local/bin/privatestack-theme"',
        '"/usr/local/bin/privatestack-controls"',
        "trusted_target",
        "metadata.st_uid == 0",
        "metadata.st_mode & 0o022 == 0",
        "os.execv",
    ):
        require(
            marker in helper,
            f"typed bridge marker missing: {marker}",
        )

    for forbidden in (
        "subprocess",
        "os.system",
        "shell=True",
        "/bin/sh",
        "sudo",
        "pkexec",
        "hyprctl",
        "swaymsg",
        "virsh",
        "ansible-playbook",
    ):
        require(
            forbidden not in helper,
            f"typed bridge gained forbidden behavior: {forbidden}",
        )

    require(
        bool(helper_path.stat().st_mode & 0o111),
        "typed action bridge source is not executable",
    )

    for marker in (
        "Install the typed shared shell action bridge",
        "src: privatestack-shell-actions.py",
        "dest: /usr/local/bin/privatestack-shell-actions",
        'mode: "0755"',
    ):
        require(
            marker in tasks,
            f"action bridge deployment marker missing: {marker}",
        )

    print(
        "HyperLab shared interactive session controls contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
