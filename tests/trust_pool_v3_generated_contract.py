#!/usr/bin/env python3
"""Regenerate the wordless trust pool and execute its material geometry."""
from __future__ import annotations

import ast
import hashlib
from itertools import accumulate
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
import time
import zlib

import yaml

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "tools/wallpaper/render_trust_pool.py"
POOL = ROOT / "themes/assets/trust-pool-v3"
PALETTE = ROOT / "tools/palette/palette.yml"
IDENTITIES = ("host", "clean", "dev", "services", "dirty", "lab")
GEOMETRY_KEYS = ("arcInnerRatio", "cutRatio", "ringRadiusRatio", "ringStrokeRatio", "coreRadiusRatio")
# Twelve renders measured below 80 s on Qt 6.10.2/6.11.2; allow slow CI CPUs.
RENDER_TIMEOUT_SECONDS = 600


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
    numbers = {node.value for node in ast.walk(tree)
               if isinstance(node, ast.Constant) and type(node.value) in (int, float)}
    # QML lives inside Python strings. Compare numeric token values, including
    # base prefixes and separators, rather than their spelling in the source.
    for token in re.findall(
            r"(?<![\w.])(?:0[xX][0-9a-fA-F_]+|0[oO][0-7_]+|0[bB][01_]+"
            r"|(?:[0-9][0-9_]*(?:\.[0-9_]*)?|\.[0-9][0-9_]*)"
            r"(?:[eE][+-]?[0-9][0-9_]*)?)(?![\w.])", "\n".join(strings)):
        literal = token.replace("_", "")
        numbers.add(int(literal, 0) if literal.lower().startswith(("0x", "0o", "0b"))
                    else float(literal))
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
        require(int(colour[1:], 16) not in numbers, f"hardcoded packed identity RGB: {identity}")


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


def geometry_contract() -> dict[str, float]:
    """Link the pool to the product source pinned by the geometry B contract."""
    ratios = []
    for path in (ROOT / "tools/wallpaper/render_isolation_ring.py", RENDERER):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        scenes = [node.value for node in tree.body if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "SCENE"
                          for target in node.targets)]
        require(len(scenes) == 1, f"missing or duplicate scene: {path}")
        scene = ast.literal_eval(scenes[0])
        values = {}
        for key in GEOMETRY_KEYS:
            matches = re.findall(r"(?m)^\s*readonly property real " + key
                                 + r":\s*([0-9]+(?:\.[0-9]+)?)\s*$", scene)
            require(len(matches) == 1, f"missing or duplicate geometry ratio: {path}/{key}")
            values[key] = float(matches[0])
        ratios.append(values)
    require(ratios[0] == ratios[1], "pool geometry differs from product symbol")
    return ratios[0]


