#!/usr/bin/env python3
"""Contract for deterministic Trust Model rendering."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "tools/theme_render.py"
RENDERED = ROOT / "themes/trust-model/rendered"
PREVIEW = ROOT / "themes/trust-model/preview.html"
THEME = ROOT / "themes/trust-model/theme.yml"


EXPECTED_FILES = {
    "hyperlab-palette-quickshell.json",
    "hyperlab-palette-gtk.css",
    "hyperlab-palette-waybar.css",
    "hyperlab-palette.rasi",
    "hyperlab-palette-foot.ini",
    "hyperlab-palette-kitty.conf",
    "hyperlab-palette-hyprland.lua",
    "hyperlab-palette.sway",
    "hyperlab-palette-swaylock.conf",
    "hyperlab-rgb-map.json",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab theme render contract: {message}"
        )


def text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    require(RENDERER.is_file(), "renderer missing")
    require(bool(RENDERER.stat().st_mode & 0o111),
            "renderer not executable")
    require(RENDERED.is_dir(), "rendered directory missing")
    require(PREVIEW.is_file(), "preview missing")

    observed = {
        path.name
        for path in RENDERED.iterdir()
        if path.is_file()
    }

    require(
        observed == EXPECTED_FILES,
        "rendered file set differs",
    )

    with tempfile.TemporaryDirectory(
        prefix="hyperlab-theme-render-"
    ) as temporary:
        temp = Path(temporary)
        output = temp / "rendered"
        preview = temp / "preview.html"

        result = subprocess.run(
            [
                "python3",
                str(RENDERER),
                "--repo",
                str(ROOT),
                "trust-model",
                str(output),
                "--preview",
                str(preview),
            ],
            check=False,
            text=True,
            capture_output=True,
        )

        require(
            result.returncode == 0,
            result.stdout + result.stderr,
        )

        for filename in EXPECTED_FILES:
            require(
                (output / filename).read_bytes()
                == (RENDERED / filename).read_bytes(),
                f"non-deterministic output: {filename}",
            )

        require(
            preview.read_bytes() == PREVIEW.read_bytes(),
            "preview is non-deterministic",
        )

    palette = json.loads(
        text(RENDERED / "hyperlab-palette-quickshell.json")
    )

    require(palette["name"] == "trust-model",
            "wrong Quickshell theme name")
    require(palette["base"] == "#07090d",
            "wrong near-black base")
    require(palette["accent"] == "#d0d7de",
            "generic focus is not neutral")
    require(palette["dom_host"] == "#8b949e",
            "host neutral token changed")
    require(palette["dom_clean"] == "#72f2a5",
            "clean trust token changed")
    require(palette["dom_dev"] == "#5b8cff",
            "dev trust token changed")
    require(palette["dom_services"] == "#35e4dd",
            "services trust token changed")
    require(palette["dom_dirty"] == "#ff9d45",
            "dirty trust token changed")
    require(palette["dom_lab"] == "#b184ff",
            "lab trust token changed")

    foot = text(RENDERED / "hyperlab-palette-foot.ini")

    require("[colors-dark]" in foot,
            "Foot palette missing")
    require("alpha=0.84" in foot,
            "Foot transparency contract changed")

    kitty = text(
        RENDERED / "hyperlab-palette-kitty.conf"
    )

    require("background #07090d" in kitty,
            "Kitty background changed")
    require("active_border_color #d0d7de" in kitty,
            "Kitty generic focus not neutral")

    hyprland = text(
        RENDERED / "hyperlab-palette-hyprland.lua"
    )

    require(
        'active_border = "rgba(d0d7deff)"'
        in hyprland,
        "Hyprland focus incorrectly uses trust colour",
    )

    rgb = json.loads(
        text(RENDERED / "hyperlab-rgb-map.json")
    )

    require(
        rgb["provider"] == "hyperlab-nitro-control",
        "RGB provider changed",
    )
    require(rgb["zones"] == 4, "RGB zone count changed")
    require(
        rgb["zone_policy"] == "uniform-trust-color",
        "RGB trust policy changed",
    )

    expected_rgb = {
        "host": "8b949e",
        "clean": "72f2a5",
        "dev": "5b8cff",
        "services": "35e4dd",
        "dirty": "ff9d45",
        "lab": "b184ff",
    }

    for identity, colour in expected_rgb.items():
        require(
            rgb["identities"][identity]["zones"]
            == [colour] * 4,
            f"RGB mapping changed: {identity}",
        )

    preview = text(PREVIEW)

    require("HyperLab · Trust Model" in preview,
            "preview title missing")
    require("TRUST DEV" in preview,
            "preview trust sample missing")

    for filename in (
        "01-cerchio-nero-e-rosso.png",
        "02-geometria-blu.png",
        "03-orbita-rossa.png",
        "04-orbita-viola.png",
        "05-spirale-verde.png",
        "06-ingranaggio-oro.png",
        "07-onda-e-semicerchio.png",
        "08-golden-image.png",
        "09-vela-geometrica.png",
        "10-diagramma-circolare.png",
    ):
        require(filename in preview,
                f"preview missing asset: {filename}")

    normalized_preview = " ".join(preview.split())

    require(
        "no symbol is assigned to a trust identity yet"
        in normalized_preview,
        "preview hides the pending mapping boundary",
    )

    # The theme remains hidden until actual runtime and visual acceptance.
    import yaml

    theme = yaml.safe_load(
        THEME.read_text(encoding="utf-8")
    )

    require(theme["status"] == "scaffold",
            "theme became ready too early")
    require(theme["selector"]["visible"] is False,
            "theme became selectable too early")

    print("HyperLab Trust Model deterministic render contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
