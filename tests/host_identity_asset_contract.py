#!/usr/bin/env python3
"""Contract for the HyperLab Platform identity asset family.

"Isolation Ring" is the product signature: geometry B, two filled annulus
segments with vertical cuts and gaps above and below a ring and core, drawn
with the v3 stone and sphere materials on a seeded near-black ground. The
shell draws the same geometry at 18 units in the rail, so one identity
carries from the lock screen to the top bar.

Three things are pinned here:

  1. the rendered assets, by content hash, so a regenerated family is a
     deliberate reviewed change and never a silent replacement;
  2. the generator, so the assets stay reproducible rather than becoming
     checked-in binaries nobody can rebuild;
  3. the ownership rules the assets exist to keep -- the wallpaper carries no
     provenance, and the lock surface is a dedicated static asset rather than
     a rotated theme wallpaper or a blurred screenshot.
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import math
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from trust_pool_v3_generated_contract import geometry_contract, ground_contract, ground_offsets, png_pixels, source_contract

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "roles/host_desktop_common/files/wallpapers"
GENERATOR = ROOT / "tools/wallpaper/render_isolation_ring.py"
ROLLBACK = ROOT / "tools/wallpaper/render_contained_planes.py"

EXPECTED = {
    "isolation-ring-1920x1080.png":
        "d333713ed82b67dc4e908584337fd260f71d906730dfacd4a085f0201ba7b5a6",
    "isolation-ring-2560x1600.png":
        "7b489b4628e722836563d3de657fe56660114b7960f9d91511d096de22f99853",
    "isolation-ring-3440x1440.png":
        "cf87587820cfbf4b6d42ed726c5fcdb14ebcfa8faeb47c6bae836157504d61e1",
    "isolation-ring-3840x2160.png":
        "984cd193f15e621a0b2180a8e36f6b06bdcac2cc14c1c99fe7742a870fe51238",
    "isolation-ring-lock-1920x1080.png":
        "85e48554daf4e4a6c4cc0034bfa53fc3280b46e796ad9a9824a8e19d0ad883c6",
    "isolation-ring-lock-2560x1600.png":
        "191427b5e37fa703aa8d861db2dbdc91ac633cbaa8128bee2502e7fdfa3a3cbc",
    "isolation-ring-lock-3440x1440.png":
        "b4c02ba1f380c0ce93ba07ebe7506695ee29cec87ba484af6b8c3a00a845f11c",
    "isolation-ring-lock-3840x2160.png":
        "42b5014d6364693120cb4dc879cdeff19df1f5ab6e91100eb912820940794bc1",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"HyperLab identity asset contract: {message}")


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def configuration_contract(directory: Path) -> dict[str, tuple[int, int]]:
    """Inspect output dimensions and exercise the actual shared capture route."""
    sys.path.insert(0, str(GENERATOR.parent))
    spec = importlib.util.spec_from_file_location("identity_renderer", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    expected_sizes = {"3840x2160": (3840, 2160), "1920x1080": (1920, 1080),
                      "2560x1600": (2560, 1600), "3440x1440": (3440, 1440)}
    require(expected_sizes == module.SIZES, "native output sizes changed")
    require(module.VARIANTS == {"isolation-ring": (0.46, 1.0), "isolation-ring-lock": (0.40, 0.55)},
            "product or quieter lock parameters changed")
    # Exercise the wrapper's actual render path with capture intercepted.
    # Both generation and capture must be delegated to the shared material.
    recorded = []
    original = module.pool_material.render
    module.pool_material.render = lambda runner, source, out: recorded.append((runner, source, out))
    try:
        for variant, (diameter, quiet) in module.VARIANTS.items():
            target = directory / f"{variant}.png"
            module.render("capture-probe", (1920, 1080), variant, target)
            shared = module.pool_material.scene((1920, 1080), (0.52, 0.48), diameter / 2,
                                                quiet, (147, 147, 147), target)
            require(recorded[-1] == ("capture-probe", shared, target), "product bypasses shared v3 drawing")
    finally:
        module.pool_material.render = original
    return expected_sizes


def native_contract(directory: Path) -> None:
    """Render all eight outputs and compare decoded pixels at native size."""
    expected_sizes = configuration_contract(directory)
    started = time.monotonic()
    result = subprocess.run([sys.executable, str(GENERATOR), "--out", str(directory), "--print-hashes"],
                            capture_output=True, text=True, timeout=600, check=False)
    require(result.returncode == 0, result.stdout + result.stderr)
    require({path.name for path in directory.glob("*.png")} == set(EXPECTED), "native output file set")
    ratios = geometry_contract()
    for name in EXPECTED:
        size = expected_sizes[name.removesuffix(".png").split("-")[-1]]
        generated = directory / name
        digest = hashlib.sha256(generated.read_bytes()).hexdigest()
        require(f"{digest}  {name}" in result.stdout, "--print-hashes drift")
        diameter = 0.40 if "-lock-" in name else 0.46
        capture_contract(ASSETS / name, generated, size, diameter, ratios)
    print(f"Native identity regeneration: OK (8 pixel-exact renders, neutral cores, negative space, {time.monotonic() - started:.1f}s)")


def capture_contract(path: Path, generated: Path, size: tuple[int, int],
                     diameter: float, ratios: dict[str, float]) -> None:
    pixels = png_pixels(path, size)
    require(pixels == png_pixels(generated, size), f"native generated pixel drift: {path.name}")
    ground_contract(pixels, ground_offsets("", ratios, size, (0.52, 0.48, diameter / 2)), path, size)
    neutral_core_contract(pixels, size, diameter, path)


def neutral_core_contract(pixels: bytes, size: tuple[int, int], diameter: float, path: Path) -> None:
    """Check every fully covered sphere pixel, not just a material probe."""
    width, height = size
    cx, cy, core = width * 0.52, height * 0.48, min(size) * diameter / 2 * 0.413 - 1
    for y in range(math.ceil(cy - core), math.floor(cy + core) + 1):
        for x in range(math.ceil(cx - core), math.floor(cx + core) + 1):
            if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= core ** 2:
                offset = (y * width + x) * 3
                require(pixels[offset] == pixels[offset + 1] == pixels[offset + 2],
                        f"neutral sphere is tinted: {path.name} at {(x, y)}")


def product_source_contract() -> None:
    generator = GENERATOR.read_text(encoding="utf-8")
    # Retain the static family's original source bans alongside the shared
    # AST and QML restrictions, including otherwise unused forbidden inputs.
    for forbidden in ("random", "time.time", "urllib", "requests", "datetime"):
        require(forbidden not in generator,
                f"identity generator became non-deterministic: {forbidden}")
    for forbidden in ("dom_", "trust", "provenance"):
        require(forbidden not in generator.lower().split('"""')[2],
                f"identity asset gained a trust input: {forbidden}")
    # The static product entry point must never acquire the pool's palette
    # loader or an identity input. Shared materials receive neutral RGB only.
    tree = ast.parse(GENERATOR.read_text(encoding="utf-8"))
    imports = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    imports.update(alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
                   for alias in node.names)
    require(not imports.intersection({"yaml", "render_trust_pool"}), "product gained palette dependency")
    names = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    names.update(node.id for node in ast.walk(tree) if isinstance(node, ast.Name))
    require(not names.intersection({"load_palette", "PALETTE", "identity", "trust"}), "product gained trust input")



