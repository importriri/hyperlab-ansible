#!/usr/bin/env python3
"""Regenerate the wordless trust pool and execute its material geometry."""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile
import zlib

import yaml

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "tools/wallpaper/render_trust_pool.py"
POOL = ROOT / "themes/assets/trust-pool-v3"
PALETTE = ROOT / "tools/palette/palette.yml"
IDENTITIES = ("host", "clean", "dev", "services", "dirty", "lab")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit("Trust pool v3 generated contract: " + message)


def source_contract() -> None:
    require(RENDERER.is_file(), "renderer missing")
    source = RENDERER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    strings = [node.value for node in ast.walk(tree)
               if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    names = [node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)]
    names.extend(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
    numeric_triples = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.List, ast.Tuple)) and len(node.elts) == 3 and all(
                isinstance(item, ast.Constant) and type(item.value) in (int, float)
                for item in node.elts):
            numeric_triples.append(list(ast.literal_eval(node)))
    content = "\n".join(strings + names)
    require(not re.search(r"\b(?:fillText|strokeText|reticle|crosshair)\b|\bText\s*\{|font(?:[._ ]?family)?",
                          content, re.IGNORECASE), "text or reticle primitive in renderer")
    scenes = [node.value for node in tree.body if isinstance(node, ast.Assign)
              and any(isinstance(target, ast.Name) and target.id == "SCENE" for target in node.targets)]
    require(len(scenes) == 1, "missing or duplicate literal scene")
    scene = ast.literal_eval(scenes[0])
    # Pixel materials are the sole paint operation; line/path/label primitives
    # would allow screen furniture to escape the geometry's surface masks.
    operations = set(re.findall(r"\bctx\s*\.\s*(\w+)\s*\(", scene))
    require(operations == {"createImageData", "putImageData"},
            f"unexpected Canvas drawing operations: {operations}")
    palette = yaml.safe_load(PALETTE.read_text(encoding="utf-8"))["domains"]
    for identity in IDENTITIES:
        colour = palette[f"dom_{identity}"]
        require(colour.lower() not in source.lower(), f"hardcoded identity colour: {identity}")
        rgb = [int(colour[i:i + 2], 16) for i in (1, 3, 5)]
        require(rgb not in numeric_triples and not re.search(
                    r"\b" + r"\s*,\s*".join(map(str, rgb)) + r"\b", content),
                f"hardcoded identity RGB: {identity}")


def input_contract(module: object, directory: Path) -> None:
    original = PALETTE.read_text(encoding="utf-8")
    fixture = directory / "palette.yml"
    for name, value in (
        ("missing domain", original.replace("  dom_dev: '#5b8cff'\n", "")),
        ("duplicate domain", original.replace("domains:\n", "domains:\n  dom_dev: '#ffffff'\n")),
        ("duplicate root", original + "\ndomains: {}\n"),
        ("invalid colour", original.replace("'#5b8cff'", "'blue'")),
    ):
        fixture.write_text(value, encoding="utf-8")
        try:
            module.load_palette(fixture)
        except (ValueError, OSError, yaml.YAMLError):
            pass
        else:
            require(False, f"accepted {name}")
    fixture.unlink()
    try:
        module.load_palette(fixture)
    except OSError:
        pass
    else:
        require(False, "accepted missing palette")
    fixture.symlink_to(PALETTE)
    try:
        module.load_palette(fixture)
    except (ValueError, OSError):
        pass
    else:
        require(False, "accepted redirected palette")
    fixture.unlink()
    redirected = directory / "redirected"
    redirected.symlink_to(PALETTE.parent, target_is_directory=True)
    try:
        module.load_palette(redirected / PALETTE.name)
    except (ValueError, OSError):
        pass
    else:
        require(False, "accepted redirected palette directory")


