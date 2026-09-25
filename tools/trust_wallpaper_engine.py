#!/usr/bin/env python3
"""Pure planner for HyperLab trust-model wallpaper rotation.

This tool deliberately does not resolve trust, write compositor state,
change RGB, or gain privilege.

Its only authority is:

    reviewed host-owned trust identity
        +
    reviewed trust wallpaper manifest
        ->
    deterministic presentation plan

The future runtime bridge supplies the already-resolved trust identity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
import time
from pathlib import Path
from typing import Any

import yaml


SCHEMA_VERSION = 1

TRUST_ORDER = (
    "host",
    "clean",
    "dev",
    "services",
    "dirty",
    "lab",
)

TRUST_COLORS = {
    "host": "#8b949e",
    "clean": "#72f2a5",
    "dev": "#5b8cff",
    "services": "#35e4dd",
    "dirty": "#ff9d45",
    "lab": "#b184ff",
}


class EngineError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EngineError(message)


def digest(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def png_geometry(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]

    require(
        len(data) == 24,
        f"truncated PNG: {path}",
    )

    require(
        data[:8] == b"\x89PNG\r\n\x1a\n",
        f"invalid PNG signature: {path}",
    )

    return struct.unpack(">II", data[16:24])


def load_pool(root: Path) -> dict[str, Any]:
    manifest_path = root / "manifest.yml"

    require(
        manifest_path.is_file(),
        f"pool manifest missing: {manifest_path}",
    )

    doc = yaml.safe_load(
        manifest_path.read_text(encoding="utf-8")
    )

    require(
        isinstance(doc, dict),
        "pool manifest must be a mapping",
    )

    require(doc.get("version") == 2, "pool version changed")
    require(
        doc.get("id") == "hyperlab-trust-v2",
        "unexpected pool id",
    )

    # Candidate is intentional until visual acceptance.
    require(
        doc.get("status") == "candidate",
        "wallpaper artwork status changed unexpectedly",
    )

    require(
        doc.get("kind") == "trust-wallpaper-pool",
        "unexpected pool kind",
    )

    require(
        doc.get("geometry") == {
            "width": 1672,
            "height": 941,
            "aspect_ratio": "1672:941",
        },
        "wallpaper geometry contract changed",
    )

    rotation = doc.get("rotation")

    require(
        rotation == {
            "enabled": True,
            "interval_minutes": 30,
            "strategy": "cycle-within-current-trust",
            "switch_on_trust_change": True,
            "cross_trust_rotation": False,
        },
        "rotation policy changed",
    )

    authority = doc.get("authority")

    require(
        authority == {
            "source": "host-owned-trust",
            "wallpaper_may_set_trust": False,
            "rgb_follows_wallpaper": False,
            "rgb_follows_trust": True,
        },
        "trust authority boundary changed",
    )

    identities = doc.get("identities")

    require(
        isinstance(identities, dict),
        "identities must be a mapping",
    )

    require(
        set(identities) == set(TRUST_ORDER),
        "trust identity set changed",
    )

    for identity in TRUST_ORDER:
        entry = identities[identity]

        require(
            entry.get("trust_color")
            == TRUST_COLORS[identity],
            f"trust color changed: {identity}",
        )

        wallpapers = entry.get("wallpapers")

        require(
            isinstance(wallpapers, list),
            f"wallpaper list missing: {identity}",
        )

        require(
            len(wallpapers) >= 2,
            f"trust pool too small: {identity}",
        )

        require(
            entry.get("count") == len(wallpapers),
            f"manifest count drift: {identity}",
        )

        expected_prefix = f"images/{identity}/"
        observed_files: set[str] = set()

        for item in wallpapers:
            require(
                isinstance(item, dict),
                f"invalid wallpaper entry: {identity}",
            )

            relative = item.get("file")
            expected_hash = item.get("sha256")

            require(
                isinstance(relative, str)
                and relative.startswith(expected_prefix),
                f"cross-trust wallpaper path: {identity}",
            )

            relative_path = Path(relative)

            require(
                not relative_path.is_absolute()
                and ".." not in relative_path.parts,
                f"unsafe wallpaper path: {relative}",
            )

            require(
                relative not in observed_files,
                f"duplicate wallpaper: {relative}",
            )

            observed_files.add(relative)

            wallpaper = root / relative

            require(
                wallpaper.is_file(),
                f"wallpaper missing: {wallpaper}",
            )

            require(
                png_geometry(wallpaper) == (1672, 941),
                f"wallpaper geometry drift: {wallpaper}",
            )

            require(
                isinstance(expected_hash, str)
                and digest(wallpaper) == expected_hash,
                f"wallpaper hash drift: {wallpaper}",
            )

    return doc


def normalized_epoch(value: float) -> int:
    require(value >= 0, "epoch must be non-negative")
    return int(value)


def plan(
    root: Path,
    doc: dict[str, Any],
    trust: str,
    epoch: float,
) -> dict[str, Any]:
    require(
        trust in TRUST_ORDER,
        f"unsupported trust identity: {trust}",
    )

    interval_seconds = (
        int(doc["rotation"]["interval_minutes"])
        * 60
    )

    require(
        interval_seconds >= 60,
        "rotation interval is unexpectedly short",
    )

    now = normalized_epoch(epoch)
    bucket = now // interval_seconds

    entry = doc["identities"][trust]

    wallpapers = sorted(
        entry["wallpapers"],
        key=lambda item: item["file"],
    )

    count = len(wallpapers)
    index = bucket % count

    selected = wallpapers[index]
    selected_path = (root / selected["file"]).resolve()

    # Defense in depth: after resolution the asset must remain inside root.
    resolved_root = root.resolve()

    require(
        selected_path.is_relative_to(resolved_root),
        "selected wallpaper escaped pool root",
    )

    trust_hex = TRUST_COLORS[trust]
    rgb = trust_hex.removeprefix("#")

    next_boundary = (
        (bucket + 1)
        * interval_seconds
    )

    return {
        "schema": SCHEMA_VERSION,
        "pool_id": doc["id"],
        "pool_status": doc["status"],
        "trust": trust,
        "trust_source": "host-owned",
        "trust_color": trust_hex,
        "wallpaper": str(selected_path),
        "wallpaper_relative": selected["file"],
        "wallpaper_sha256": selected["sha256"],
        "wallpaper_index": index + 1,
        "wallpaper_count": count,
        "rotation_bucket": bucket,
        "rotation_interval_seconds": interval_seconds,
        "next_rotation_epoch": next_boundary,
        "seconds_until_rotation": next_boundary - now,
        "cross_trust_rotation": False,
        "wallpaper_may_set_trust": False,
        "rgb_follows_wallpaper": False,
        "rgb_follows_trust": True,
        "rgb_provider": "hyperlab-nitro-control",
        "rgb_zones": [rgb, rgb, rgb, rgb],
    }


def transition_plan(
    root: Path,
    doc: dict[str, Any],
    previous: str,
    current: str,
    epoch: float,
) -> dict[str, Any]:
    result = plan(
        root,
        doc,
        current,
        epoch,
    )

    if previous == current:
        reason = "rotation-or-refresh"
    elif previous in TRUST_ORDER:
        reason = "trust-change"
    elif previous == "none":
        reason = "initial"
    else:
        raise EngineError(
            f"unsupported previous trust identity: {previous}"
        )

    result["previous_trust"] = previous
    result["transition_reason"] = reason

    return result


def emit(payload: dict[str, Any]) -> None:
    print(
        json.dumps(
            payload,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()

    result.add_argument(
        "--pool-root",
        type=Path,
        required=True,
        help="Root containing hyperlab-trust-v2 manifest.yml",
    )

    sub = result.add_subparsers(
        dest="command",
        required=True,
    )

    sub.add_parser("validate")

    plan_parser = sub.add_parser("plan")

    plan_parser.add_argument(
        "--trust",
        choices=TRUST_ORDER,
        required=True,
    )

    plan_parser.add_argument(
        "--epoch",
        type=float,
        default=None,
    )

    transition = sub.add_parser("transition")

    transition.add_argument(
        "--previous",
        required=True,
        help="none or previous reviewed trust identity",
    )

    transition.add_argument(
        "--trust",
        choices=TRUST_ORDER,
        required=True,
    )

    transition.add_argument(
        "--epoch",
        type=float,
        default=None,
    )

    return result


def main() -> int:
    args = parser().parse_args()

    try:
        doc = load_pool(args.pool_root)

        if args.command == "validate":
            print("TRUST_WALLPAPER_ENGINE_SCHEMA=1")
            print(f"TRUST_POOL_ID={doc['id']}")
            print(
                "TRUST_ROTATION_MINUTES="
                f"{doc['rotation']['interval_minutes']}"
            )
            print(
                "TRUST_IDENTITIES="
                + ",".join(TRUST_ORDER)
            )
            print("TRUST_WALLPAPER_ENGINE=PASS")
            return 0

        epoch = (
            time.time()
            if args.epoch is None
            else args.epoch
        )

        if args.command == "plan":
            emit(
                plan(
                    args.pool_root,
                    doc,
                    args.trust,
                    epoch,
                )
            )
            return 0

        if args.command == "transition":
            emit(
                transition_plan(
                    args.pool_root,
                    doc,
                    args.previous,
                    args.trust,
                    epoch,
                )
            )
            return 0

        raise AssertionError("unreachable")

    except (
        EngineError,
        KeyError,
        OSError,
        TypeError,
        yaml.YAMLError,
    ) as exc:
        print(
            f"HyperLab trust wallpaper engine: {exc}",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
