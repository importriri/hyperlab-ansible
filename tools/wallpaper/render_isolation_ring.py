#!/usr/bin/env python3
"""Render the HyperLab product identity wallpaper family deterministically.

"Isolation Ring" is the product signature at wallpaper scale: two vertically cut
annulus segments with gaps above and below a containment ring and core, cut
into a graphite ground as architectural relief under a broad upper-left light. It is the same geometry the shell draws at 18
units in the rail, so the product is recognisable from the lock screen to the
top bar without a second logo.

It carries no words, no reticles, no telemetry, no provenance colours and no
state-like marks. It is a ground for the shell and it grants no authority:
wallpaper never encodes trust.

Two variants are produced from one geometry:

    desktop   the everyday ground, mark at ~46% of the shorter side
    lock      darker and quieter, for a screen that must show nothing about
              the session behind it

Rendering uses Qt's software rasteriser through qmlscene, so the output is
byte-stable for a given Qt release.

    python3 tools/wallpaper/render_isolation_ring.py --out <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "roles/host_desktop_common/files/wallpapers"

# Native outputs plus the two aspect ratios the Nitro panel and the reviewed
# external modes actually use.
SIZES = {
    "3840x2160": (3840, 2160),
    "1920x1080": (1920, 1080),
    "2560x1600": (2560, 1600),
    "3440x1440": (3440, 1440),
}

SCENE = r"""
import QtQuick
import QtQuick.Window