def png_samples(path: Path, coordinates: list[tuple[int, int]]) -> list[list[int]]:
    """Read real capture pixels, including Qt's adaptive PNG scanline filters."""
    source = path.read_bytes()
    require(source[:8] == b"\x89PNG\r\n\x1a\n", "invalid PNG capture")
    width, height, depth, kind, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", source[16:29])
    require((width, height, depth, compression, filtering, interlace) == (1672, 941, 8, 0, 0, 0)
            and kind in (2, 6), "unexpected capture geometry or pixel format")
    compressed = bytearray()
    offset = 8
    while offset < len(source):
        length = struct.unpack(">I", source[offset:offset + 4])[0]
        if source[offset + 4:offset + 8] == b"IDAT":
            compressed.extend(source[offset + 8:offset + 8 + length])
        offset += 12 + length
    data = zlib.decompress(compressed)
    channels = 4 if kind == 6 else 3
    stride = width * channels
    require(len(data) == (stride + 1) * height, "truncated capture pixels")
    previous = bytearray(stride)
    rows = {}
    wanted = {y for _, y in coordinates}
    for y in range(max(wanted) + 1):
        start = y * (stride + 1)
        method = data[start]
        row = bytearray(data[start + 1:start + 1 + stride])
        require(method in range(5), "invalid PNG filter")
        for i in range(stride):
            left = row[i - channels] if i >= channels else 0
            up = previous[i]
            corner = previous[i - channels] if i >= channels else 0
            if method == 1:
                prediction = left
            elif method == 2:
                prediction = up
            elif method == 3:
                prediction = (left + up) // 2
            elif method == 4:
                estimate = left + up - corner
                candidates = (left, up, corner)
                prediction = min(candidates, key=lambda value: abs(estimate - value))
            else:
                prediction = 0
            row[i] = (row[i] + prediction) % 256
        if y in wanted:
            rows[y] = row
        previous = row
    return [list(rows[y][x * channels:x * channels + 3]) for x, y in coordinates]


def material_contract(module: object, directory: Path) -> None:
    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    require(bool(runner), "Qt 6 qmlscene is required")
    palette = module.load_palette(PALETTE)
    for identity in ("host", "dev"):
        for variant, cx, radius in (("01", 0.5, 0.33), ("02", 0.75, 0.26)):
            scene = module.scene(palette[identity], identity, variant, directory / "unused.png")
            scene = scene[:scene.index("        onPaint:")] + "    }\n}\n"
            probe = r'''
    Timer {
        interval: 1; running: true
        onTriggered: {
            const r = art.radius, cx = art.centreX, cy = art.centreY;
            const points = [];
            for (const x of [0, 0.2, 0.412, 0.43, 0.5, 0.55, 0.6, 0.68, 0.72, 0.9, 1.01])
                points.push([x, art.sample(cx + x*r, cy)]);
            const capture = [[2, 2], [Math.floor(cx), Math.floor(cy)],
                [Math.floor(cx+r*0.9), Math.floor(cy)]];
            console.log("MATERIAL " + JSON.stringify({capture: capture.map(p =>
                ({point: p, rgb: art.sample(p[0]+0.5, p[1]+0.5)})), cx: cx, cy: cy, radius: r,
                cut: art.cutRatio, inner: art.arcInnerRatio, ring: art.ringRadiusRatio,
                stroke: art.ringStrokeRatio, core: art.coreRadiusRatio, points: points,
                top: art.sample(cx, cy-r*0.9), corner: art.sample(2, 2)}));
            Qt.quit();
        }
    }
'''
            head, tail = scene.rsplit("}", 1)
            check = directory / "material.qml"
            check.write_text(head + probe + "}" + tail, encoding="utf-8")
            result = subprocess.run([runner, str(check)], capture_output=True, text=True,
                                    timeout=20, check=False, env={**os.environ,
                                    "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
                                    "QT_FORCE_STDERR_LOGGING": "1", "QML_DISABLE_DISK_CACHE": "1", "XDG_CACHE_HOME": str(directory / "cache")})
            lines = (result.stderr + result.stdout).splitlines()
            rows = [line.split("MATERIAL ", 1)[1] for line in lines if "MATERIAL " in line]
            require(result.returncode == 0 and len(rows) == 1, f"Qt material probe: {lines}")
            row = json.loads(rows[0])
            coordinates = [tuple(item["point"]) for item in row["capture"]]
            actual = png_samples(POOL / f"images/{identity}/{variant}.png", coordinates)
            expected = [[math.floor(value + 0.5) for value in item["rgb"]]
                        for item in row["capture"]]
            require(actual == expected, f"capture differs from material: {identity}/{variant}")
            require(math.isclose(row["cx"], 1672 * cx) and row["cy"] == 941 * 0.5
                    and math.isclose(row["radius"], 941 * radius), "variant scale or placement")
            require([row[key] for key in ("cut", "inner", "ring", "stroke", "core")]
                    == [0.41, 0.685, 0.555, 0.057, 0.413], "geometry B ratios")
            for x, rgb in row["points"]:
                if identity == "host" and x < 0.413:
                    # At the half-pixel silhouette the neutral material blends
                    # with the slightly blue-black ground through coverage.
                    coverage = min(1, max(0, 941 * radius * (0.413 - x) + 0.5))
                    require(max(rgb) - min(rgb) <= 8 * (1 - coverage) + 1e-6,
                            "HOST sphere is tinted")
                if x > 0.413 or identity == "host":
                    require(max(rgb) - min(rgb) <= 8, "tint escaped sphere or HOST is tinted")
                if x in (0.43, 0.5, 0.6, 0.68, 1.01):
                    require(max(rgb) <= 35, f"geometry gap filled at {x}")
                if x in (0.55, 0.72, 0.9):
                    require(min(rgb) > 40, f"grey ring/stone arc missing at {x}")
                if identity == "dev" and x == 0.2:
                    require(rgb[2] > rgb[0] + 12, "sphere lost palette tint")
            require(max(row["top"]) < 35 and max(row["corner"]) < 35,
                    "top opening or ground is no longer quiet")


