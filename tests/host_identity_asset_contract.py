#!/usr/bin/env python3
"""Contract for the HyperLab Platform identity asset family.

"Isolation Ring" is the product signature: a split circular boundary
containing a core, drawn as architectural relief on a graphite ground. It is
the same geometry the shell draws at 18 units in the rail, so one identity
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
        "40d9e602d7f49358a863d76618ef35919455eaab2247a9feed36df4307e493d5",
    "isolation-ring-2560x1600.png":
        "39256c6141a78ca66d554154955adef8039c793bb3010ca89a2eaed4db2150b1",
    "isolation-ring-3440x1440.png":
        "8b352df8f25f3ca92072722394f853ae8828d97d5486ef0b8873b2f585c23cce",
    "isolation-ring-3840x2160.png":
        "9f17c16d5e31b2be1c5474e41df789fc574353ea6b96d492d0383d51a11aa420",
    "isolation-ring-lock-1920x1080.png":
        "89953418ef17e15190c8db7e25a28018689f27f370c9b63dd5e79d08dad54852",
    "isolation-ring-lock-2560x1600.png":
        "826cf8497913b9dac0702aff88e8c1f06074866dda6c3c73ee1a173a88655e5f",
    "isolation-ring-lock-3440x1440.png":
        "424522d63892ed125a0051cb25ab03459cb3bc81a22e96e88e0891d7a2dfe5a7",
    "isolation-ring-lock-3840x2160.png":
        "81d4ebcb9f2db001fd5df5a6fbb60118f3bdf0f988765525cca4dfa72034ebcc",
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

    for marker in ("PathAngleArc", "splitAngle", "Contained core"):
        require(marker in glyph, f"shell product symbol changed: {marker}")

    print(
        "HyperLab Platform identity asset contract: OK (%d assets)"
        % len(EXPECTED)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
