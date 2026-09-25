#!/usr/bin/env python3
"""Render the HyperLab product wallpaper "Contained Planes" deterministically.

An original architectural still life: one broad graphite foundation carrying
three shallow enclosures with clear air gaps, drawn in an orthographic
three-quarter view under a broad upper-left light. It contains no words,
logos, reticles, provenance colours or state-like marks; it is a ground for
the shell, never an information layer, and it grants no authority.

The master is 3840x2160. Art-directed crops for 1920x1080, 2560x1600 and
3440x1440 keep the object group near 72% width / 25% height so the overview
below stays quiet. Rendering uses Qt's software rasteriser through qmlscene,
so the output is byte-stable for a given Qt release.

    python3 tools/wallpaper/render_contained_planes.py --out <dir>
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT = ROOT / "roles/host_desktop_common/files/wallpapers"

MASTER = (3840, 2160)
CROPS = {
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
    color: "#101316"

    Canvas {
        id: art
        anchors.fill: parent
        renderStrategy: Canvas.Immediate

        // Orthographic three-quarter view: azimuth 34 degrees, elevation 20.
        readonly property real azimuth: 34 * Math.PI / 180
        readonly property real elevation: 20 * Math.PI / 180
        readonly property real unit: width / 3840

        function project(x, y, z, cx, cy) {
            const sx = x * Math.cos(art.azimuth) - y * Math.sin(art.azimuth);
            const depth = x * Math.sin(art.azimuth) + y * Math.cos(art.azimuth);
            const sy = -z * Math.cos(art.elevation) + depth * Math.sin(art.elevation);
            return [cx + sx * art.unit, cy + sy * art.unit];
        }

        function polygon(ctx, points) {
            ctx.beginPath();
            ctx.moveTo(points[0][0], points[0][1]);
            for (let i = 1; i < points.length; i++) ctx.lineTo(points[i][0], points[i][1]);
            ctx.closePath();
        }

        // A box with its origin at (x0, y0) on plane z0, size (w, d, h).
        // Faces: top, left (toward viewer, -y), right (toward viewer, +x).
        function box(ctx, cx, cy, x0, y0, z0, w, d, h, tone) {
            const p = (x, y, z) => art.project(x, y, z, cx, cy);
            const top = [p(x0, y0, z0 + h), p(x0 + w, y0, z0 + h), p(x0 + w, y0 + d, z0 + h), p(x0, y0 + d, z0 + h)];
            const left = [p(x0, y0, z0), p(x0 + w, y0, z0), p(x0 + w, y0, z0 + h), p(x0, y0, z0 + h)];
            const right = [p(x0 + w, y0, z0), p(x0 + w, y0 + d, z0), p(x0 + w, y0 + d, z0 + h), p(x0 + w, y0, z0 + h)];

            art.polygon(ctx, right);
            ctx.fillStyle = tone.right;
            ctx.fill();
            art.polygon(ctx, left);
            ctx.fillStyle = tone.left;
            ctx.fill();

            // Top face with a soft directional gradient from the upper-left.
            const g = ctx.createLinearGradient(top[0][0], top[0][1], top[2][0], top[2][1]);
            g.addColorStop(0, tone.topLight);
            g.addColorStop(1, tone.topDark);
            art.polygon(ctx, top);
            ctx.fillStyle = g;
            ctx.fill();

            // Controlled edge highlight along the lit edges only.
            ctx.strokeStyle = tone.edge;
            ctx.lineWidth = Math.max(1, 1.5 * art.unit);
            ctx.beginPath();
            ctx.moveTo(top[3][0], top[3][1]);
            ctx.lineTo(top[0][0], top[0][1]);
            ctx.lineTo(top[1][0], top[1][1]);
            ctx.stroke();
        }

        // Narrow contact shadow on the plane the box rests on.
        function contactShadow(ctx, cx, cy, x0, y0, z0, w, d, spread, alpha) {
            const p = (x, y) => art.project(x, y, z0, cx, cy);
            const s = spread;
            art.polygon(ctx, [p(x0 - s * 0.4, y0 - s * 0.4), p(x0 + w + s * 1.2, y0 - s * 0.4),
                              p(x0 + w + s * 1.2, y0 + d + s * 1.2), p(x0 - s * 0.4, y0 + d + s * 1.2)]);
            ctx.save();
            ctx.shadowColor = "rgba(0, 0, 0, " + alpha + ")";
            ctx.shadowBlur = 42 * art.unit;
            ctx.fillStyle = "rgba(0, 0, 0, " + (alpha * 0.22) + ")";
            ctx.fill();
            ctx.restore();
        }

        onPaint: {
            const ctx = getContext("2d");
            const w = width;
            const h = height;
            ctx.reset();

            // Ground: graphite with a broad, soft upper-left light and a
            // barely cooler lower half. No vignette crush.
            const base = ctx.createLinearGradient(0, 0, w * 0.35, h);
            base.addColorStop(0, "#161a1e");
            base.addColorStop(0.5, "#111417");
            base.addColorStop(1, "#0e1114");
            ctx.fillStyle = base;
            ctx.fillRect(0, 0, w, h);

            const light = ctx.createRadialGradient(w * 0.18, h * 0.05, 0, w * 0.18, h * 0.05, w * 0.95);
            light.addColorStop(0, "rgba(255, 250, 244, 0.075)");
            light.addColorStop(0.55, "rgba(255, 250, 244, 0.02)");
            light.addColorStop(1, "rgba(255, 250, 244, 0)");
            ctx.fillStyle = light;
            ctx.fillRect(0, 0, w, h);

            // Object group anchored near 72% width, 25% height.
            const cx = w * 0.72;
            const cy = h * 0.25;

            const graphite = {
                topLight: "#3a4047", topDark: "#2a2f35", left: "#1d2126", right: "#171a1e",
                edge: "rgba(214, 205, 194, 0.22)"
            };
            const charcoal = {
                topLight: "#464c53", topDark: "#333940", left: "#22262b", right: "#1a1d21",
                edge: "rgba(224, 214, 202, 0.30)"
            };
            const ceramic = {
                topLight: "#5a5f64", topDark: "#41464c", left: "#2b2f34", right: "#202327",
                edge: "rgba(232, 223, 210, 0.38)"
            };

            // Foundation: broad and low.
            const fw = 1180, fd = 720, fh = 36;
            const fx = -fw / 2, fy = -fd / 2;
            art.contactShadow(ctx, cx, cy, fx, fy, -fh, fw, fd, 60, 0.55);
            art.box(ctx, cx, cy, fx, fy, -fh, fw, fd, fh, graphite);

            // Three shallow enclosures, asymmetric, with air gaps. Painter's
            // order: farthest first. One is displaced toward the front edge
            // to show its independent boundary.
            const enclosures = [
                { x: fx + 110, y: fy + 420, w: 400, d: 250, h: 62, tone: charcoal },
                { x: fx + 640, y: fy + 380, w: 470, d: 300, h: 74, tone: ceramic },
                { x: fx + 560, y: fy - 40, w: 350, d: 300, h: 56, tone: charcoal }
            ];
            // Larger x + y is nearer the viewer in this projection; draw far first.
            enclosures.sort((a, b) => (a.x + a.y) - (b.x + b.y));
            for (const e of enclosures) {
                art.contactShadow(ctx, cx, cy, e.x, e.y, 0, e.w, e.d, 26, 0.5);
                art.box(ctx, cx, cy, e.x, e.y, 0, e.w, e.d, e.h, e.tone);
            }
        }
    }

    Timer {
        interval: 400
        running: true
        onTriggered: window.contentItem.grabToImage(result => {
            if (!result.saveToFile("OUTFILE")) {
                console.error("wallpaper save failed");
                Qt.exit(1);
                return;
            }
            Qt.quit();
        })
    }
}
"""


def render(runner: str, size: tuple[int, int], out: Path) -> None:
    with tempfile.TemporaryDirectory(prefix="hyperlab-wallpaper-") as d:
        scene = Path(d) / "scene.qml"
        scene.write_text(
            SCENE.replace("WIDTH", str(size[0]))
            .replace("HEIGHT", str(size[1]))
            .replace("OUTFILE", str(out))
        )
        result = subprocess.run(
            [runner, str(scene)],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software"},
            check=False,
        )
    if result.returncode or result.stderr.strip():
        raise SystemExit(f"render failed for {out.name}: {result.returncode} {result.stderr}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--master-only", action="store_true")
    args = parser.parse_args()

    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    if not runner:
        raise SystemExit("Qt 6 qmlscene is required to render the wallpaper")

    args.out.mkdir(parents=True, exist_ok=True)
    render(runner, MASTER, args.out / "contained-planes-3840x2160.png")
    print("rendered contained-planes-3840x2160.png")
    if args.master_only:
        return 0
    for name, size in CROPS.items():
        render(runner, size, args.out / f"contained-planes-{name}.png")
        print(f"rendered contained-planes-{name}.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
