#!/usr/bin/env python3
"""Render the HyperLab product identity wallpaper family deterministically.

"Isolation Ring" is the product signature at wallpaper scale: two vertically cut
annulus segments with gaps above and below a containment ring and core. The
v3 materials give the arcs light stone grain under an upper-left light and
the core a neutral textured sphere on a seeded near-black ground. The shell
draws the same geometry at 18 units in the rail.

It carries no words, no reticles, no telemetry, no provenance colours and no
state-like marks. It is a ground for the shell and it grants no authority:
wallpaper never encodes trust.

Two variants are produced from one geometry:

    desktop   the everyday ground, mark at ~46% of the shorter side
    lock      darker and quieter, for a screen that must show nothing about
              the session behind it

Rendering uses Qt's software rasteriser through qmlscene, so the output is
byte-stable for given Qt and zlib releases.

    python3 tools/wallpaper/render_isolation_ring.py --out <dir>
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
from pathlib import Path
import struct
import tempfile
import zlib

import pool_material

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

# The static family has no identity or palette input. Its sphere uses the
# same neutral grey material as the reviewed HOST pool image.
VARIANTS = {
    # name: (diameter fraction, material strength)
    "isolation-ring": (0.46, 1.0),
    "isolation-ring-lock": (0.40, 0.55),
}


def scene(size: tuple[int, int], variant: str, out: Path) -> str:
    diameter, quiet = VARIANTS[variant]
    return pool_material.scene(size, (0.52, 0.48), diameter / 2, quiet, (147, 147, 147), out)


def render(runner: str, size: tuple[int, int], variant: str, out: Path) -> None:
    # Capture the same opaque pixels without Qt's adaptive PNG filters. For
    # this fine grain, unfiltered RGB compresses better and keeps 4K below
    # the 5 MiB asset budget without quantisation or resampling.
    with tempfile.TemporaryDirectory(prefix="hyperlab-product-rgb-") as temporary:
        capture = Path(temporary) / "capture.ppm"
        pool_material.render(runner, scene(size, variant, capture), capture)
        data = capture.read_bytes()
    width, height = size
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    if not data.startswith(header) or len(data) != len(header) + width * height * 3:
        raise ValueError("unexpected native RGB capture")
    pixels = data[len(header):]
    stride = width * 3
    rows = b"".join(b"\0" + pixels[start:start + stride]
                    for start in range(0, len(pixels), stride))

    def chunk(kind: bytes, payload: bytes) -> bytes:
        body = kind + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    out.write_bytes(b"\x89PNG\r\n\x1a\n"
                    + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(rows, 9)) + chunk(b"IEND", b""))


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
