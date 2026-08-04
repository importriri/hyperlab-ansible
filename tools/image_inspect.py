#!/usr/bin/env python3
"""Inspect one candidate or committed base image without modifying it."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


class InspectError(ValueError):
    """The candidate cannot be accepted as a sealed base."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, text=True, capture_output=True, check=False)


def inspect(path: Path, qemu_img: str, expected_format: str, expected_size_gib: int) -> dict[str, Any]:
    try:
        lst = path.lstat()
    except FileNotFoundError as exc:
        raise InspectError(f"image does not exist: {path}") from exc
    except OSError as exc:
        raise InspectError(f"image cannot be inspected: {exc}") from exc
    if stat.S_ISLNK(lst.st_mode) or not stat.S_ISREG(lst.st_mode):
        raise InspectError(f"image must be one regular non-symlink file: {path}")
    real = path.resolve(strict=True)
    if real != path.absolute():
        raise InspectError(f"image path is redirected: {path} -> {real}")

    info_result = run([qemu_img, "info", "--output=json", str(path)])
    if info_result.returncode != 0:
        raise InspectError(f"qemu-img info failed: {info_result.stderr.strip()}")
    try:
        info = json.loads(info_result.stdout)
    except json.JSONDecodeError as exc:
        raise InspectError(f"qemu-img info returned invalid JSON: {exc}") from exc
    if not isinstance(info, dict):
        raise InspectError("qemu-img info JSON root must be a mapping")
    if info.get("format") != expected_format:
        raise InspectError(f"format {info.get('format')!r} != expected {expected_format!r}")
    expected_bytes = expected_size_gib * 1024 * 1024 * 1024
    if info.get("virtual-size") != expected_bytes:
        raise InspectError(
            f"virtual size {info.get('virtual-size')!r} != expected {expected_bytes} bytes"
        )
    if info.get("backing-filename") is not None:
        raise InspectError("a sealed base must not have a backing file")

    check_result = run([qemu_img, "check", "-f", expected_format, str(path)])
    if check_result.returncode != 0:
        raise InspectError(f"qemu-img check failed: {check_result.stderr.strip() or check_result.stdout.strip()}")

    return {
        "path": str(path),
        "realpath": str(real),
        "device": int(lst.st_dev),
        "size_bytes": int(lst.st_size),
        "sha256": sha256_file(path),
        "format": info["format"],
        "virtual_size_bytes": info["virtual-size"],
        "backing_file": None,
        "qemu_img_check": "pass",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", required=True)
    parser.add_argument("--qemu-img", required=True)
    parser.add_argument("--expected-format", required=True)
    parser.add_argument("--expected-size-gib", required=True, type=int)
    args = parser.parse_args()
    try:
        result = inspect(Path(args.path), args.qemu_img, args.expected_format, args.expected_size_gib)
    except (InspectError, OSError) as exc:
        print(f"image inspection refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
