#!/usr/bin/env python3
"""Contract for the pure HyperLab trust wallpaper planner."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

ENGINE = ROOT / "tools/trust_wallpaper_engine.py"
POOL = ROOT / "themes/assets/hyperlab-trust-v2"

TRUST_COLORS = {
    "host": "#8b949e",
    "clean": "#72f2a5",
    "dev": "#5b8cff",
    "services": "#35e4dd",
    "dirty": "#ff9d45",
    "lab": "#b184ff",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab trust wallpaper engine contract: {message}"
        )


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3",
            str(ENGINE),
            "--pool-root",
            str(POOL),
            *args,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def plan(trust: str, epoch: int) -> dict:
    result = run(
        "plan",
        "--trust",
        trust,
        "--epoch",
        str(epoch),
    )

    require(
        result.returncode == 0,
        result.stdout + result.stderr,
    )

    return json.loads(result.stdout)


def main() -> int:
    require(ENGINE.is_file(), "engine missing")
    require(
        bool(ENGINE.stat().st_mode & 0o111),
        "engine is not executable",
    )

    validation = run("validate")

    require(
        validation.returncode == 0,
        validation.stdout + validation.stderr,
    )

    require(
        "TRUST_WALLPAPER_ENGINE=PASS"
        in validation.stdout,
        "validator did not report PASS",
    )

    # Two variants at 30-minute boundaries:
    # slot 0 -> 01
    # slot 1 -> 02
    # slot 2 -> 01
    epochs = (
        (0, "01.png"),
        (1799, "01.png"),
        (1800, "02.png"),
        (3599, "02.png"),
        (3600, "01.png"),
    )

    for trust, color in TRUST_COLORS.items():
        rgb = color.removeprefix("#")

        for epoch, expected_name in epochs:
            payload = plan(trust, epoch)

            require(
                payload["schema"] == 1,
                "planner schema changed",
            )

            require(
                payload["trust"] == trust,
                "planner changed trust identity",
            )

            require(
                payload["trust_source"]
                == "host-owned",
                "planner invented trust authority",
            )

            require(
                payload["trust_color"] == color,
                f"trust color drift: {trust}",
            )

            expected_prefix = (
                f"images/{trust}/"
            )

            require(
                payload["wallpaper_relative"]
                .startswith(expected_prefix),
                (
                    "cross-trust wallpaper selected: "
                    f"{trust} -> "
                    f"{payload['wallpaper_relative']}"
                ),
            )

            require(
                payload["wallpaper_relative"]
                .endswith(expected_name),
                (
                    f"rotation slot wrong for {trust} "
                    f"at epoch {epoch}"
                ),
            )

            require(
                payload["wallpaper_count"] == 2,
                "candidate pool size changed",
            )

            require(
                payload["rotation_interval_seconds"]
                == 1800,
                "30-minute contract changed",
            )

            require(
                payload["cross_trust_rotation"]
                is False,
                "cross-trust rotation became possible",
            )

            require(
                payload["wallpaper_may_set_trust"]
                is False,
                "wallpaper gained trust authority",
            )

            require(
                payload["rgb_follows_wallpaper"]
                is False,
                "RGB started following artwork",
            )

            require(
                payload["rgb_follows_trust"]
                is True,
                "RGB disconnected from trust",
            )

            require(
                payload["rgb_provider"]
                == "hyperlab-nitro-control",
                "RGB escaped reviewed broker",
            )

            require(
                payload["rgb_zones"]
                == [rgb, rgb, rgb, rgb],
                f"four-zone RGB drift: {trust}",
            )

    # Same trust at two visual slots: RGB must not change.
    dev_a = plan("dev", 0)
    dev_b = plan("dev", 1800)

    require(
        dev_a["wallpaper_relative"]
        != dev_b["wallpaper_relative"],
        "DEV wallpaper did not rotate",
    )

    require(
        dev_a["rgb_zones"]
        == dev_b["rgb_zones"],
        "DEV RGB incorrectly follows wallpaper variant",
    )

    # A trust transition must switch pool immediately.
    transition = run(
        "transition",
        "--previous",
        "dev",
        "--trust",
        "dirty",
        "--epoch",
        "1800",
    )

    require(
        transition.returncode == 0,
        transition.stdout + transition.stderr,
    )

    transition_payload = json.loads(
        transition.stdout
    )

    require(
        transition_payload["transition_reason"]
        == "trust-change",
        "trust change not identified",
    )

    require(
        transition_payload["previous_trust"]
        == "dev",
        "previous trust lost",
    )

    require(
        transition_payload["trust"] == "dirty",
        "new trust lost",
    )

    require(
        transition_payload["wallpaper_relative"]
        .startswith("images/dirty/"),
        "trust change retained previous pool",
    )

    # Fail closed on unreviewed identity.
    bad = subprocess.run(
        [
            "python3",
            str(ENGINE),
            "--pool-root",
            str(POOL),
            "plan",
            "--trust",
            "unknown",
            "--epoch",
            "0",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    require(
        bad.returncode != 0,
        "unknown trust identity was accepted",
    )

    # Planner itself must not contain runtime side effects.
    source = ENGINE.read_text(encoding="utf-8")

    forbidden = (
        "swaymsg",
        "hyprctl",
        "hyprpaper",
        "wpctl",
        "sudo",
        "pkexec",
        "hyperlab-nitro-control",
        "subprocess.run(",
        "subprocess.Popen(",
        "os.system(",
    )

    for marker in forbidden:
        # The provider name is valid as inert JSON output only.
        if marker == "hyperlab-nitro-control":
            continue

        require(
            marker not in source,
            f"planner gained runtime side effect: {marker}",
        )

    print(
        "HyperLab pure trust wallpaper rotation engine contract: OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
