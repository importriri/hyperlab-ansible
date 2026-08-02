#!/usr/bin/env python3
"""Fail closed when the M2/M3 image-store topology has drifted."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import yaml

REQUIRED_LAYOUT_DIRECTORIES = {
    "",
    "bases",
    "bases/windows",
    "bases/linux",
    "disposable",
    "permanent",
    "cloud-init",
    "nvram",
    "tpm",
    "state",
}
MANAGEMENT_DIRECTORIES = ("state/vms", "state/domains", "state/locks")


class StoreError(ValueError):
    """The verified store can no longer be used safely by the guest brick."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise StoreError(message)


def normalized_absolute(value: str, label: str) -> Path:
    path = Path(value)
    require(path.is_absolute(), f"{label} must be absolute: {path}")
    normalized = Path(os.path.normpath(str(path)))
    require(path == normalized, f"{label} must be normalized: {path}")
    return path


def lstat(path: Path, label: str) -> os.stat_result:
    try:
        return os.lstat(path)
    except FileNotFoundError as exc:
        raise StoreError(f"{label} is missing: {path}") from exc
    except OSError as exc:
        raise StoreError(f"cannot inspect {label} {path}: {exc}") from exc


def require_real_directory(path: Path, label: str, device: int | None = None) -> int:
    observed = lstat(path, label)
    require(stat.S_ISDIR(observed.st_mode), f"{label} is not a real directory: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise StoreError(f"cannot resolve {label} {path}: {exc}") from exc
    require(resolved == path, f"{label} is redirected: {path} -> {resolved}")
    if device is not None:
        require(observed.st_dev == device, f"{label} is on another filesystem: {path}")
    return observed.st_dev


def require_real_file(path: Path, label: str, device: int) -> None:
    observed = lstat(path, label)
    require(stat.S_ISREG(observed.st_mode), f"{label} is not a regular file: {path}")
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise StoreError(f"cannot resolve {label} {path}: {exc}") from exc
    require(resolved == path, f"{label} is redirected: {path} -> {resolved}")
    require(observed.st_dev == device, f"{label} is on another filesystem: {path}")


def load_layout(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise StoreError(f"layout manifest cannot be read as YAML: {exc}") from exc
    require(isinstance(data, dict), "layout manifest root must be a mapping")
    return data


def verify(layout_path: Path, store: Path, require_management_roots: bool) -> dict[str, Any]:
    store_device = require_real_directory(store, "image-store root")
    require_real_file(layout_path, "layout manifest", store_device)
    layout = load_layout(layout_path)

    require(layout.get("root") == str(store), "layout manifest describes another store root")
    directories = layout.get("directories")
    require(isinstance(directories, list), "layout manifest directories must be a list")
    require(all(isinstance(item, str) for item in directories),
            "layout manifest directories must contain strings only")
    missing = sorted(REQUIRED_LAYOUT_DIRECTORIES - set(directories))
    require(not missing, f"layout manifest is missing required directories: {', '.join(missing)}")

    for relative in sorted(REQUIRED_LAYOUT_DIRECTORIES):
        path = store if relative == "" else store / relative
        require_real_directory(path, f"managed store directory {relative or '<root>'}", store_device)

    observed_management: list[str] = []
    for relative in MANAGEMENT_DIRECTORIES:
        path = store / relative
        if os.path.lexists(path):
            require_real_directory(path, f"guest management directory {relative}", store_device)
            observed_management.append(relative)
        elif require_management_roots:
            raise StoreError(f"guest management directory is missing: {path}")

    return {
        "status": "safe",
        "store": str(store),
        "device": store_device,
        "management_directories": observed_management,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--layout", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--require-management-roots", choices=("true", "false"), required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        layout_path = normalized_absolute(args.layout, "layout path")
        store = normalized_absolute(args.store, "store path")
        require(layout_path == store / "state/layout.yml",
                "layout path must be exactly <store>/state/layout.yml")
        result = verify(layout_path, store, args.require_management_roots == "true")
    except StoreError as exc:
        print(f"guest store refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