def main() -> int:
    require(GENERATOR.is_file(), "the identity generator disappeared")
    require(
        ROLLBACK.is_file(),
        "the rollback wallpaper generator was removed before acceptance",
    )

    source_contract()
    product_source_contract()

    for name, digest in EXPECTED.items():
        path = ASSETS / name

        require(path.is_file(), f"identity asset missing: {name}")

        actual = hashlib.sha256(path.read_bytes()).hexdigest()

        require(
            actual == digest,
            f"identity asset changed without review: {name} is {actual}",
        )

    tasks = text("roles/host_desktop_common/tasks/main.yml")

    for marker in (
        "src: wallpapers/isolation-ring-3840x2160.png",
        "dest: /usr/share/backgrounds/hyperlab/product.png",
        "src: wallpapers/isolation-ring-lock-3840x2160.png",
        "dest: /usr/share/backgrounds/hyperlab/lock.png",
        # Rollback material stays installed until physical acceptance.
        "dest: /usr/share/backgrounds/hyperlab/contained-planes.png",
    ):
        require(marker in tasks, f"identity deployment marker missing: {marker}")

    theme_helper = text(
        "roles/host_desktop_sway/files/privatestack-theme.sh"
    )

    require(
        "/usr/share/backgrounds/hyperlab/product.png" in theme_helper,
        "the product wallpaper mode lost the identity asset",
    )
    require(
        "/usr/share/backgrounds/hyperlab/lock.png" in theme_helper,
        "the lock surface no longer uses a dedicated static asset",
    )
    # The historical rotation offset remains only as an explicit fallback.
    require(
        "lock_index=$(( (desktop_index + 3) % count ))" in theme_helper,
        "the lock fallback rotation disappeared",
    )

    # The shell draws the same geometry rather than shipping a second logo.
    glyph = text(
        "roles/host_desktop_common/files/quickshell/hyperlab/"
        "IsolationGlyph.qml"
    )

    for marker in ("PathAngleArc", "cutRatio", "Contained core"):
        require(marker in glyph, f"shell product symbol changed: {marker}")

    with tempfile.TemporaryDirectory(prefix="hyperlab-native-identity-") as temporary:
        native_contract(Path(temporary))

    print(
        "HyperLab Platform identity asset contract: OK (%d assets)"
        % len(EXPECTED)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
