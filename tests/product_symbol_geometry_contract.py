#!/usr/bin/env python3
"""Execute the product glyph and wallpaper paths against geometry B."""
from __future__ import annotations

import ast
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GLYPH = ROOT / "roles/host_desktop_common/files/quickshell/hyperlab/IsolationGlyph.qml"
RENDERER = ROOT / "tools/wallpaper/render_isolation_ring.py"
EXPECTED = {
    "radiusRatio": 0.46,
    "arcInnerRatio": 0.685,
    "cutRatio": 0.41,
    "ringRadiusRatio": 0.555,
    "ringStrokeRatio": 0.057,
    "coreRadiusRatio": 0.413,
    "smallCoreRadiusRatio": 0.435,
    "smallThreshold": 33,
}

GLYPH_SCENE = r'''
import QtQuick
import QtQuick.Window
import QtQuick.Shapes

Window {
    id: window
    visible: true
    width: 160
    height: 160
    color: "#101319"

    Component { id: symbol; IsolationGlyph {} }

    function point(element) {
        return {x: element.x, y: element.y};
    }
    function pathRecord(path) {
        return {
            start: {x: path.startX, y: path.startY},
            stroke: String(path.strokeColor), fill: String(path.fillColor),
            width: path.strokeWidth, round: path.capStyle === ShapePath.RoundCap,
            elements: Array.from(path.pathElements, element => {
                const p = point(element);
                if (element instanceof PathArc) {
                    return {kind: "arc", x: p.x, y: p.y,
                            rx: element.radiusX, ry: element.radiusY,
                            clockwise: element.direction === PathArc.Clockwise,
                            large: element.useLargeArc};
                }
                if (element instanceof PathLine)
                    return {kind: "line", x: p.x, y: p.y};
                if (element instanceof PathAngleArc)
                    return {kind: "circle", cx: element.centerX, cy: element.centerY,
                            rx: element.radiusX, ry: element.radiusY,
                            start: element.startAngle, sweep: element.sweepAngle};
                throw new Error("unexpected path element: " + element);
            })
        };
    }
    Component.onCompleted: Qt.callLater(function() {
        try {
            const rows = [];
            for (const size of [16, 24, 32, 33, 48, 64, 128]) {
                for (const scale of [1, 0, 0.75, 1.25, 3]) {
                    const glyph = symbol.createObject(window.contentItem, {
                        size: size, stroke: "#e2e8ee", core: "#91a0b0", strokeScale: scale
                    });
                    const constants = {};
                    for (const key of @@KEYS@@) constants[key] = glyph[key];
                    const shapes = Array.from(glyph.children).filter(item => item instanceof Shape);
                    rows.push({size: size, scale: scale, constants: constants,
                               small: glyph.small, radius: glyph.outerRadius,
                               width: glyph.width, height: glyph.height,
                               implicitWidth: glyph.implicitWidth, implicitHeight: glyph.implicitHeight,
                               paths: shapes.reduce((paths, shape) =>
                                   paths.concat(Array.from(shape.data).map(pathRecord)), [])});
                    glyph.destroy();
                }
            }
            const defaultCore = symbol.createObject(window.contentItem, {stroke: "#b0c0d0"});
            if (String(defaultCore.core) !== "#b0c0d0")
                throw new Error("core must follow stroke by default");
            defaultCore.stroke = "#d0c0b0";
            if (String(defaultCore.core) !== "#d0c0b0")
                throw new Error("default core binding must follow stroke changes");
            defaultCore.destroy();
            console.log("GEOMETRY " + JSON.stringify(rows));
            Qt.callLater(Qt.quit);
        } catch (error) { console.error(String(error)); Qt.callLater(() => Qt.exit(1)); }
    })
}
'''

