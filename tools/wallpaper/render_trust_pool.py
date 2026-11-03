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
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "themes/assets/trust-pool-v3"
PALETTE = ROOT / "tools/palette/palette.yml"
IDENTITIES = ("host", "clean", "dev", "services", "dirty", "lab")
VARIANTS = {"01": (0.5, 0.33, 1.0), "02": (0.75, 0.26, 0.66)}

SCENE = r"""
import QtQuick
import QtQuick.Window

Window {
    width: 1672
    height: 941
    visible: true
    color: "#07090d"

    Canvas {
        id: art
        anchors.fill: parent
        renderStrategy: Canvas.Immediate
        readonly property real centreX: width * @@CENTRE@@
        readonly property real centreY: height * 0.5
        readonly property real radius: height * @@RADIUS@@
        readonly property real quiet: @@QUIET@@
        readonly property var tint: @@TINT@@

        // Geometry B: annulus with vertical cuts, closed ring, contained core.
        readonly property real arcInnerRatio: 0.685
        readonly property real cutRatio: 0.41
        readonly property real ringRadiusRatio: 0.555
        readonly property real ringStrokeRatio: 0.057
        readonly property real coreRadiusRatio: 0.413

        function shader() {
            const centreX = art.centreX, centreY = art.centreY, radius = art.radius;
            const width = art.width, height = art.height, quiet = art.quiet, tint = art.tint;
            const arcInnerRatio = art.arcInnerRatio, cutRatio = art.cutRatio;
            const ringRadiusRatio = art.ringRadiusRatio, ringStrokeRatio = art.ringStrokeRatio;
            const coreRadiusRatio = art.coreRadiusRatio;
            function clamp(value) { return Math.max(0, Math.min(1, value)); }

            // Integer coordinate hashing, fixed seeds, no clock or ambient entropy.
            function noise(x, y, seed) {
                let n = Math.imul(Math.floor(x), 374761393)
                      + Math.imul(Math.floor(y), 668265263) + seed;
                n = Math.imul(n ^ (n >>> 13), 1274126177);
                return ((n ^ (n >>> 16)) >>> 0) / 4294967295 - 0.5;
            }

            function pixel(x, y) {
                const dx = x - centreX, dy = y - centreY;
                const d = Math.sqrt(dx*dx + dy*dy);
                const light = clamp(1 - (x / width + y / height) * 0.5);
                const fine = noise(x, y, 173) * 2.2;
                const ground = [9 + light * 5 + fine,
                                11 + light * 6 + fine,
                                16 + light * 7 + fine];
                const stone = noise(x, y, 941) * 9
                            + noise(x / 3, y / 3, 1672) * 7
                            + noise(x / 11, y / 11, 3181) * 4;
                const lit = clamp(0.65 - (dx + dy) / radius * 0.16);
                const arc = clamp(radius - d + 0.5)
                          * clamp(d - radius * arcInnerRatio + 0.5)
                          * clamp(Math.abs(dx) - radius * cutRatio + 0.5);
                const ring = clamp(radius * ringStrokeRatio / 2
                           - Math.abs(d - radius * ringRadiusRatio) + 0.5);
                const grey = (100 + lit * 91 + stone);
                const ringGrey = (77 + lit * 70 + stone * 0.5);
                const result = ground.map(channel =>
                    channel * (1 - arc * quiet) + grey * arc * quiet);
                for (let channel = 0; channel < 3; channel++)
                    result[channel] = result[channel] * (1 - ring * quiet)
                                    + ringGrey * ring * quiet;

                // The entire sphere material is clipped to its own edge. A soft
                // coloured rim and upper-left surface light surround a dark centre.
                const core = radius * coreRadiusRatio;
                const coverage = clamp(core - d + 0.5);
                if (coverage > 0) {
                    const nx = dx / core, ny = dy / core;
                    const t = Math.min(1, d / core);
                    const nz = Math.sqrt(Math.max(0, 1 - t*t));
                    const diffuse = Math.max(0, -nx * 0.50 - ny * 0.65 + nz * 0.22);
                    const shade = 0.13 + 0.31 * Math.pow(t, 3) + diffuse * 0.14;
                    const texture = noise(x, y, 5723) * 5
                                  + noise(x / 3, y / 3, 191) * 2;
                    for (let channel = 0; channel < 3; channel++) {
                        const surface = 4 + tint[channel] * shade + texture;
                        result[channel] = result[channel] * (1 - coverage)
                                        + surface * coverage * quiet;
                    }
                }
                return result;
            }

            return pixel;
        }

        function sample(x, y) { return shader()(x, y); }

        function draw(ctx) {
            const pixel = shader();
            const pixels = ctx.createImageData(width, height);
            const data = pixels.data;
            let offset = 0;
            for (let y = 0; y < height; y++) {
                for (let x = 0; x < width; x++) {
                    const rgb = pixel(x + 0.5, y + 0.5);
                    data[offset++] = Math.round(rgb[0]);
                    data[offset++] = Math.round(rgb[1]);
                    data[offset++] = Math.round(rgb[2]);
                    data[offset++] = 255;
                }
            }
            ctx.putImageData(pixels, 0, 0, 0, 0, width, height);
        }

        property bool painted: false
        onPaint: {
            if (painted) return;
            painted = true;
            art.draw(getContext("2d"));
            art.grabToImage(function(result) {
                if (!result.saveToFile(@@OUTFILE@@)) {
                    console.error("Could not save wallpaper");
                    Qt.exit(1);
                    return;
                }
                Qt.quit();
            });
        }
        Component.onCompleted: requestPaint()
    }
}
"""


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
    result = SCENE
    for key, value in {"CENTRE": repr(centre), "RADIUS": repr(radius), "QUIET": repr(quiet),
                       "TINT": json.dumps(tint), "OUTFILE": json.dumps(str(out))}.items():
        result = result.replace(f"@@{key}@@", value)
    return result


def render(runner: str, colour: str, identity: str, variant: str, out: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="hyperlab-trust-render-") as temporary:
        directory = Path(temporary)
        source = directory / "scene.qml"
        source.write_text(scene(colour, identity, variant, out), encoding="utf-8")
        result = subprocess.run([runner, str(source)], capture_output=True, text=True,
                                timeout=120, check=False, env={**os.environ,
                                "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                                "QT_FORCE_STDERR_LOGGING": "1", "QML_DISABLE_DISK_CACHE": "1", "XDG_CACHE_HOME": str(directory / "cache")})
    noise = [line for line in result.stderr.splitlines() if line.strip()
             and not line.startswith(("qt.tools.qmlscene.deprecated:", "QStandardPaths:"))]
    if result.returncode or noise or not out.is_file():
        raise ValueError(f"render failed for {identity}/{variant}: {result.returncode} {result.stderr}")


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
