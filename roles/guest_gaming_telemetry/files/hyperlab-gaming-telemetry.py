#!/usr/bin/env python3
"""Record and summarize MangoHud frame telemetry for HyperLab."""

from __future__ import annotations

import argparse
import csv
import io
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_CONFIG = Path("/etc/privatestack/gaming-telemetry.json")


class TelemetryError(RuntimeError):
    """A deterministic telemetry contract failure."""


def load_config() -> dict[str, Any]:
    path = Path(
        os.environ.get(
            "HYPERLAB_GAMING_TELEMETRY_CONFIG",
            str(DEFAULT_CONFIG),
        )
    )

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise TelemetryError(
            f"cannot read telemetry config {path}: {exc}"
        ) from exc

    required = {
        "schema_version",
        "output_root",
        "log_interval_ms",
        "autostart_seconds",
        "min_samples",
    }

    missing = required - data.keys()

    if missing:
        raise TelemetryError(
            "telemetry config missing: "
            + ", ".join(sorted(missing))
        )

    if data["schema_version"] != 1:
        raise TelemetryError("unsupported telemetry schema")

    if int(data["log_interval_ms"]) != 0:
        raise TelemetryError(
            "frame telemetry requires log_interval_ms=0"
        )

    if int(data["min_samples"]) < 100:
        raise TelemetryError(
            "min_samples must be at least 100"
        )

    return data


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        raise TelemetryError("cannot percentile an empty sample set")

    if not 0.0 <= quantile <= 1.0:
        raise TelemetryError("percentile quantile outside [0, 1]")

    ordered = sorted(values)

    if len(ordered) == 1:
        return ordered[0]

    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)

    if lower == upper:
        return ordered[lower]

    fraction = position - lower

    return (
        ordered[lower]
        + (ordered[upper] - ordered[lower]) * fraction
    )


def compute_metrics(frame_ms: list[float]) -> dict[str, float | int | str]:
    clean = [
        value
        for value in frame_ms
        if math.isfinite(value) and value > 0.0
    ]

    if not clean:
        raise TelemetryError("no valid frame-time samples")

    mean_ms = statistics.fmean(clean)
    p95_ms = percentile(clean, 0.95)
    p99_ms = percentile(clean, 0.99)
    p999_ms = percentile(clean, 0.999)

    return {
        "sample_count": len(clean),
        "duration_seconds": sum(clean) / 1000.0,
        "frame_time_mean_ms": mean_ms,
        "frame_time_p95_ms": p95_ms,
        "frame_time_p99_ms": p99_ms,
        "frame_time_p99_9_ms": p999_ms,
        "average_fps": 1000.0 / mean_ms,
        "one_percent_low_fps": 1000.0 / p99_ms,
        "zero_point_one_percent_low_fps": 1000.0 / p999_ms,
        "low_fps_method": "reciprocal_of_frame_time_percentile",
    }


