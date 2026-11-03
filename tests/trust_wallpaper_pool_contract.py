#!/usr/bin/env python3
"""Contract for the candidate HyperLab rotating trust wallpaper pool."""

from __future__ import annotations

import hashlib
import struct
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
POOL = ROOT / "themes/assets/hyperlab-trust-v2"

COLORS = {
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
            f"HyperLab trust wallpaper pool contract: {message}"
        )


def digest(path: Path) -> str:
    return hashlib.sha256(
        path.read_bytes()
    ).hexdigest()


def size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()[:24]

    require(
        len(data) == 24
        and data[:8] == b"\x89PNG\r\n\x1a\n",
        f"invalid PNG: {path}",
    )

    return struct.unpack(">II", data[16:24])


def check_pool(pool: Path, pool_id: str, colours: dict[str, str]) -> None:
    manifest = pool / "manifest.yml"
    require(manifest.is_file(), "manifest missing")

    doc = yaml.safe_load(
        manifest.read_text(encoding="utf-8")
    )

    require(doc["version"] == 2, "version changed")
    require(
        doc["id"] == pool_id,
        "pool id changed",
    )
    require(
        doc["status"] == "candidate",
        "unaccepted artwork became canonical",
    )

    require(
        doc["rotation"] == {
            "enabled": True,
            "interval_minutes": 30,
            "strategy": "cycle-within-current-trust",
            "switch_on_trust_change": True,
            "cross_trust_rotation": False,
        },
        "rotation policy changed",
    )

    require(
        doc["authority"] == {
            "source": "host-owned-trust",
            "wallpaper_may_set_trust": False,
            "rgb_follows_wallpaper": False,
            "rgb_follows_trust": True,
        },
        "trust authority boundary changed",
    )

    identities = doc["identities"]

    require(
        set(identities) == set(colours),
        "trust identity set changed",
    )

    count = 0

    for identity, colour in colours.items():
        entry = identities[identity]

        require(
            entry["trust_color"] == colour,
            f"semantic colour changed: {identity}",
        )

        require(
            entry["count"] == 2,
            f"pool size changed: {identity}",
        )

        require(
            len(entry["wallpapers"]) == 2,
            f"wallpaper list changed: {identity}",
        )

        expected = {
            f"images/{identity}/01.png",
            f"images/{identity}/02.png",
        }

        observed = {
            item["file"]
            for item in entry["wallpapers"]
        }

        require(
            observed == expected,
            f"wrong wallpaper paths: {identity}",
        )

        for item in entry["wallpapers"]:
            wallpaper = pool / item["file"]

            require(
                wallpaper.is_file(),
                f"missing: {wallpaper}",
            )

            require(
                size(wallpaper) == (1672, 941),
                f"wrong geometry: {wallpaper}",
            )

            require(
                digest(wallpaper) == item["sha256"],
                f"hash drift: {wallpaper}",
            )

            count += 1

    require(count == 12, "total pool size changed")

    filesystem = list(
        (pool / "images").glob("*/*.png")
    )

    require(
        len(filesystem) == 12,
        "unexpected wallpaper filesystem count",
    )


def main() -> int:
    check_pool(POOL, "hyperlab-trust-v2", COLORS)
    domains = yaml.safe_load((ROOT / "tools/palette/palette.yml").read_text())["domains"]
    colours = {identity: domains[f"dom_{identity}"] for identity in COLORS}
    check_pool(ROOT / "themes/assets/trust-pool-v3", "trust-pool-v3", colours)
    print("HyperLab candidate rotating trust wallpaper pools contract: OK (v2 rollback, v3)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
