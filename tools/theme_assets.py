#!/usr/bin/env python3
"""Validate canonical HyperLab visual asset sets."""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path

import yaml


EXPECTED_SIZE = (1672, 941)


def fail(message: str) -> None:
    raise ValueError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]

    if len(data) != 24:
        fail(f"truncated PNG: {path}")

    if data[:8] != b"\x89PNG\r\n\x1a\n":
        fail(f"invalid PNG: {path}")

    return struct.unpack(">II", data[16:24])


def validate(root: Path) -> dict:
    manifest_path = root / "manifest.yml"

    if not manifest_path.is_file():
        fail(f"manifest missing: {manifest_path}")

    doc = yaml.safe_load(
        manifest_path.read_text(encoding="utf-8")
    )

    if doc.get("version") != 1:
        fail("unsupported asset manifest version")

    if doc.get("id") != root.name:
        fail("asset-set directory/id mismatch")

    if doc.get("status") != "canonical":
        fail("asset set is not canonical")

    if doc.get("kind") != "wallpaper-set":
        fail("unexpected asset-set kind")

    geometry = doc.get("geometry")

    if geometry != {
        "width": 1672,
        "height": 941,
        "aspect_ratio": "1672:941",
    }:
        fail("canonical geometry changed")

    semantic = doc.get("semantic_policy", {})

    if semantic.get("trust_assignment") != "pending":
        fail("unreviewed trust assignment encoded")

    if semantic.get("theme_assignment") != "pending":
        fail("unreviewed theme assignment encoded")

    images = doc.get("images")

    if not isinstance(images, list) or len(images) != 10:
        fail("asset set must contain exactly ten images")

    observed_paths = set()
    observed_hashes = set()

    for expected_index, image in enumerate(
        images,
        start=1,
    ):
        if image.get("index") != expected_index:
            fail("asset ordering/index changed")

        if image.get("trust_identity") is not None:
            fail("trust identity assigned before design review")

        if image.get("theme_role") is not None:
            fail("theme role assigned before design review")

        relative = Path(image["file"])

        if relative.is_absolute() or ".." in relative.parts:
            fail("unsafe relative asset path")

        image_path = root / relative

        if not image_path.is_file():
            fail(f"missing asset: {image_path}")

        if png_size(image_path) != EXPECTED_SIZE:
            fail(f"geometry mismatch: {image_path}")

        observed = sha256(image_path)

        if observed != image["sha256"]:
            fail(f"hash mismatch: {image_path}")

        if image["file"] in observed_paths:
            fail("duplicate asset path")

        if observed in observed_hashes:
            fail("duplicate asset payload")

        observed_paths.add(image["file"])
        observed_hashes.add(observed)

    actual_paths = {
        str(path.relative_to(root))
        for path in root.rglob("*.png")
    }

    if actual_paths != observed_paths:
        fail("manifest/filesystem PNG set differs")

    return doc


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )

    parser.add_argument(
        "asset_set",
        nargs="?",
        default="hyperlab-symbols-v1",
    )

    args = parser.parse_args()

    try:
        doc = validate(
            args.repo / "themes/assets" / args.asset_set
        )
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(
            f"HyperLab theme assets: {exc}",
            file=sys.stderr,
        )
        return 1

    print(f"ASSET_SET={doc['id']}")
    print(f"ASSET_COUNT={len(doc['images'])}")
    print("ASSET_GEOMETRY=1672x941")
    print(
        "TRUST_ASSIGNMENT="
        + doc["semantic_policy"]["trust_assignment"]
    )
    print("THEME_ASSET_VALIDATOR=PASS")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
