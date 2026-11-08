#!/usr/bin/env python3
"""Execute the product glyph and wallpaper paths against geometry B."""
from __future__ import annotations

import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from trust_pool_v3_generated_contract import png_samples

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
        interval: 1; running: true
        onTriggered: {
            const constants = {};
            for (const key of @@KEYS@@) constants[key] = art[key];
            const r = art.radius, cx = art.centreX, cy = art.centreY;
            const points = [
                [0, 0], [0.2, 0], [0.412, 0], [0.43, 0], [0.5, 0],
                [0.55, 0], [0.6, 0], [0.68, 0], [0.72, 0], [0.9, 0], [1.01, 0],
                [0, -0.9], [0, 0.9], [0.40, -0.75], [0.42, -0.75],
                [-0.40, 0.75], [-0.42, 0.75], [-0.9, -0.2], [0.9, 0.2]
            ];
            const capture = [[2, 2], [Math.floor(cx), Math.floor(cy)],
                [Math.floor(cx+r*0.9), Math.floor(cy)], [Math.floor(cx+r*0.55), Math.floor(cy)],
                [Math.floor(cx+r*0.4), Math.floor(cy-r*0.75)],
                [Math.floor(cx+r*0.42), Math.floor(cy-r*0.75)]];
            console.log("GEOMETRY " + JSON.stringify({constants: constants,
                radius: r, cx: cx, cy: cy, quiet: art.quiet,
                width: art.width, height: art.height,
                capture: capture.map(p => ({point: p, rgb: art.sample(p[0]+0.5, p[1]+0.5)})),
                points: points.map(p => ({x: p[0], y: p[1],
                    rgb: art.sample(cx + p[0]*r, cy + p[1]*r)}))}));
            Qt.quit();
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


def renderer_module() -> object:
    sys.path.insert(0, str(RENDERER.parent))
    spec = importlib.util.spec_from_file_location("product_renderer", RENDERER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check_renderer(row: dict, size: tuple[int, int], variant: str) -> None:
    for name in ("arcInnerRatio", "cutRatio", "ringRadiusRatio", "ringStrokeRatio", "coreRadiusRatio"):
        require(row["constants"].get(name) == EXPECTED[name], f"renderer: {name} must be {EXPECTED[name]}")
    diameter, quiet = (0.46, 1.0) if variant == "isolation-ring" else (0.40, 0.55)
    r, cx, cy = min(size) * diameter / 2, size[0] * 0.52, size[1] * 0.48
    require(close(row["radius"], r) and close(row["cx"], cx) and close(row["cy"], cy),
            "renderer: mark scale or centre changed")
    require((row["width"], row["height"]) == size, "renderer: native canvas size")
    require(row["quiet"] == quiet, "renderer: lock material attenuation")
    for point in row["points"]:
        x, y, rgb = point["x"], point["y"], point["rgb"]
        distance = math.hypot(x, y)
        is_core = distance < 0.413
        is_ring = abs(distance - 0.555) < 0.057 / 2
        is_arc = 0.685 < distance < 1 and abs(x) > 0.41
        if is_core:
            # Silhouette coverage can blend with the slightly blue ground.
            coverage = min(1, max(0, r * (0.413 - distance) + 0.5))
            require(max(rgb) - min(rgb) <= 8 * (1 - coverage) + 1e-6,
                    "renderer: neutral sphere is tinted")
        elif is_ring or is_arc:
            require(min(rgb) > 40, f"renderer: grey ring/stone arc missing at {(x, y)}")
            require(max(rgb) - min(rgb) <= 9 * (1 - quiet) + 1e-6,
                    f"renderer: grey material is tinted at {(x, y)}: {rgb}")
        else:
            require(max(rgb) < 35, f"renderer: geometry gap filled at {(x, y)}")

    name = f"{variant}-{size[0]}x{size[1]}.png"
    path = ROOT / "roles/host_desktop_common/files/wallpapers" / name
    actual = png_samples(path, [tuple(item["point"]) for item in row["capture"]], size)
    expected = [[math.floor(value + 0.5) for value in item["rgb"]] for item in row["capture"]]
    require(actual == expected, f"renderer: capture differs from material: {name}")


def main() -> int:
    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    require(bool(runner), "Qt 6 qmlscene is required")
    keys = json.dumps(list(EXPECTED))
    with tempfile.TemporaryDirectory(prefix="hyperlab-symbol-") as temporary:
        directory = Path(temporary)
        shutil.copyfile(GLYPH, directory / GLYPH.name)
        check_glyph(run(runner, directory, GLYPH_SCENE.replace("@@KEYS@@", keys)))
        module = renderer_module()
        geometry_keys = json.dumps([key for key in EXPECTED
                                    if key not in ("radiusRatio", "smallCoreRadiusRatio", "smallThreshold")])
        for size in ((3840, 2160), (1920, 1080), (2560, 1600), (3440, 1440)):
            for variant in ("isolation-ring", "isolation-ring-lock"):
                scene = module.scene(size, variant, directory / "unused.png")
                # Inspect the exact production shader without capturing an image.
                scene = scene[:scene.index("        onPaint:")] + "    }\n}\n"
                head, tail = scene.rsplit("}", 1)
                row = run(runner, directory, head + RENDERER_CHECK.replace("@@KEYS@@", geometry_keys) + "}" + tail)
                check_renderer(row, size, variant)
    print("Product symbol geometry contract: OK (glyph paths, size boundary, native v3 material masks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