Window {
    id: window
    width: WIDTH
    height: HEIGHT
    visible: true
    color: "#0b0e11"

    Canvas {
        id: art
        anchors.fill: parent
        renderStrategy: Canvas.Immediate

        // The mark sits slightly right of centre and slightly high, so the
        // rail above and any window below still read as the subject.
        readonly property real centreX: width * 0.52
        readonly property real centreY: height * 0.48
        readonly property real radius: Math.min(width, height) * DIAMETER / 2

        // Geometry B, shared numerically with IsolationGlyph.qml (ADR 0056).
        // The size and small-form constants describe the shared glyph family;
        // these wallpaper-sized marks always draw the full form.
        readonly property real radiusRatio: 0.46
        readonly property real arcInnerRatio: 0.685
        readonly property real cutRatio: 0.41
        readonly property real ringRadiusRatio: 0.555
        readonly property real ringStrokeRatio: 0.057
        readonly property real coreRadiusRatio: 0.413
        readonly property real smallCoreRadiusRatio: 0.435
        readonly property int smallThreshold: 33

        // A filled annulus segment. Both joins have the same x coordinate,
        // so the opening is a vertical band, never a radial or rounded cut.
        function arcPath(ctx, side) {
            const r = art.radius;
            const inner = r * art.arcInnerRatio;
            const cut = r * art.cutRatio;
            const outerY = Math.sqrt(r * r - cut * cut);
            const innerY = Math.sqrt(inner * inner - cut * cut);
            const outerAngle = Math.acos(art.cutRatio);
            const innerAngle = Math.acos(art.cutRatio / art.arcInnerRatio);
            const left = side < 0;
            ctx.beginPath();
            ctx.moveTo(art.centreX + side * cut, art.centreY - outerY);
            ctx.arc(art.centreX, art.centreY, r,
                    left ? Math.PI + outerAngle : -outerAngle,
                    left ? Math.PI - outerAngle : outerAngle, left);
            ctx.lineTo(art.centreX + side * cut, art.centreY + innerY);
            ctx.arc(art.centreX, art.centreY, inner,
                    left ? Math.PI - innerAngle : innerAngle,
                    left ? Math.PI + innerAngle : -innerAngle, !left);
            ctx.closePath();
        }

        function engravedArc(ctx, side, lineWidth, depth, light) {
            ctx.save();
            art.arcPath(ctx, side);
            ctx.fillStyle = "rgba(0, 0, 0, " + depth + ")";
            ctx.fill();
            ctx.restore();

            ctx.save();
            ctx.translate(-lineWidth * 0.22, -lineWidth * 0.22);
            art.arcPath(ctx, side);
            ctx.lineWidth = lineWidth * 0.5;
            ctx.lineJoin = "miter";
            ctx.strokeStyle = "rgba(226, 232, 238, " + light + ")";
            ctx.stroke();
            ctx.restore();
        }

        function ring(ctx, r, lineWidth, from, to, stroke) {
            ctx.beginPath();
            ctx.arc(art.centreX, art.centreY, r, from, to, false);
            ctx.lineWidth = lineWidth;
            ctx.strokeStyle = stroke;
            ctx.stroke();
        }

        // One engraved stroke: a dark recess with a lit upper-left lip, which
        // is what makes the mark read as cut into the ground rather than
        // drawn on top of it.
        function engraved(ctx, r, lineWidth, from, to, depth, light) {
            ctx.save();
            art.ring(ctx, r, lineWidth, from, to, "rgba(0, 0, 0, " + depth + ")");
            ctx.restore();

            ctx.save();
            ctx.translate(-lineWidth * 0.22, -lineWidth * 0.22);
            art.ring(
                ctx,
                r,
                lineWidth * 0.5,
                from,
                to,
                "rgba(226, 232, 238, " + light + ")"
            );
            ctx.restore();
        }

        function draw(ctx) {
            const w = width;
            const h = height;
            ctx.reset();

            // Ground: graphite, a broad soft light from the upper left, no
            // vignette crush and no colour cast.
            const base = ctx.createLinearGradient(0, 0, w * 0.35, h);
            base.addColorStop(0, "#151920");
            base.addColorStop(0.5, "#101319");
            base.addColorStop(1, "#0b0e13");
            ctx.fillStyle = base;
            ctx.fillRect(0, 0, w, h);

            const light = ctx.createRadialGradient(
                w * 0.20, h * 0.06, 0, w * 0.20, h * 0.06, w * 0.95
            );
            light.addColorStop(0, "rgba(255, 250, 244, " + GLOW + ")");
            light.addColorStop(0.55, "rgba(255, 250, 244, 0.018)");
            light.addColorStop(1, "rgba(255, 250, 244, 0)");
            ctx.fillStyle = light;
            ctx.fillRect(0, 0, w, h);

            const r = art.radius;
            const unit = Math.min(w, h) / 1080;

            // A very shallow pool inside the boundary, so the contained
            // region sits a fraction below the surrounding plane.
            const pool = ctx.createRadialGradient(
                art.centreX - r * 0.25, art.centreY - r * 0.3, r * 0.05,
                art.centreX, art.centreY, r
            );
            pool.addColorStop(0, "rgba(255, 252, 246, 0.022)");
            pool.addColorStop(0.7, "rgba(0, 0, 0, 0.05)");
            pool.addColorStop(1, "rgba(0, 0, 0, 0.14)");
            ctx.beginPath();
            ctx.arc(art.centreX, art.centreY, r, 0, Math.PI * 2, false);
            ctx.fillStyle = pool;
            ctx.fill();

            // Outer isolation boundary: filled arcs, gaps at top and bottom.
            const outer = 9 * unit;
            art.engravedArc(ctx, -1, outer, DEPTH, EDGE);
            art.engravedArc(ctx, 1, outer, DEPTH, EDGE);

            // Containment ring: closed, thinner, the boundary the core is
            // actually inside.
            art.engraved(ctx, r * art.ringRadiusRatio,
                         Math.max(1, r * art.ringStrokeRatio), 0, Math.PI * 2,
                         DEPTH * 0.85, EDGE * 0.8);

            // Contained core: a machined disc raised out of the pool, not a
            // glossy sphere. One flat face, one lit lip, one seated shadow.
            const core = r * art.coreRadiusRatio;

            ctx.beginPath();
            ctx.arc(
                art.centreX + core * 0.10,
                art.centreY + core * 0.14,
                core * 1.06,
                0, Math.PI * 2, false
            );
            ctx.fillStyle = "rgba(0, 0, 0, 0.34)";
            ctx.fill();

            const coreFill = ctx.createLinearGradient(
                art.centreX - core, art.centreY - core,
                art.centreX + core, art.centreY + core
            );
            coreFill.addColorStop(0, "rgba(198, 208, 218, " + CORE + ")");
            coreFill.addColorStop(1, "rgba(142, 153, 165, " + (CORE * 0.82) + ")");
            ctx.beginPath();
            ctx.arc(art.centreX, art.centreY, core, 0, Math.PI * 2, false);
            ctx.fillStyle = coreFill;
            ctx.fill();

            ctx.beginPath();
            ctx.arc(
                art.centreX, art.centreY, core - unit * 0.6,
                Math.PI * 1.05, Math.PI * 1.75, false
            );
            ctx.lineWidth = 1.4 * unit;
            ctx.strokeStyle = "rgba(240, 246, 252, " + (CORE * 0.42) + ")";
            ctx.stroke();
        }

        onPaint: {
            art.draw(getContext("2d"));
            art.grabToImage(function(result) {
                result.saveToFile("OUTFILE");
                Qt.quit();
            });
        }

        Component.onCompleted: requestPaint()
    }
}
"""

VARIANTS = {
    # name: (diameter fraction, ground glow, engraving depth, lit edge, core)
    "isolation-ring": (0.46, 0.070, 0.42, 0.26, 0.72),
    "isolation-ring-lock": (0.40, 0.045, 0.50, 0.18, 0.55),
}


def render(runner: str, size: tuple[int, int], variant: str, out: Path) -> None:
    diameter, glow, depth, edge, core = VARIANTS[variant]

    with tempfile.TemporaryDirectory(prefix="hyperlab-identity-") as directory:
        scene = Path(directory) / "scene.qml"
        scene.write_text(
            SCENE.replace("WIDTH", str(size[0]))
            .replace("HEIGHT", str(size[1]))
            .replace("DIAMETER", repr(diameter))
            .replace("GLOW", repr(glow))
            .replace("DEPTH", repr(depth))
            .replace("EDGE", repr(edge))
            .replace("CORE", repr(core))
            .replace("OUTFILE", str(out))
        )
        result = subprocess.run(
            [runner, str(scene)],
            capture_output=True,
            text=True,
            timeout=180,
            env={
                **os.environ,
                "QT_QPA_PLATFORM": "offscreen",
                "QT_QUICK_BACKEND": "software",
            },
            check=False,
        )

    if result.returncode or result.stderr.strip():
        raise SystemExit(
            f"render failed for {out.name}: {result.returncode} {result.stderr}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--print-hashes", action="store_true")
    args = parser.parse_args()

    runner = (
        shutil.which("qmlscene", path="/usr/lib/qt6/bin")
        or shutil.which("qmlscene6")
    )
    if not runner:
        raise SystemExit("Qt 6 qmlscene is required to render the wallpaper")

    args.out.mkdir(parents=True, exist_ok=True)

    produced: list[Path] = []
    for variant in VARIANTS:
        for name, size in SIZES.items():
            target = args.out / f"{variant}-{name}.png"
            render(runner, size, variant, target)
            produced.append(target)
            print(f"rendered {target.name}")

    if args.print_hashes:
        for target in produced:
            digest = hashlib.sha256(target.read_bytes()).hexdigest()
            print(f"{digest}  {target.name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
