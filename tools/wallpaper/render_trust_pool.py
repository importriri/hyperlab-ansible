#!/usr/bin/env python3
"""Render the wordless trust pool with Qt's software rasteriser.

Geometry B is shared with the product symbol (ADR 0056). Fixed coordinate
noise supplies grain; the palette supplies identity colours. Output is
byte-stable for a given Qt release. Wallpaper confers no trust authority.

    python3 tools/wallpaper/render_trust_pool.py --print-hashes
"""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat

import yaml

import pool_material

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "themes/assets/trust-pool-v3"
PALETTE = ROOT / "tools/palette/palette.yml"
IDENTITIES = ("host", "clean", "dev", "services", "dirty", "lab")
VARIANTS = {"01": (0.5, 0.33, 1.0), "02": (0.75, 0.26, 0.66)}


class UniqueLoader(yaml.SafeLoader):
    """Refuse duplicate mappings rather than silently replacing policy."""


def unique_mapping(loader: UniqueLoader, node: yaml.MappingNode) -> dict:
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in result:
            raise ValueError(f"duplicate palette key: {key}")
        result[key] = loader.construct_object(value_node, deep=True)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_palette(path: Path) -> dict[str, str]:
    path = path.absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("redirected palette input")
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, encoding="utf-8") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("palette must be a regular file")
        doc = yaml.load(stream, Loader=UniqueLoader)
    if not isinstance(doc, dict) or not isinstance(doc.get("domains"), dict):
        raise ValueError("palette domains missing")
    domains = doc["domains"]
    if set(domains) != {f"dom_{identity}" for identity in IDENTITIES}:
        raise ValueError("palette domain set changed")
    colours = {identity: domains[f"dom_{identity}"] for identity in IDENTITIES}
    if any(not isinstance(value, str) or not re.fullmatch(r"#[0-9a-fA-F]{6}", value)
           for value in colours.values()):
        raise ValueError("palette domain colour must be six-digit RGB")
    return colours


def scene(colour: str, identity: str, variant: str, out: Path) -> str:
    centre, radius, quiet = VARIANTS[variant]
    tint = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
    if identity == "host":
        neutral = round(tint[0] * 0.2126 + tint[1] * 0.7152 + tint[2] * 0.0722)
        tint = [neutral] * 3
    return pool_material.scene((1672, 941), (centre, 0.5), radius, quiet, tuple(tint), out)


def render(runner: str, colour: str, identity: str, variant: str, out: Path) -> None:
    pool_material.render(runner, scene(colour, identity, variant, out), out)


class ManifestDumper(yaml.SafeDumper):
    """Keep block sequences indented like the repository's YAML sources."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        return super().increase_indent(flow, False)


def manifest_text(manifest: dict) -> str:
    return yaml.dump(manifest, Dumper=ManifestDumper, sort_keys=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--print-hashes", action="store_true")
    args = parser.parse_args()
    colours = load_palette(PALETTE)
    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    if not runner:
        raise SystemExit("Qt 6 qmlscene is required to render the wallpaper")
    out = args.out.absolute()
    manifest = {
        "version": 2, "id": "trust-pool-v3", "name": "HyperLab Trust Wallpaper Pool v3",
        "status": "candidate", "kind": "trust-wallpaper-pool",
        "geometry": {"width": 1672, "height": 941, "aspect_ratio": "1672:941"},
        "rotation": {"enabled": True, "interval_minutes": 30,
                     "strategy": "cycle-within-current-trust", "switch_on_trust_change": True,
                     "cross_trust_rotation": False},
        "authority": {"source": "host-owned-trust", "wallpaper_may_set_trust": False,
                      "rgb_follows_wallpaper": False, "rgb_follows_trust": True},
        "identities": {},
    }
    for identity, colour in colours.items():
        wallpapers = []
        for variant in VARIANTS:
            relative = Path(f"images/{identity}/{variant}.png")
            target = out / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            render(runner, colour, identity, variant, target)
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            wallpapers.append({"file": relative.as_posix(), "sha256": digest})
            if args.print_hashes:
                print(f"{digest}  {relative.as_posix()}", flush=True)
        manifest["identities"][identity] = {"trust_color": colour, "count": 2, "wallpapers": wallpapers}
    (out / "manifest.yml").write_text(manifest_text(manifest), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