def normalized(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")


def choose_column(fieldnames: list[str], target: str) -> str | None:
    exact = {
        normalized(name): name
        for name in fieldnames
        if name
    }

    if target in exact:
        return exact[target]

    for key, original in exact.items():
        if target in key:
            return original

    return None


def parse_mangohud_csv(path: Path) -> tuple[list[float], str]:
    try:
        raw_lines = path.read_text(
            encoding="utf-8",
            errors="strict",
        ).splitlines()
    except OSError as exc:
        raise TelemetryError(
            f"cannot read MangoHud log {path}: {exc}"
        ) from exc

    lines = [
        line
        for line in raw_lines
        if line.strip()
        and not line.lstrip().startswith("#")
    ]

    if len(lines) < 2:
        raise TelemetryError("MangoHud CSV has no data rows")

    # MangoHud writes a machine metadata table before the actual
    # per-frame metric table. Locate the metric header instead of
    # assuming that the first non-comment row is fps/frametime.
    metric_header_index: int | None = None

    for index, line in enumerate(lines):
        try:
            columns = next(csv.reader([line]))
        except csv.Error:
            continue

        normalized_columns = {
            normalized(column)
            for column in columns
            if column
        }

        if (
            "frametime" in normalized_columns
            or "fps" in normalized_columns
        ):
            metric_header_index = index
            break

    if metric_header_index is None:
        raise TelemetryError(
            "MangoHud CSV contains no metric header"
        )

    metric_lines = lines[metric_header_index:]

    if len(metric_lines) < 2:
        raise TelemetryError(
            "MangoHud metric table contains no data rows"
        )

    reader = csv.DictReader(
        io.StringIO("\n".join(metric_lines))
    )

    fieldnames = [
        name
        for name in (reader.fieldnames or [])
        if name is not None
    ]

    frame_column = choose_column(fieldnames, "frametime")
    fps_column = choose_column(fieldnames, "fps")

    frame_ms: list[float] = []

    if frame_column is not None:
        for row in reader:
            raw = row.get(frame_column)

            if raw is None:
                continue

            try:
                value = float(raw.strip())
            except ValueError:
                continue

            if math.isfinite(value) and value > 0:
                frame_ms.append(value)

        return frame_ms, "frametime"

    if fps_column is not None:
        for row in reader:
            raw = row.get(fps_column)

            if raw is None:
                continue

            try:
                fps = float(raw.strip())
            except ValueError:
                continue

            if math.isfinite(fps) and fps > 0:
                frame_ms.append(1000.0 / fps)

        return frame_ms, "fps_derived"

    raise TelemetryError(
        "MangoHud CSV contains neither frametime nor fps"
    )


def sanitize_label(value: str) -> str:
    label = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")

    if not label:
        raise TelemetryError("empty telemetry label after sanitization")

    return label[:80]


def write_summary(
    path: Path,
    summary: dict[str, Any],
) -> None:
    path.write_text(
        json.dumps(
            summary,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )

    text_path = path.with_suffix(".txt")

    ordered = [
        "schema_version",
        "source_column",
        "sample_count",
        "duration_seconds",
        "average_fps",
        "one_percent_low_fps",
        "zero_point_one_percent_low_fps",
        "frame_time_mean_ms",
        "frame_time_p95_ms",
        "frame_time_p99_ms",
        "frame_time_p99_9_ms",
        "low_fps_method",
        "command_rc",
    ]

    lines = []

    for key in ordered:
        value = summary[key]

        if isinstance(value, float):
            lines.append(f"{key}={value:.6f}")
        else:
            lines.append(f"{key}={value}")

    text_path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


def build_mangohud_config(
    run_dir: Path,
    config: dict[str, Any],
) -> str:
    return "\n".join(
        [
            f"autostart_log={int(config['autostart_seconds'])}",
            f"log_interval={int(config['log_interval_ms'])}",
            f"output_folder={run_dir}",
            "permit_upload=0",
            "fps",
            "frametime",
            "gpu_stats",
            "gpu_temp",
            "gpu_core_clock",
            "gpu_power",
            "",
        ]
    )


def record(args: argparse.Namespace) -> int:
    config = load_config()

    command = list(args.command)

    if command and command[0] == "--":
        command = command[1:]

    if not command:
        raise TelemetryError(
            "record requires a command after --"
        )

    mangohud = shutil.which("mangohud")

    if mangohud is None:
        raise TelemetryError("mangohud executable is unavailable")

    label = sanitize_label(args.label)

    output_root = (
        Path(args.output_root).expanduser()
        if args.output_root
        else Path(config["output_root"]).expanduser()
    )

    stamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%SZ"
    )

    run_dir = output_root / f"{stamp}-{label}-{os.getpid()}"
    run_dir.mkdir(parents=True, exist_ok=False)

    mangohud_config = run_dir / "MangoHud.conf"
    mangohud_config.write_text(
        build_mangohud_config(run_dir, config),
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.pop("MANGOHUD_CONFIG", None)
    env["MANGOHUD_CONFIGFILE"] = str(mangohud_config)

    print(f"HYPERLAB_TELEMETRY_RUN_DIR={run_dir}", flush=True)
    print(
        "HYPERLAB_TELEMETRY_COMMAND="
        + " ".join(command),
        flush=True,
    )

    completed = subprocess.run(
        [mangohud, *command],
        env=env,
        check=False,
    )

    logs = sorted(run_dir.glob("*.csv"))

    if len(logs) != 1:
        raise TelemetryError(
            "expected exactly one MangoHud CSV, "
            f"found {len(logs)}"
        )

    samples, source_column = parse_mangohud_csv(logs[0])

    minimum = (
        args.min_samples
        if args.min_samples is not None
        else int(config["min_samples"])
    )

    if len(samples) < minimum:
        raise TelemetryError(
            f"only {len(samples)} frame samples; "
            f"minimum is {minimum}"
        )

    metrics = compute_metrics(samples)

    summary: dict[str, Any] = {
        "schema_version": 1,
        "source_log": str(logs[0]),
        "source_column": source_column,
        "command": command,
        "command_rc": completed.returncode,
        **metrics,
    }

    summary_path = run_dir / "summary.json"
    write_summary(summary_path, summary)

    print(
        (run_dir / "summary.txt").read_text(
            encoding="utf-8"
        ),
        end="",
    )

    print(
        f"HYPERLAB_TELEMETRY_CSV={logs[0]}",
        flush=True,
    )
    print(
        f"HYPERLAB_TELEMETRY_SUMMARY={summary_path}",
        flush=True,
    )

    if completed.returncode != 0:
        return completed.returncode

    return 0


def self_test() -> int:
    values = [10.0] * 1000
    metrics = compute_metrics(values)

    assert metrics["sample_count"] == 1000
    assert math.isclose(
        float(metrics["average_fps"]),
        100.0,
    )
    assert math.isclose(
        float(metrics["one_percent_low_fps"]),
        100.0,
    )
    assert math.isclose(
        float(metrics["zero_point_one_percent_low_fps"]),
        100.0,
    )
    assert math.isclose(
        float(metrics["frame_time_p95_ms"]),
        10.0,
    )
    assert math.isclose(
        float(metrics["frame_time_p99_ms"]),
        10.0,
    )

    fixture = (
        "os,cpu,gpu,ram,kernel,driver,cpuscheduler\n"
        "Arch Linux,Test CPU,Test GPU,16384,test-kernel,test-driver,\n"
        " fps,frametime,gpu_load\n"
        "100,10.0,50\n"
        "50,20.0,60\n"
    )

    reader_path = Path(
        os.environ.get(
            "TMPDIR",
            "/tmp",
        )
    ) / f"hyperlab-gaming-telemetry-{os.getpid()}.csv"

    try:
        reader_path.write_text(
            fixture,
            encoding="utf-8",
        )

        parsed, source = parse_mangohud_csv(reader_path)

        assert source == "frametime"
        assert parsed == [10.0, 20.0]
    finally:
        reader_path.unlink(missing_ok=True)

    print("gaming telemetry self-test: OK")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description=(
            "Record MangoHud frametimes and publish "
            "reproducible HyperLab metrics."
        )
    )

    commands = root.add_subparsers(
        dest="subcommand",
        required=True,
    )

    commands.add_parser(
        "self-test",
        help="validate the local metric parser",
    )

    record_parser = commands.add_parser(
        "record",
        help="record one instrumented workload",
    )

    record_parser.add_argument(
        "--label",
        required=True,
    )
    record_parser.add_argument(
        "--output-root",
    )
    record_parser.add_argument(
        "--min-samples",
        type=int,
    )
    record_parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
    )

    return root


def main() -> int:
    args = parser().parse_args()

    try:
        if args.subcommand == "self-test":
            return self_test()

        if args.subcommand == "record":
            return record(args)

        raise TelemetryError(
            f"unsupported subcommand: {args.subcommand}"
        )
    except TelemetryError as exc:
        print(
            f"HYPERLAB_TELEMETRY_ERROR={exc}",
            file=sys.stderr,
        )
        return 65


if __name__ == "__main__":
    raise SystemExit(main())
