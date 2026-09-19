#!/usr/bin/env python3
"""Contract for shared read-only HyperLab host telemetry."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab Quickshell telemetry contract: {message}"
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

    bar = text(
        "roles/host_desktop_common/files/"
        "quickshell/hyperlab/HyperLabBar.qml"
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
        '"TEMP "',
        '"NET "',
        '"VOL "',
        '"BAT "',
        "interval: 30000",
    ):
        require(
            marker in bar,
            f"shared telemetry marker missing: {marker}",
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
            forbidden not in bar,
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

    print(
        "HyperLab shared host telemetry contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