def png_pixels(path: Path) -> bytes:
    """Decode the entire opaque capture to RGB, independent of PNG compression."""
    source = path.read_bytes()
    require(source[:8] == b"\x89PNG\r\n\x1a\n" and len(source) >= 33, "invalid PNG capture")
    width, height, depth, kind, compression, filtering, interlace = struct.unpack(
        ">IIBBBBB", source[16:29])
    require((width, height, depth, compression, filtering, interlace) == (1672, 941, 8, 0, 0, 0)
            and kind in (2, 6), "unexpected capture geometry or pixel format")
    compressed = bytearray()
    offset = 8
    kinds = []
    while offset < len(source):
        require(offset + 12 <= len(source), "truncated PNG chunk")
        length = struct.unpack(">I", source[offset:offset + 4])[0]
        end = offset + 8 + length
        require(end + 4 <= len(source), "truncated PNG payload")
        chunk = source[offset + 4:end]
        require(zlib.crc32(chunk) == struct.unpack(">I", source[end:end + 4])[0], "invalid PNG CRC")
        kinds.append(chunk[:4])
        if kinds[-1] == b"IDAT":
            compressed.extend(chunk[4:])
        offset = end + 4
    require(kinds[0] == b"IHDR" and kinds.count(b"IHDR") == 1
            and kinds[-1] == b"IEND" and kinds.count(b"IEND") == 1, "invalid PNG structure")
    data = zlib.decompress(compressed)
    channels = 4 if kind == 6 else 3
    stride = width * channels
    require(len(data) == (stride + 1) * height, "truncated capture pixels")
    previous = bytearray(stride)
    pixels = bytearray()
    opaque = b"\xff" * width
    for y in range(height):
        start = y * (stride + 1)
        method = data[start]
        row = bytearray(data[start + 1:start + 1 + stride])
        require(method in range(5), "invalid PNG filter")
        if method == 1:
            for channel in range(channels):
                row[channel::channels] = bytes(value % 256 for value in accumulate(row[channel::channels]))
        elif method == 2:
            row = bytearray((value + up) % 256 for value, up in zip(row, previous, strict=True))
        elif method in (3, 4):
            for i in range(stride):
                left = row[i - channels] if i >= channels else 0
                up = previous[i]
                corner = previous[i - channels] if i >= channels else 0
                if method == 3:
                    prediction = (left + up) // 2
                else:
                    estimate = left + up - corner
                    a, b, c = abs(estimate - left), abs(estimate - up), abs(estimate - corner)
                    prediction = left if a <= b and a <= c else up if b <= c else corner
                row[i] = (row[i] + prediction) % 256
        if channels == 4:
            require(row[3::4] == opaque, f"nonopaque capture: {path}/{y}")
            rgb = bytearray(width * 3)
            for channel in range(3):
                rgb[channel::3] = row[channel::4]
            pixels.extend(rgb)
        else:
            pixels.extend(row)
        previous = row
    return bytes(pixels)


def png_samples(path: Path, coordinates: list[tuple[int, int]]) -> list[list[int]]:
    pixels = png_pixels(path)
    return [list(pixels[(y * 1672 + x) * 3:(y * 1672 + x) * 3 + 3]) for x, y in coordinates]


def ground_offsets(variant: str, ratios: dict[str, float]) -> list[int]:
    """Every negative-space pixel, leaving one pixel for surface antialiasing."""
    cx, radius = ((1672 * 0.5, 941 * 0.33) if variant == "01"
                  else (1672 * 0.75, 941 * 0.26))
    core = (radius * ratios["coreRadiusRatio"] + 1) ** 2
    ring_inner = (radius * (ratios["ringRadiusRatio"] - ratios["ringStrokeRatio"] / 2) - 1) ** 2
    ring_outer = (radius * (ratios["ringRadiusRatio"] + ratios["ringStrokeRatio"] / 2) + 1) ** 2
    arc_inner = (radius * ratios["arcInnerRatio"] - 1) ** 2
    arc_outer = (radius + 1) ** 2
    cut = radius * ratios["cutRatio"] - 1
    offsets = []
    for y in range(941):
        dy2 = (y + 0.5 - 941 * 0.5) ** 2
        for x in range(1672):
            dx = x + 0.5 - cx
            d2 = dx * dx + dy2
            if (d2 <= core or ring_inner <= d2 <= ring_outer
                    or (arc_inner <= d2 <= arc_outer and abs(dx) >= cut)):
                continue
            offsets.append((y * 1672 + x) * 3)
    return offsets


