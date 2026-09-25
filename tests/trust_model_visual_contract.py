#!/usr/bin/env python3
"""Contract for the HyperLab Trust Model visual profile."""

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
VISUAL = ROOT / "themes/trust-model/visual.yml"
THEME = ROOT / "themes/trust-model/theme.yml"
ASSETS = ROOT / "themes/assets/hyperlab-symbols-v1/manifest.yml"


TRUST_COLORS = {
    "host": "#8b949e",
    "clean": "#72f2a5",
    "dev": "#5b8cff",
    "services": "#35e4dd",
    "dirty": "#ff9d45",
    "lab": "#b184ff",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab trust-model visual contract: {message}"
        )


def main() -> int:
    require(VISUAL.is_file(), "visual.yml missing")

    visual = yaml.safe_load(
        VISUAL.read_text(encoding="utf-8")
    )
    theme = yaml.safe_load(
        THEME.read_text(encoding="utf-8")
    )
    assets = yaml.safe_load(
        ASSETS.read_text(encoding="utf-8")
    )

    require(visual["version"] == 1, "visual schema changed")
    require(visual["theme"] == "trust-model", "wrong theme")

    design = visual["design"]

    require(
        design["style"] == "dark-near-black",
        "trust-model lost near-black identity",
    )
    require(
        design["identity"] == "central-symbol",
        "central-symbol identity changed",
    )
    require(
        design["decorative_trust_colors"] is False,
        "trust colours became decoration",
    )

    appearance = visual["appearance"]

    require(
        appearance["base"] == "#07090d",
        "base colour changed",
    )
    require(
        appearance["focus"] == "#d0d7de",
        "generic focus must remain neutral",
    )

    trust = visual["trust"]

    require(
        trust["authority"] == "host-owned",
        "trust authority escaped host ownership",
    )
    require(
        trust["focused_surface_drives_identity"] is True,
        "focus provenance no longer drives trust presentation",
    )
    require(
        trust["host_native_returns_neutral"] is True,
        "host-native surface no longer returns neutral",
    )

    observed_colors = {
        identity: data["color"]
        for identity, data in trust["identities"].items()
    }

    require(
        observed_colors == TRUST_COLORS,
        "canonical trust colours changed",
    )

    quickshell = visual["quickshell"]

    require(
        quickshell["focus_uses_neutral_focus_token"] is True,
        "focus and trust semantics were collapsed",
    )
    require(
        quickshell["trust_badge_uses_trust_identity"] is True,
        "trust badge disconnected from provenance",
    )
    require(
        quickshell["generic_controls_use_trust_colors"] is False,
        "generic controls misuse security colours",
    )
    require(
        quickshell["telemetry_uses_trust_colors"] is False,
        "telemetry misuses security colours",
    )

    wallpaper = visual["wallpaper"]

    require(
        wallpaper["asset_set"] == "hyperlab-trust-v2",
        "wrong canonical visual asset set",
    )
    require(
        wallpaper["rotation"] is True,
        "reviewed trust wallpaper rotation was disabled",
    )
    require(
        wallpaper["central_symbol_required"] is True,
        "central symbol requirement disappeared",
    )
    require(
        wallpaper["trust_mapping"] == "explicit-manifest",
        "reviewed explicit wallpaper/trust mapping changed",
    )
    require(
        wallpaper["infer_mapping_from_color"] is False,
        "wallpaper colour became trust authority",
    )
    require(
        wallpaper["infer_mapping_from_filename"] is False,
        "wallpaper filename became trust authority",
    )

    require(
        assets["semantic_policy"]["trust_assignment"]
        == "pending",
        "asset manifest gained unreviewed trust semantics",
    )

    rgb = visual["keyboard_rgb"]

    require(
        rgb["source"] == "focused-host-owned-trust",
        "keyboard RGB source changed",
    )
    require(
        rgb["provider"] == "hyperlab-nitro-control",
        "keyboard RGB escaped reviewed Nitro broker",
    )
    require(
        rgb["capability"] == "per_zone",
        "keyboard RGB capability changed",
    )
    require(rgb["zones"] == 4, "four-zone policy changed")
    require(
        rgb["zone_policy"] == "uniform-trust-color",
        "Trust mode must use one identity across all four zones",
    )
    require(
        rgb["brightness"] == "preserve",
        "theme unexpectedly forces brightness",
    )
    require(
        rgb["update_policy"] == "event-driven",
        "Trust RGB should follow focus events",
    )

    for identity, color in TRUST_COLORS.items():
        expected = color.removeprefix("#")

        require(
            rgb["identities"][identity]["zones"]
            == [expected] * 4,
            f"RGB identity mismatch: {identity}",
        )

    security = visual["security"]

    require(
        all(value is False for value in security.values()),
        "visual theme gained security authority",
    )

    require(
        theme["keyboard_rgb"]["mode"] == "trust",
        "theme manifest RGB mode changed",
    )
    require(
        theme["keyboard_rgb"]["provider"]
        == "hyperlab-nitro-control",
        "theme manifest RGB provider changed",
    )
    require(
        theme["selector"]["visible"] is False,
        "unfinished trust-model became selectable",
    )

    print("HyperLab trust-model visual + RGB contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
