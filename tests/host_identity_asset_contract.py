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
MAX_PNG_BYTES = 5 * 1024 * 1024

EXPECTED = {
    "isolation-ring-1920x1080.png":
        "0717b9d6b97dffa9346d4cf9be0d9474bdd8efd036a437e5e0df1139c965ceff",
    "isolation-ring-2560x1600.png":
        "47b11250c28a9a7131ebb021966f49a622bc80a6bf1764259f924a86ce338f3e",
    "isolation-ring-3440x1440.png":
        "627e633da60044ee2592f93e433af8ed1419901e787991e84bcd266a9ce7486b",
    "isolation-ring-3840x2160.png":
        "0c3bffde2f3b9c6f00ab4f1e04a71927f311cc1a7f060e9b2c67967401a0b3ef",
    "isolation-ring-lock-1920x1080.png":
        "60fb2d24f642d0f12170d4252d11de69fbb7bd366897f727d89a74a79f08f24b",
    "isolation-ring-lock-2560x1600.png":
        "0066e6fee2501115b6cdaa106cc44049daf15f1c557f98ff9e18db9c80f3bf09",
    "isolation-ring-lock-3440x1440.png":
        "55e976e2402192eb8cabbf0873c1ec539f2629a3f653359011b396f44a02b053",
    "isolation-ring-lock-3840x2160.png":
        "9df66f58668908cf671fe6ab21ed95fbe1ebc1b86f10c2e8a8cbc62a73fe2295",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"HyperLab identity asset contract: {message}")


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def file_budget_contract(path: Path) -> None:
    require(path.stat().st_size <= MAX_PNG_BYTES,
            f"identity PNG exceeds 5 MiB: {path.name}")


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
    size = (32, 16)
    pixels = bytes(index % 256 for index in range(math.prod(size) * 3))

    def capture(runner: str, source: str, out: Path) -> None:
        recorded.append((runner, source, out))
        out.write_bytes(b"P6\n32 16\n255\n" + pixels)

    module.pool_material.render = capture
    try:
        for variant, (diameter, quiet) in module.VARIANTS.items():
            target = directory / f"{variant}.png"
            module.render("capture-probe", size, variant, target)
            captured = recorded[-1][2]
            shared = module.pool_material.scene(size, (0.52, 0.48), diameter / 2,
                                                quiet, (147, 147, 147), captured)
            require(recorded[-1] == ("capture-probe", shared, captured), "product bypasses shared v3 drawing")
            require(png_pixels(target, size) == pixels, "product encoding changed captured RGB pixels")
            target.unlink()
        for invalid in (b"P6\n16 32\n255\n" + pixels,
                        b"P6\n32 16\n255\n" + pixels[:-1],
                        b"P6\n32 16\n255\n" + pixels + b"\0"):
            module.pool_material.render = lambda runner, source, out, payload=invalid: out.write_bytes(payload)
            try:
                module.render("capture-probe", size, "isolation-ring", directory / "invalid.png")
            except ValueError:
                pass
            else:
                require(False, "product accepted invalid native RGB capture")
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
        file_budget_contract(generated)
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
        file_budget_contract(path)

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
