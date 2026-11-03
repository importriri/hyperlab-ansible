#!/usr/bin/env python3
"""Contract for the HyperLab Platform identity asset family.

"Isolation Ring" is the product signature: geometry B, two filled annulus
segments with vertical cuts and gaps above and below a ring and core, drawn
as architectural relief on a graphite ground. It is the same geometry the
shell draws at 18 units in the rail, so one identity
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

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "roles/host_desktop_common/files/wallpapers"
GENERATOR = ROOT / "tools/wallpaper/render_isolation_ring.py"
ROLLBACK = ROOT / "tools/wallpaper/render_contained_planes.py"

EXPECTED = {
    "isolation-ring-1920x1080.png":
        "e03f345f113be6a6b5828731546372793ed17047257eedeb63e103ca5d5d87f9",
    "isolation-ring-2560x1600.png":
        "e82127343308b5668c1316c4ca3b3f04e58ad8168355004ec483191705f519dd",
    "isolation-ring-3440x1440.png":
        "30cf1e7965eb29371d99326c17c7d4433c45d359b4009088a69db35267bb4f57",
    "isolation-ring-3840x2160.png":
        "2b0041b991ea1e18b2cad48a3a193ffee9f27778e7234306479f3e2ff0ceaead",
    "isolation-ring-lock-1920x1080.png":
        "0ccb01fd27a53e00e1840e70d5c6f1707268a774b77dd8f11e254af3a8ca8619",
    "isolation-ring-lock-2560x1600.png":
        "1796e337f3a1b79279b521047bae4efca9f7c8206c6e6462654c089b7092adba",
    "isolation-ring-lock-3440x1440.png":
        "39e81fe4b30f0f1af7752384541d81ef9677fdce6dbdc3c672b698676a888cd2",
    "isolation-ring-lock-3840x2160.png":
        "57f00830a8f651c813a07a68b23494f27079a2e36a3b89fc2bd42b4a511508a7",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"HyperLab identity asset contract: {message}")


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def main() -> int:
    require(GENERATOR.is_file(), "the identity generator disappeared")
    require(
        ROLLBACK.is_file(),
        "the rollback wallpaper generator was removed before acceptance",
    )

    generator = GENERATOR.read_text(encoding="utf-8")

    # Reproducible by construction: no randomness, no clock, no network.
    for forbidden in ("random", "time.time", "urllib", "requests", "datetime"):
        require(
            forbidden not in generator,
            f"identity generator became non-deterministic: {forbidden}",
        )

    for forbidden in ("dom_", "trust", "provenance"):
        require(
            forbidden not in generator.lower().split('"""')[2],
            f"identity asset gained a trust input: {forbidden}",
        )

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

    print(
        "HyperLab Platform identity asset contract: OK (%d assets)"
        % len(EXPECTED)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