def deployment_contract() -> None:
    for path in ("themes/trust-model/theme.yml", "themes/trust-model/visual.yml"):
        doc = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
        require(doc["wallpaper"]["asset_set"] == "trust-pool-v3", f"v3 not selected: {path}")
    defaults = yaml.safe_load((ROOT / "roles/guest_desktop_hyprland/defaults/main.yml").read_text())
    require(defaults["guest_desktop_hyprland_identity_assets"].endswith("/themes/assets/trust-pool-v3"),
            "guest deploys old pool")
    tasks = yaml.safe_load((ROOT / "roles/host_desktop_sway/tasks/palette.yml").read_text())
    copies = [task["ansible.builtin.copy"] for task in tasks if "ansible.builtin.copy" in task
              and "/wallpapers/" in task["ansible.builtin.copy"].get("dest", "")]
    require(len(copies) == 1 and "/themes/assets/trust-pool-v3/images/" in copies[0]["src"],
            "host deploys old pool")
    # The reviewed rollback stays byte-pinned by its original pool contract.
    require((ROOT / "themes/assets/hyperlab-trust-v2/manifest.yml").is_file(), "v2 rollback missing")


def main() -> int:
    source_contract()
    require((POOL / "manifest.yml").is_file(), "manifest missing")
    doc = yaml.safe_load((POOL / "manifest.yml").read_text(encoding="utf-8"))
    domains = yaml.safe_load(PALETTE.read_text(encoding="utf-8"))["domains"]
    require(set(doc["identities"]) == set(IDENTITIES), "identity set changed")
    for identity in IDENTITIES:
        require(doc["identities"][identity]["trust_color"] == domains[f"dom_{identity}"],
                f"palette/manifest drift: {identity}")
    deployment_contract()
    spec = importlib.util.spec_from_file_location("trust_pool_renderer", RENDERER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="trust-pool-v3-") as temporary:
        directory = Path(temporary)
        input_contract(module, directory)
        material_contract(module, directory)
        result = subprocess.run(["python3", str(RENDERER), "--out", str(directory / "pool"),
                                 "--print-hashes"], capture_output=True, text=True, timeout=180, check=False)
        require(result.returncode == 0, result.stdout + result.stderr)
        generated = directory / "pool"
        expected = {Path("manifest.yml")} | {Path(f"images/{identity}/{variant}.png")
                   for identity in IDENTITIES for variant in ("01", "02")}
        for root in (POOL, generated):
            require({path.relative_to(root) for path in root.rglob("*") if path.is_file()} == expected,
                    f"pool file set: {root}")
        for relative in sorted(expected):
            require((POOL / relative).read_bytes() == (generated / relative).read_bytes(),
                    f"generated output drift: {relative}")
            if relative.suffix == ".png":
                digest = hashlib.sha256((generated / relative).read_bytes()).hexdigest()
                require(f"{digest}  {relative.as_posix()}" in result.stdout, "--print-hashes drift")
    print("Trust pool v3 generated contract: OK (12 exact renders, materials, palette, deployment)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
