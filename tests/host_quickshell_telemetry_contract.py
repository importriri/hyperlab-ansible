#!/usr/bin/env python3
"""Contract for shared read-only HyperLab host telemetry."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
QML = "roles/host_desktop_common/files/quickshell/hyperlab/"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            "HyperLab Quickshell telemetry contract: "
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
        stage["telemetry_enabled"] is True,
        "telemetry gate is not enabled",
    )
    require(
        stage["telemetry_bridge"]
        == "/usr/local/bin/privatestack-telemetry",
        "telemetry bridge changed",
    )
    require(
        stage["telemetry_poll_seconds"] == 30,
        "telemetry cadence changed",
    )
    require(
        stage["telemetry_fields"]
        == [
            "temperature",
            "network",
            "audio",
            "battery",
        ],
        "telemetry field contract changed",
    )

    state = text(QML + "ShellState.qml")
    bar = text(QML + "HyperLabBar.qml")
    panel = text(QML + "SystemPanel.qml")
    osd = text(QML + "OsdSurface.qml")
    system = text(QML + "SystemCluster.qml")

    shared_qml = "\n".join(
        text(QML + name)
        for name in stage["surface_files"]
    )

    helper_path = (
        ROOT
        / "roles/host_desktop_common/files/"
        "privatestack-telemetry.py"
    )
    helper = helper_path.read_text(encoding="utf-8")
    tasks = text("roles/host_desktop_common/tasks/main.yml")

    for marker in (
        '"/usr/local/bin/privatestack-telemetry"',
        "telemetryProcess",
        '"snapshot"',
        "temperaturePayload",
        "networkPayload",
        "audioPayload",
        "batteryPayload",
        "interval: 30000",
    ):
        require(
            marker in state,
            f"shared telemetry runtime marker missing: {marker}",
        )

    for marker in (
        "audioPayload: bar.shellState.audioPayload",
        "batteryPayload: bar.shellState.batteryPayload",
        "networkPayload: bar.shellState.networkPayload",
    ):
        require(
            marker in bar,
            f"rail telemetry wiring missing: {marker}",
        )

    for marker in (
        "cluster.audioPayload",
        "cluster.batteryPayload",
        "cluster.networkPayload",
        "cluster.attentionClass",
    ):
        require(
            marker in system,
            f"system telemetry marker missing: {marker}",
        )

    for marker in (
        "panel.shellState.networkPayload",
        "panel.shellState.audioPayload",
        "panel.shellState.batteryPayload",
        "panel.shellState.temperaturePayload",
    ):
        require(
            marker in panel,
            f"system panel telemetry marker missing: {marker}",
        )

    require(
        "osd.shellState.audioLevel" in osd
        and "function show(" not in osd
        and "IpcHandler" not in osd,
        "OSD accepts caller values",
    )

    # Audio is a number from the host, not a percentage parsed back out of
    # display text, so a localized or changed label cannot alter behaviour.
    for marker in (
        "audioLevel",
        '"percent"',
        '"muted"',
        '"maximum"',
        '"present"',
        "batteryPresence",
    ):
        require(
            marker in state,
            f"structured telemetry marker missing: {marker}",
        )

    for forbidden in (
        'indexOf("mute")',
        "match(/(",
        'text === "0%"',
        'indexOf("wifi")',
        'text === "offline"',
    ):
        require(
            forbidden not in shared_qml,
            f"telemetry display text became a state machine input: {forbidden}",
        )

    for marker in (
        "percent=percent",
        "muted=True",
        "muted=False",
        "present=False",
        "present=True",
        "AUDIO_MAXIMUM",
        'kind="offline"',
        "kind=link",
    ):
        require(
            marker in helper,
            f"structured telemetry bridge marker missing: {marker}",
        )

    for forbidden in (
        "/sys/",
        "/proc/",
        "wpctl",
        "nmcli",
        "upower",
        "sensors",
        "sudo",
        "pkexec",
        "hyprctl",
        "swaymsg",
        "virsh",
        "shell=True",
    ):
        require(
            forbidden not in shared_qml,
            f"QML crossed telemetry boundary: {forbidden}",
        )

    for marker in (
        "/sys/class/thermal",
        "/sys/class/hwmon",
        "/proc/net/route",
        "/sys/class/net",
        "/sys/class/power_supply",
        "/usr/bin/wpctl",
        "subprocess.run",
        '"snapshot"',
    ):
        require(
            marker in helper,
            f"bridge source marker missing: {marker}",
        )

    for forbidden in (
        "sudo",
        "pkexec",
        "hyprctl",
        "swaymsg",
        "virsh",
        "shell=True",
        "subprocess.Popen",
        "os.system",
        "write_text(",
    ):
        require(
            forbidden not in helper,
            f"telemetry bridge gained forbidden behavior: {forbidden}",
        )

    require(
        bool(helper_path.stat().st_mode & 0o111),
        "telemetry source is not executable",
    )

    for marker in (
        "Install the shared read-only host telemetry bridge",
        "src: privatestack-telemetry.py",
        "dest: /usr/local/bin/privatestack-telemetry",
        'mode: "0755"',
    ):
        require(
            marker in tasks,
            f"telemetry deployment marker missing: {marker}",
        )

    print("HyperLab shared host telemetry contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