RENDERER_CHECK = r'''
    Timer {
        interval: 50
        running: true
        onTriggered: {
            try {
                const constants = {};
                for (const key of @@KEYS@@) constants[key] = art[key];
                const arcs = [];
                const ctx = {
                    beginPath: function() { arcs.push(["begin"]); },
                    moveTo: function(x, y) { arcs.push(["move", x, y]); },
                    lineTo: function(x, y) { arcs.push(["line", x, y]); },
                    arc: function(x, y, r, from, to, reverse) {
                        arcs.push(["arc", x, y, r, from, to, reverse]);
                    },
                    closePath: function() { arcs.push(["close"]); }
                };
                art.arcPath(ctx, -1);
                art.arcPath(ctx, 1);
                const ring = [];
                ctx.beginPath = function() { ring.push(["begin"]); };
                ctx.arc = function(x, y, r, from, to, reverse) {
                    ring.push(["arc", x, y, r, from, to, reverse]);
                };
                ctx.stroke = function() {
                    ring.push(["stroke", ctx.lineWidth, ctx.strokeStyle]);
                };
                art.ring(ctx, art.radius * art.ringRadiusRatio,
                         Math.max(1, art.radius * art.ringStrokeRatio), 0, Math.PI * 2, "#e2e8ee");
                // Exercise the real paint body too: unused correct constants cannot
                // conceal drift in its arc, containment ring or core call sites.
                const painted = [];
                let path = [];
                let offset = [0, 0];
                const stack = [];
                const paint = {
                    reset: function() {},
                    createLinearGradient: function() { return {addColorStop: function() {}}; },
                    createRadialGradient: function() { return {addColorStop: function() {}}; },
                    fillRect: function() {},
                    save: function() { stack.push(offset.slice()); },
                    restore: function() { offset = stack.pop(); },
                    translate: function(x, y) { offset = [offset[0] + x, offset[1] + y]; },
                    beginPath: function() { path = [["begin"]]; },
                    moveTo: function(x, y) { path.push(["move", x, y]); },
                    lineTo: function(x, y) { path.push(["line", x, y]); },
                    arc: function(x, y, r, from, to, reverse) {
                        path.push(["arc", x, y, r, from, to, reverse]);
                    },
                    closePath: function() { path.push(["close"]); },
                    fill: function() { painted.push({kind: "fill", path: path,
                                                     offset: offset.slice(), colour: paint.fillStyle}); },
                    stroke: function() { painted.push({kind: "stroke", path: path,
                                                       offset: offset.slice(), width: paint.lineWidth,
                                                       colour: paint.strokeStyle}); }
                };
                art.draw(paint);
                console.log("GEOMETRY " + JSON.stringify({constants: constants,
                            radius: art.radius, cx: art.centreX, cy: art.centreY,
                            arcs: arcs, ring: ring, painted: painted}));
                Qt.callLater(Qt.quit);
            } catch (error) { console.error(String(error)); Qt.callLater(() => Qt.exit(1)); }
        }
    }
'''


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("Product symbol geometry contract: " + message)


def close(actual: float, expected: float) -> bool:
    return isinstance(actual, (int, float)) and math.isclose(actual, expected, abs_tol=1e-6)


def run(runner: str, directory: Path, source: str) -> object:
    scene = directory / "check.qml"
    scene.write_text(source, encoding="utf-8")
    try:
        result = subprocess.run(
            [runner, str(scene)], capture_output=True, text=True, timeout=20, check=False,
            env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                 "QT_FORCE_STDERR_LOGGING": "1", "QML_DISABLE_DISK_CACHE": "1",
                 "XDG_CACHE_HOME": str(directory / "cache")},
        )
    except subprocess.TimeoutExpired as error:
        raise SystemExit(f"Product symbol geometry contract: Qt path inspection timed out: {error.stderr}") from None
    lines = result.stderr.splitlines() + result.stdout.splitlines()
    records = [line.split("GEOMETRY ", 1)[1] for line in lines if "GEOMETRY " in line]
    noise = [line for line in lines if line.strip() and "GEOMETRY " not in line
             and not line.startswith(("qt.tools.qmlscene.deprecated:", "QStandardPaths:"))]
    require(not result.returncode and len(records) == 1 and not noise,
            f"Qt path inspection failed ({result.returncode}): {noise}")
    return json.loads(records[0])


