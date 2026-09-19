#!/usr/bin/env python3
"""Contract for the read-only shared HyperLab Quickshell status core."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab Quickshell readonly runtime contract: {message}"
        )


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    shared = yaml.safe_load(
        text("group_vars/all/host-desktop.yml")
    )
    stage = shared["host_desktop_common_shell_stage"]

    require(
        stage["read_only_runtime_data_enabled"] is True,
        "read-only runtime data gate is not enabled",
    )
    require(
        stage["read_only_status_bridge"]
        == "/usr/local/bin/privatestack-hyperlab",
        "shell status bridge changed",
    )
    require(
        stage["trust_update_transport"] == "event-stream",
        "trust stopped being event-driven",
    )
    require(
        stage["slow_poll_seconds"] == 30,
        "slow status polling cadence changed",
    )

    bar = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/HyperLabBar.qml"
    )

    for marker in (
        "import Quickshell.Io",
        "SystemClock {",
        "Process {",
        "SplitParser {",
        '"/usr/local/bin/privatestack-hyperlab"',
        '"watch"',
        '"trust"',
        '"ram"',
        '"gpu"',
        '"vms"',
        "interval: 30000",
        'text: "◆  HYPERLAB"',
        'text: "TRUST " + root.trustPayload.text',
        'text: "RAM " + root.ramPayload.text',
        'text: "GPU " + root.gpuPayload.text',
        'text: "VM " + root.vmPayload.text',
    ):
        require(
            marker in bar,
            f"required shell marker missing: {marker}",
        )

    # Shared QML can consume the reviewed presentation bridge only.
    # Compositor IPC and privileged operations stay outside the shell.
    for forbidden in (
        "Quickshell.Hyprland",
        "Quickshell.I3",
        "hyprctl",
        "swaymsg",
        "sudo",
        "pkexec",
        "/sys/",
        "execDetached",
        "Quickshell.execDetached",
        '["sh", "-c"',
        '["bash", "-c"',
        "MouseArea",
        "TapHandler",
    ):
        require(
            forbidden not in bar,
            f"forbidden shell behavior appeared: {forbidden}",
        )

    require(
        bar.count('"watch"') == 1
        and bar.count('"trust"') >= 1,
        "trust stream command is no longer singular",
    )

    require(
        "interval: 1000" not in bar
        and "interval: 5000" not in bar,
        "read-only status core gained aggressive polling",
    )

    print(
        "HyperLab shared Quickshell read-only runtime contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
