#!/usr/bin/env python3
"""Static contract for guest gaming frame telemetry."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def load(relative: str):
    return yaml.safe_load(text(relative))


def load_recorder():
    path = (
        ROOT
        / "roles/guest_gaming_telemetry/files/"
        "hyperlab-gaming-telemetry.py"
    )

    spec = importlib.util.spec_from_file_location(
        "hyperlab_gaming_telemetry",
        path,
    )

    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def main() -> None:
    defaults = load(
        "roles/guest_gaming_telemetry/defaults/main.yml"
    )
    tasks_text = text(
        "roles/guest_gaming_telemetry/tasks/main.yml"
    )
    graph = load("group_vars/all/bricks.yml")
    play = load("playbooks/guest-gaming-telemetry.yml")[0]
    vfio_roles = load(
        "playbooks/guest-arch-dev-vfio.yml"
    )[0]["roles"]

    assert defaults["guest_gaming_telemetry_packages"] == [
        "mangohud",
        "vkmark",
    ]

    assert (
        defaults["guest_gaming_telemetry_log_interval_ms"]
        == 0
    )

    assert (
        defaults["guest_gaming_telemetry_min_samples"]
        >= 100
    )

    assert (
        defaults["guest_gaming_telemetry_command"]
        == "/usr/local/bin/hyperlab-gaming-telemetry"
    )

    assert "'workstations' in group_names" in tasks_text
    assert "'hypervisor' not in group_names" in tasks_text
    assert (
        "ansible_facts['virtualization_role'] == 'guest'"
        in tasks_text
    )

    assert "Install the frame telemetry package" in tasks_text
    assert "gaming-telemetry.json.j2" in tasks_text
    assert "hyperlab-gaming-telemetry.py" in tasks_text
    assert (
        "brick_guard_brick: guest_gaming_telemetry"
        in tasks_text
    )

    assert graph["brick_requires"][
        "guest_gaming_telemetry"
    ] == ["guest_gpu_nvidia"]

    assert graph["brick_playbooks"][
        "guest_gaming_telemetry"
    ] == "playbooks/guest-gaming-telemetry.yml"

    assert play["hosts"] == "workstations"
    assert play["become"] is True
    assert play["roles"][0] == {
        "role": "brick_guard",
        "vars": {
            "brick_guard_brick": "guest_gaming_telemetry"
        },
    }
    assert play["roles"][1] == "guest_gaming_telemetry"

    assert vfio_roles[5] == "guest_gaming_telemetry"
    assert vfio_roles[6] == {
        "role": "guest_looking_glass_linux",
        "vars": {
            "guest_looking_glass_linux_experimental": True
        },
    }

    recorder_text = text(
        "roles/guest_gaming_telemetry/files/"
        "hyperlab-gaming-telemetry.py"
    )

    for token in (
        "MANGOHUD_CONFIGFILE",
        "autostart_log=",
        "log_interval=",
        "output_folder=",
        "frametime",
        "average_fps",
        "one_percent_low_fps",
        "zero_point_one_percent_low_fps",
        "frame_time_p95_ms",
        "frame_time_p99_ms",
        "permit_upload=0",
    ):
        assert token in recorder_text

    assert '"no_display"' not in recorder_text

    recorder = load_recorder()

    metrics = recorder.compute_metrics([10.0] * 1000)

    assert metrics["sample_count"] == 1000
    assert metrics["average_fps"] == 100.0
    assert metrics["one_percent_low_fps"] == 100.0
    assert (
        metrics["zero_point_one_percent_low_fps"]
        == 100.0
    )
    assert metrics["frame_time_p95_ms"] == 10.0
    assert metrics["frame_time_p99_ms"] == 10.0

    # Exercise the real MangoHud metadata-preamble parser shape.
    assert recorder.self_test() == 0

    print("guest gaming telemetry contract: OK")


if __name__ == "__main__":
    main()