def constants(values: dict[str, float], where: str) -> None:
    for name, expected in EXPECTED.items():
        require(values.get(name) == expected, f"{where}: {name} must be {expected}")


def check_glyph(rows: list[dict]) -> None:
    for row in rows:
        size, scale = row["size"], row["scale"]
        constants(row["constants"], "glyph")
        small = size < 33
        r = size * 0.46
        c = r * 0.41
        inner = max(c, r * (1 - (1 - 0.685) * scale))
        outer_y, inner_y = math.sqrt(r * r - c * c), math.sqrt(inner * inner - c * c)
        require(row["small"] == small, f"glyph: small variant at {size}")
        require(close(row["radius"], r), "glyph: outer radius")
        require(all(row[key] == size for key in ("width", "height", "implicitWidth", "implicitHeight")),
                "glyph: public size changed")
        paths = row["paths"]
        require(len(paths) == 4, "glyph: expected two filled arcs, ring and core")
        for path, side in zip(paths[:2], (-1, 1), strict=True):
            require(path["fill"] == "#e2e8ee" and path["stroke"] == "#00000000"
                    and path["width"] < 0 and not path["round"], "glyph: arcs must be filled without caps")
            x = size / 2 + side * c
            require(close(path["start"]["x"], x)
                    and close(path["start"]["y"], size / 2 - outer_y), "glyph: outer start")
            elements = path["elements"]
            require([e["kind"] for e in elements] == ["arc", "line", "arc", "line"],
                    "glyph: arcs need circular edges and straight vertical cuts")
            for e, y in zip(elements, (outer_y, inner_y, -inner_y, -outer_y), strict=True):
                require(close(e["x"], x) and close(e["y"], size / 2 + y),
                        "glyph: a cut is not vertical")
            for e, radius, clockwise in ((elements[0], r, side == 1),
                                         (elements[2], inner, side == -1)):
                require(close(e["rx"], radius) and close(e["ry"], radius)
                        and e["clockwise"] == clockwise and not e["large"], "glyph: annulus arc")
        for path, radius, fill, stroke in (
            (paths[2], r * 0.555, "#00000000", "#00000000" if small else "#e2e8ee"),
            (paths[3], r * (0.435 if small else 0.413), "#91a0b0", "#00000000"),
        ):
            require(path["fill"] == fill and path["stroke"] == stroke, "glyph: ring/core colour")
            require(len(path["elements"]) == 1, "glyph: ring/core must be closed circles")
            e = path["elements"][0]
            require(e["kind"] == "circle" and close(e["cx"], size / 2)
                    and close(e["cy"], size / 2) and close(e["rx"], radius)
                    and close(e["ry"], radius) and e["start"] == 0 and e["sweep"] == 360,
                    "glyph: ring/core circle geometry")
        require(close(paths[2]["width"], max(1, r * 0.057 * scale)),
                "glyph: strokeScale or one-pixel ring minimum")


def renderer_scene() -> str:
    tree = ast.parse(RENDERER.read_text(encoding="utf-8"))
    scenes = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == "SCENE" for target in node.targets)]
    require(len(scenes) == 1, "renderer: missing or duplicate scene")
    scene = ast.literal_eval(scenes[0])
    require(isinstance(scene, str), "renderer: scene must be a literal")
    return scene


