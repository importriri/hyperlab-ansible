#!/usr/bin/env python3
"""Contract for the read-only shared HyperLab Quickshell status core."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
QML = "roles/host_desktop_common/files/quickshell/hyperlab/"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            "HyperLab Quickshell readonly runtime contract: "
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

    state_qml = text(QML + "ShellState.qml")
    bar = text(QML + "HyperLabBar.qml")
    machine_stage = text(QML + "MachineStage.qml")
    context = text(QML + "ContextCluster.qml")
    identity = text(QML + "IdentityMark.qml")
    gpu = text(QML + "GpuBadge.qml")

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
        "applyTrustPayload(data)",
    ):
        require(
            marker in state_qml,
            f"required runtime marker missing: {marker}",
        )

    for marker, corpus in (
        ('text: "HyperLab"', identity),
        ("badge.claim.claimed", gpu),
        (
            "provenanceColor(badge.claim.identity)",
            gpu,
        ),
        (
            "claim: bar.shellState.trustClaim",
            bar,
        ),
        (
            "payload: bar.shellState.gpuPayload",
            bar,
        ),
        (
            "shellState.machines",
            machine_stage,
        ),
        (
            "cluster.context",
            context,
        ),
    ):
        require(
            marker in corpus,
            f"required presentation wiring missing: {marker}",
        )

    shared_qml = "\n".join(
        text(QML + name)
        for name in stage["surface_files"]
    )

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
    ):
        require(
            forbidden not in shared_qml,
            f"forbidden shell behavior appeared: {forbidden}",
        )

    require(
        state_qml.count('"watch"') == 1
        and state_qml.count('"trust"') >= 1,
        "trust stream command is no longer singular",
    )

    require(
        "interval: 1000" not in state_qml
        and "interval: 5000" not in state_qml,
        "read-only status core gained aggressive polling",
    )

    print(
        "HyperLab shared Quickshell read-only runtime contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
