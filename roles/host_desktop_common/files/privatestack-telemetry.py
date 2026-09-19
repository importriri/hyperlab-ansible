#!/usr/bin/env python3
"""Read-only host telemetry bridge for the shared HyperLab Shell."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path


WPCTL = Path("/usr/bin/wpctl")


def payload(
    text: str,
    tooltip: str = "",
    status_class: str = "",
) -> dict[str, str]:
    """Return the narrow presentation object consumed by Quickshell."""
    return {
        "text": text,
        "tooltip": tooltip,
        "class": status_class,
    }


def read_text(path: Path) -> str | None:
    """Read a small kernel/userspace status file without mutating it."""
    try:
        return path.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return None


def temperature_value(raw: str | None) -> float | None:
    if raw is None:
        return None

    try:
        value = float(raw)
    except ValueError:
        return None

    if value > 1000:
        value /= 1000.0

    if not 0.0 < value < 150.0:
        return None

    return value


def temperature_payload() -> dict[str, str]:
    candidates: list[tuple[float, str]] = []

    thermal_root = Path("/sys/class/thermal")
    for zone in sorted(thermal_root.glob("thermal_zone*")):
        value = temperature_value(read_text(zone / "temp"))
        if value is None:
            continue

        source = read_text(zone / "type") or zone.name
        candidates.append((value, source))

    hwmon_root = Path("/sys/class/hwmon")
    for input_path in sorted(hwmon_root.glob("hwmon*/temp*_input")):
        value = temperature_value(read_text(input_path))
        if value is None:
            continue

        chip = read_text(input_path.parent / "name") or input_path.parent.name
        label_path = input_path.with_name(
            input_path.name.replace("_input", "_label")
        )
        label = read_text(label_path) or input_path.stem
        candidates.append((value, f"{chip} {label}".strip()))

    if not candidates:
        return payload(
            "—",
            "No readable host temperature sensor",
            "unavailable",
        )

    preferred_words = (
        "cpu",
        "core",
        "package",
        "x86",
        "tctl",
        "tdie",
        "acpitz",
    )

    preferred = [
        item
        for item in candidates
        if any(
            word in item[1].lower()
            for word in preferred_words
        )
    ]

    selected = max(preferred or candidates, key=lambda item: item[0])
    value, source = selected

    if value >= 82:
        status_class = "critical"
    elif value >= 75:
        status_class = "warning"
    else:
        status_class = ""

    return payload(
        f"{value:.0f}°C",
        f"Host temperature: {value:.1f}°C ({source})",
        status_class,
    )


def default_interface() -> str | None:
    route = read_text(Path("/proc/net/route"))
    if route is None:
        return None

    for line in route.splitlines()[1:]:
        fields = line.split()
        if len(fields) < 4 or fields[1] != "00000000":
            continue

        try:
            flags = int(fields[3], 16)
        except ValueError:
            continue

        if flags & 0x1:
            return fields[0]

    return None


def network_payload() -> dict[str, str]:
    interface = default_interface()

    if not interface:
        return payload(
            "offline",
            "No active default network route",
            "warning",
        )

    device = Path("/sys/class/net") / interface
    state = read_text(device / "operstate") or "unknown"
    wireless = (device / "wireless").exists()

    if state != "up":
        return payload(
            "offline",
            f"Default interface {interface}: {state}",
            "warning",
        )

    kind = "wifi" if wireless else "wired"

    return payload(
        kind,
        f"Default interface: {interface}",
        "",
    )


def audio_payload() -> dict[str, str]:
    if not WPCTL.is_file():
        return payload(
            "—",
            "wpctl is unavailable",
            "unavailable",
        )

    try:
        result = subprocess.run(
            [
                str(WPCTL),
                "get-volume",
                "@DEFAULT_AUDIO_SINK@",
            ],
            capture_output=True,
            check=False,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.SubprocessError):
        return payload(
            "—",
            "Default audio sink is unavailable",
            "unavailable",
        )

    if result.returncode != 0:
        return payload(
            "—",
            "Default audio sink is unavailable",
            "unavailable",
        )

    match = re.search(
        r"Volume:\s*([0-9]+(?:\.[0-9]+)?)",
        result.stdout,
    )

    if match is None:
        return payload(
            "—",
            "Unable to parse default audio volume",
            "unavailable",
        )

    percent = round(float(match.group(1)) * 100)
    percent = max(0, min(percent, 125))
    muted = "[MUTED]" in result.stdout.upper()

    if muted:
        return payload(
            "mute",
            f"Default audio sink: muted ({percent}%)",
            "warning",
        )

    return payload(
        f"{percent}%",
        f"Default audio sink: {percent}%",
        "",
    )


def battery_payload() -> dict[str, str]:
    batteries = sorted(
        Path("/sys/class/power_supply").glob("BAT*")
    )

    if not batteries:
        return payload(
            "—",
            "No battery exposed by this host",
            "unavailable",
        )

    battery = batteries[0]
    capacity_raw = read_text(battery / "capacity")
    status = read_text(battery / "status") or "Unknown"

    try:
        capacity = int(capacity_raw or "")
    except ValueError:
        return payload(
            "—",
            "Battery capacity is unavailable",
            "unavailable",
        )

    capacity = max(0, min(capacity, 100))

    if capacity <= 10:
        status_class = "critical"
    elif capacity <= 25:
        status_class = "warning"
    else:
        status_class = ""

    return payload(
        f"{capacity}%",
        f"Battery: {capacity}% ({status})",
        status_class,
    )


def snapshot() -> dict[str, dict[str, str]]:
    """Build one compositor-independent telemetry snapshot."""
    return {
        "temperature": temperature_payload(),
        "network": network_payload(),
        "audio": audio_payload(),
        "battery": battery_payload(),
    }


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "snapshot":
        print(
            "usage: privatestack-telemetry snapshot",
            file=sys.stderr,
        )
        return 2

    print(
        json.dumps(
            snapshot(),
            separators=(",", ":"),
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
