#!/usr/bin/env python3
"""Validate and transactionally install private guest wallpaper bundles."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

THEMES = (
    "sakura-circuit",
    "neon-terminal",
    "moon-library",
    "glitch-lab",
)
SURFACES = ("desktop", "lockscreen")
SHA256_RE_LENGTH = 64
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ASSET_NAME_RE = re.compile(r"^[0-9]{2}\.png$")


class AssetError(ValueError):
    """A wallpaper bundle violates the private asset contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssetError(message)


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AssetError(f"manifest does not exist: {path}") from exc
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise AssetError(f"manifest cannot be read as YAML: {exc}") from exc
    require(isinstance(data, dict), "manifest root must be a mapping")
    return data


def within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def normalize_entry(
    source_root: Path,
    theme: str,
    surface: str,
    entry: Any,
) -> dict[str, str]:
    require(isinstance(entry, dict), f"{theme}.{surface} entries must be mappings")
    relative = entry.get("path")
    checksum = entry.get("sha256")
    require(isinstance(relative, str) and relative, f"{theme}.{surface} path is required")
    require(
        isinstance(checksum, str)
        and len(checksum) == SHA256_RE_LENGTH
        and all(char in "0123456789abcdef" for char in checksum),
        f"{theme}.{surface} sha256 must be lowercase hexadecimal",
    )
    relative_path = Path(relative)
    require(not relative_path.is_absolute(), f"asset path must be relative: {relative}")
    require(".." not in relative_path.parts, f"asset path escapes the bundle: {relative}")
    expected_prefix = Path("wallpapers") / theme / surface
    require(
        relative_path.parent == expected_prefix,
        f"asset path must live below {expected_prefix}: {relative}",
    )
    require(
        ASSET_NAME_RE.fullmatch(relative_path.name) is not None,
        f"asset filename must use the reviewed NN.png form: {relative}",
    )
    candidate = source_root / relative_path
    require(candidate.exists(), f"asset is missing: {relative}")
    require(not candidate.is_symlink(), f"asset is redirected: {relative}")
    source = candidate.resolve()
    require(within(source, source_root), f"asset path escaped source root: {relative}")
    require(source.is_file(), f"asset is not a regular file: {relative}")
    with source.open("rb") as stream:
        require(stream.read(8) == PNG_SIGNATURE, f"asset has no PNG signature: {relative}")
    observed = file_sha256(source)
    require(observed == checksum, f"asset checksum mismatch: {relative}")
    return {
        "theme": theme,
        "surface": surface,
        "path": relative_path.as_posix(),
        "filename": relative_path.name,
        "sha256": checksum,
    }


def validate_bundle(source_root: Path, manifest_path: Path) -> list[dict[str, str]]:
    require(not source_root.is_symlink(), "bundle root must not be a symbolic link")
    source_root = source_root.resolve()
    require(source_root.is_dir(), f"bundle root is not a directory: {source_root}")
    require(manifest_path.exists(), f"manifest does not exist: {manifest_path}")
    require(not manifest_path.is_symlink(), "manifest must not be a symbolic link")
    manifest_path = manifest_path.resolve()
    require(within(manifest_path, source_root), "manifest must be inside the bundle root")
    manifest = load_manifest(manifest_path)
    require(manifest.get("schema_version") == 1, "asset manifest schema_version must be 1")
    themes = manifest.get("themes")
    require(isinstance(themes, dict), "asset manifest themes must be a mapping")
    require(set(themes) == set(THEMES), "asset manifest must contain exactly four reviewed themes")

    normalized: list[dict[str, str]] = []
    seen_paths: set[str] = set()
    for theme in THEMES:
        surfaces = themes.get(theme)
        require(isinstance(surfaces, dict), f"theme {theme} must be a mapping")
        require(set(surfaces) == set(SURFACES), f"theme {theme} needs desktop and lockscreen")
        hashes: dict[str, set[str]] = {}
        for surface in SURFACES:
            entries = surfaces.get(surface)
            require(isinstance(entries, list) and entries, f"{theme}.{surface} must not be empty")
            require(len(entries) <= 20, f"{theme}.{surface} may contain at most 20 assets")
            expected_names = {f"{index:02d}.png" for index in range(1, len(entries) + 1)}
            declared_names = {Path(str(entry.get("path", ""))).name for entry in entries if isinstance(entry, dict)}
            require(
                declared_names == expected_names,
                f"{theme}.{surface} must use a contiguous 01.png through {len(entries):02d}.png set",
            )
            hashes[surface] = set()
            for entry in entries:
                item = normalize_entry(source_root, theme, surface, entry)
                require(
                    item["sha256"] not in hashes[surface],
                    f"{theme}.{surface} contains duplicate image content",
                )
                require(item["path"] not in seen_paths, f"duplicate asset path: {item['path']}")
                seen_paths.add(item["path"])
                hashes[surface].add(item["sha256"])
                normalized.append(item)
        require(
            hashes["desktop"].isdisjoint(hashes["lockscreen"]),
            f"{theme} desktop and lockscreen pools must use distinct images",
        )
    return normalized


def install_bundle(source_root: Path, manifest_path: Path, target_root: Path) -> dict[str, Any]:
    items = validate_bundle(source_root, manifest_path)
    require(not target_root.is_symlink(), "target root must not be a symbolic link")
    target_root = target_root.resolve()
    target_root.mkdir(parents=True, exist_ok=True)
    target_root.chmod(0o755)
    changed = False

    for theme in THEMES:
        for surface in SURFACES:
            destination = target_root / theme / surface
            require(not destination.is_symlink(), f"target pool is redirected: {destination}")
            destination.mkdir(parents=True, exist_ok=True)
            destination.chmod(0o755)
            selected = [
                item for item in items
                if item["theme"] == theme and item["surface"] == surface
            ]
            wanted_names = {item["filename"] for item in selected}
            for stale in destination.glob("[0-9][0-9].png"):
                if stale.name not in wanted_names:
                    stale.unlink()
                    changed = True
            for item in selected:
                source = source_root / item["path"]
                target = destination / item["filename"]
                if target.is_file() and not target.is_symlink() and file_sha256(target) == item["sha256"]:
                    continue
                temporary_fd, temporary_name = tempfile.mkstemp(
                    prefix=f".{target.name}.",
                    dir=destination,
                )
                os.close(temporary_fd)
                temporary = Path(temporary_name)
                try:
                    shutil.copyfile(source, temporary)
                    temporary.chmod(0o644)
                    temporary.replace(target)
                finally:
                    if temporary.exists():
                        temporary.unlink()
                changed = True

    return {
        "changed": changed,
        "files": len(items),
        "themes": len(THEMES),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for name in ("validate", "install"):
        command = subparsers.add_parser(name)
        command.add_argument("--source", required=True)
        command.add_argument("--manifest", required=True)
        if name == "install":
            command.add_argument("--target", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        source = Path(args.source)
        manifest = Path(args.manifest)
        if args.command == "validate":
            result: dict[str, Any] = {
                "changed": False,
                "files": len(validate_bundle(source, manifest)),
                "themes": len(THEMES),
            }
        else:
            result = install_bundle(source, manifest, Path(args.target))
    except (AssetError, OSError) as exc:
        print(f"guest assets refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
