#!/usr/bin/env python3
"""Validate repository schemas and, when supplied, one safe selector."""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


class SelectorError(ValueError):
    pass


def within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def resolve_selector(root: Path, value: str, directory: str, label: str) -> Path:
    target_root = (root / directory).resolve()
    path = Path(value)
    path = (root / path).resolve() if not path.is_absolute() else path.resolve()
    if not within(path, target_root):
        raise SelectorError(f"{label} must resolve below {directory}/")
    if not path.is_file() or path.is_symlink():
        raise SelectorError(f"{label} is not one regular checked-in file: {path}")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--spec")
    group.add_argument("--manifest")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    selected: Path | None = None
    try:
        if args.spec:
            selected = resolve_selector(root, args.spec, "vm-specs", "guest_spec")
        elif args.manifest:
            selected = resolve_selector(root, args.manifest, "images", "image_factory_manifest")
    except (OSError, SelectorError) as exc:
        print(f"schema selector refused: {exc}", file=sys.stderr)
        return 2
    validator = root / "tests/schema_validate.py"
    result = subprocess.run(
        [sys.executable, str(validator)],
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stdout.write(result.stdout)
        sys.stderr.write(result.stderr)
        return result.returncode
    suffix = "repository" if selected is None else str(selected.relative_to(root))
    print(f"schema selector: OK ({suffix})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