def ground_contract(pixels: bytes, offsets: list[int], where: Path) -> None:
    # Documented #07090d–#151b23 ground, plus 1.1 grain and byte rounding:
    # two integer levels of margin per channel, including silhouettes.
    for offset in offsets:
        if not (5 <= pixels[offset] <= 23 and 7 <= pixels[offset + 1] <= 29
                and 11 <= pixels[offset + 2] <= 37):
            y, x = divmod(offset // 3, 1672)
            require(False, f"non-ground pixel in geometry gap: {where} at ({x}, {y})")


def pool_manifest(root: Path, expected: set[Path], output: str | None = None) -> dict:
    """Pin each file's own compressed bytes; compare policy independently."""
    require({path.relative_to(root) for path in root.rglob("*") if path.is_file()} == expected,
            f"pool file set: {root}")
    doc = yaml.safe_load((root / "manifest.yml").read_text(encoding="utf-8"))
    files = []
    for identity in IDENTITIES:
        for entry in doc["identities"][identity]["wallpapers"]:
            relative = Path(entry["file"])
            require(relative in expected and relative.suffix == ".png", "unexpected manifest image")
            files.append(relative)
            digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
            require(entry["sha256"] == digest, f"manifest hash mismatch: {root / relative}")
            if output is not None:
                require(f"{digest}  {relative.as_posix()}" in output, "--print-hashes drift")
            del entry["sha256"]
    require(len(files) == 12 and set(files) == expected - {Path("manifest.yml")},
            "missing or duplicate manifest images")
    return doc


def material_contract(module: object, directory: Path) -> None:
    ratios = geometry_contract()
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
                    == [ratios[key] for key in ("cutRatio", "arcInnerRatio", "ringRadiusRatio",
                                              "ringStrokeRatio", "coreRadiusRatio")], "geometry B ratios")
            for x, rgb in row["points"]:
                if identity == "host" and x < ratios["coreRadiusRatio"]:
                    # At the half-pixel silhouette the neutral material blends
                    # with the slightly blue-black ground through coverage.
                    coverage = min(1, max(0, 941 * radius * (ratios["coreRadiusRatio"] - x) + 0.5))
                    require(max(rgb) - min(rgb) <= 8 * (1 - coverage) + 1e-6,
                            "HOST sphere is tinted")
                if x > ratios["coreRadiusRatio"] or identity == "host":
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
    ratios = geometry_contract()
    require((POOL / "manifest.yml").is_file(), "manifest missing")
    doc = yaml.safe_load((POOL / "manifest.yml").read_text(encoding="utf-8"))
    domains = yaml.safe_load(PALETTE.read_text(encoding="utf-8"))["domains"]
    require(set(doc["identities"]) == set(IDENTITIES), "identity set changed")
    for identity in IDENTITIES:
        require(doc["identities"][identity]["trust_color"] == domains[f"dom_{identity}"],
                f"palette/manifest drift: {identity}")
    deployment_contract()
    expected = {Path("manifest.yml")} | {Path(f"images/{identity}/{variant}.png")
               for identity in IDENTITIES for variant in ("01", "02")}
    committed_manifest = pool_manifest(POOL, expected)
    offsets = {variant: ground_offsets(variant, ratios) for variant in ("01", "02")}
    committed_pixels = {}
    for relative in sorted(expected - {Path("manifest.yml")}):
        pixels = png_pixels(POOL / relative)
        ground_contract(pixels, offsets[relative.stem], relative)
        committed_pixels[relative] = pixels
    spec = importlib.util.spec_from_file_location("trust_pool_renderer", RENDERER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix="trust-pool-v3-") as temporary:
        directory = Path(temporary)
        input_contract(module, directory)
        material_contract(module, directory)
        started = time.monotonic()
        result = subprocess.run(["python3", str(RENDERER), "--out", str(directory / "pool"),
                                 "--print-hashes"], capture_output=True, text=True, timeout=RENDER_TIMEOUT_SECONDS, check=False)
        elapsed = time.monotonic() - started
        require(result.returncode == 0, result.stdout + result.stderr)
        generated = directory / "pool"
        require(committed_manifest == pool_manifest(generated, expected, result.stdout),
                "generated manifest policy drift")
        for relative, committed in committed_pixels.items():
            require(committed == png_pixels(generated / relative), f"generated pixel drift: {relative}")
    print(f"Trust pool v3 generated contract: OK (12 pixel-exact renders in {elapsed:.1f}s, "
          "hashes, negative space, shared geometry, materials, palette, deployment)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
