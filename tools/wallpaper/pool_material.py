"""Seeded geometry B materials shared by static identity and pool wallpapers.

The only paint operation is an opaque native pixel buffer. Materials carry
no text, screen furniture or trust authority. Capture uses Qt's software backend.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import tempfile

SCENE = r"""
import QtQuick
import QtQuick.Window

Window {
    width: @@WIDTH@@
    height: @@HEIGHT@@
    visible: true
    color: "#07090d"

    Canvas {
        id: art
        anchors.fill: parent
        renderStrategy: Canvas.Immediate
        readonly property real centreX: width * @@CENTRE_X@@
        readonly property real centreY: height * @@CENTRE_Y@@
        readonly property real radius: Math.min(width, height) * @@RADIUS@@
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


def scene(size: tuple[int, int], centre: tuple[float, float], radius: float,
          quiet: float, tint: tuple[int, int, int], out: Path) -> str:
    """Build a native scene; radius is a fraction of the shorter side."""
    result = SCENE
    for key, value in {"WIDTH": str(size[0]), "HEIGHT": str(size[1]),
                       "CENTRE_X": repr(centre[0]), "CENTRE_Y": repr(centre[1]),
                       "RADIUS": repr(radius), "QUIET": repr(quiet),
                       "TINT": json.dumps(tint), "OUTFILE": json.dumps(str(out))}.items():
        result = result.replace(f"@@{key}@@", value)
    return result


def render(runner: str, source_text: str, out: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="hyperlab-trust-render-") as temporary:
        directory = Path(temporary)
        source = directory / "scene.qml"
        source.write_text(source_text, encoding="utf-8")
        result = subprocess.run([runner, str(source)], capture_output=True, text=True,
                                timeout=120, check=False, env={**os.environ,
                                "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                                "QT_FORCE_STDERR_LOGGING": "1", "QML_DISABLE_DISK_CACHE": "1", "XDG_CACHE_HOME": str(directory / "cache")})
    noise = [line for line in result.stderr.splitlines() if line.strip()
             and not line.startswith(("qt.tools.qmlscene.deprecated:", "QStandardPaths:"))]
    if result.returncode or noise or not out.is_file():
        raise ValueError(f"render failed for {out.name}: {result.returncode} {result.stderr}")