def check_renderer(row: dict) -> None:
    constants(row["constants"], "renderer")
    r, cx, cy = 1080 * 0.46 / 2, 1920 * 0.52, 1080 * 0.48
    require(close(row["radius"], r) and close(row["cx"], cx) and close(row["cy"], cy),
            "renderer: mark scale or centre changed")
    expected = []
    for side in (-1, 1):
        c, inner = 0.41 * r, 0.685 * r
        oy, iy = math.sqrt(r * r - c * c), math.sqrt(inner * inner - c * c)
        outer_angle, inner_angle = math.acos(0.41), math.acos(0.41 / 0.685)
        top_outer = -outer_angle if side == 1 else math.pi + outer_angle
        bottom_outer = outer_angle if side == 1 else math.pi - outer_angle
        bottom_inner = inner_angle if side == 1 else math.pi - inner_angle
        top_inner = -inner_angle if side == 1 else math.pi + inner_angle
        expected.extend([
            ["begin"], ["move", cx + side * c, cy - oy],
            ["arc", cx, cy, r, top_outer, bottom_outer, side == -1],
            ["line", cx + side * c, cy + iy],
            ["arc", cx, cy, inner, bottom_inner, top_inner, side == 1], ["close"],
        ])
    expected_ring = [["begin"], ["arc", cx, cy, r * 0.555, 0, math.pi * 2, False],
                     ["stroke", max(1, r * 0.057), "#e2e8ee"]]
    painted = row["painted"]
    require([p["kind"] for p in painted] == ["fill", "fill", "stroke", "fill", "stroke",
                                          "stroke", "stroke", "fill", "fill", "stroke"],
            "renderer: relief must fill both arcs, stroke the ring and fill the core")
    require(painted[1]["colour"] == painted[3]["colour"] == "rgba(0, 0, 0, 0.42)",
            "renderer: arc recess depth")
    require(all(painted[i]["colour"] == "rgba(226, 232, 238, 0.26)"
                and close(painted[i]["width"], 4.5)
                and all(close(v, -9 * 0.22) for v in painted[i]["offset"])
                for i in (2, 4)), "renderer: arc edge-light treatment")
    for actual, wanted, part in ((row["arcs"], expected, "filled arcs"),
                                  (row["ring"], expected_ring, "ring"),
                                  (painted[1]["path"], expected[:6], "painted left arc"),
                                  (painted[3]["path"], expected[6:], "painted right arc"),
                                  (painted[5]["path"], expected_ring[:2], "painted ring"),
                                  (painted[8]["path"], [["begin"],
                                   ["arc", cx, cy, r * 0.413, 0, math.pi * 2, False]], "painted core")):
        require(len(actual) == len(wanted), f"renderer: {part} path count")
        for a, b in zip(actual, wanted, strict=True):
            require(len(a) == len(b) and all(
                close(x, y) if type(y) in (int, float) else x == y
                for x, y in zip(a, b, strict=True)), f"renderer: {part} path differs: {a} != {b}")

    require(close(painted[5]["width"], r * 0.057), "renderer: painted ring stroke")


def main() -> int:
    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    require(bool(runner), "Qt 6 qmlscene is required")
    keys = json.dumps(list(EXPECTED))
    with tempfile.TemporaryDirectory(prefix="hyperlab-symbol-") as temporary:
        directory = Path(temporary)
        shutil.copyfile(GLYPH, directory / GLYPH.name)
        check_glyph(run(runner, directory, GLYPH_SCENE.replace("@@KEYS@@", keys)))
        # Suppress only the production capture exit, so the timer can inspect
        # the laid-out Canvas. The actual draw handler still runs.
        scene = renderer_scene().replace("Qt.quit();", "")
        for key, value in {"WIDTH": "1920", "HEIGHT": "1080", "DIAMETER": "0.46",
                           "GLOW": "0.070", "DEPTH": "0.42", "EDGE": "0.26", "CORE": "0.72",
                           "OUTFILE": str(directory / "unused.png")}.items():
            scene = scene.replace(key, value)
        head, tail = scene.rsplit("}", 1)
        check_renderer(run(runner, directory, head + RENDERER_CHECK.replace("@@KEYS@@", keys) + "}" + tail))
    print("Product symbol geometry contract: OK (glyph paths, size boundary, relief paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
