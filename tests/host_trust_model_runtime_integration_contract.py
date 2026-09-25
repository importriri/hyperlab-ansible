#!/usr/bin/env python3
"""Contract for staged HyperLab trust-model host activation."""

from __future__ import annotations

import json
import re
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
QML = "roles/host_desktop_common/files/quickshell/hyperlab/"


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            "HyperLab staged trust-model runtime contract: "
            + message
        )


def main() -> int:
    theme = yaml.safe_load(
        text("themes/trust-model/theme.yml")
    )
    visual = yaml.safe_load(
        text("themes/trust-model/visual.yml")
    )

    require(
        theme["status"] == "scaffold",
        "theme promoted before physical acceptance",
    )
    require(
        theme["selector"]["visible"] is False,
        "selector enabled before physical acceptance",
    )
    require(
        theme["wallpaper"]["asset_set"]
        == "hyperlab-trust-v2",
        "wrong reviewed wallpaper pool",
    )

    wallpaper = visual["wallpaper"]

    require(
        wallpaper["asset_set"] == "hyperlab-trust-v2",
        "visual references wrong wallpaper pool",
    )
    require(
        wallpaper["rotation"] is True,
        "reviewed rotation disabled",
    )
    require(
        wallpaper["rotation_seconds"] == 1800,
        "rotation is not 30 minutes",
    )
    require(
        wallpaper["rotation_scope"] == "current-trust-only",
        "rotation can leave current trust",
    )
    require(
        wallpaper["immediate_switch_on_trust_change"] is True,
        "trust change does not switch immediately",
    )
    require(
        wallpaper["cross_trust_rotation"] is False,
        "cross-trust rotation enabled",
    )
    require(
        wallpaper["trust_mapping"] == "explicit-manifest",
        "trust mapping is not explicit",
    )

    expected = {
        "host": "#8b949e",
        "clean": "#72f2a5",
        "dev": "#5b8cff",
        "services": "#35e4dd",
        "dirty": "#ff9d45",
        "lab": "#b184ff",
    }

    identities = visual["trust"]["identities"]

    for identity, colour in expected.items():
        require(
            identities[identity]["color"].lower()
            == colour.lower(),
            f"{identity} trust colour changed",
        )

    choices = yaml.safe_load(
        text("group_vars/all/choices.yml")
    )

    require(
        choices["desktop_palette"] == "green",
        "repository default promoted too early",
    )
    require(
        "trust-model"
        in choices["desktop_palette_options"],
        "trust-model not supported by runtime",
    )

    tasks = text(
        "roles/host_desktop_sway/tasks/palette.yml"
    )

    for marker in (
        "Install the rendered trust-model runtime palette",
        "Install the reviewed trust-model wallpaper pool",
        "themes/trust-model/rendered",
        "themes/assets/hyperlab-trust-v2/images",
    ):
        require(
            marker in tasks,
            f"missing deployment marker: {marker}",
        )

    controller = text(
        "roles/host_desktop_sway/files/"
        "privatestack-theme.sh"
    )

    for marker in (
        "green violet blue red trust-model",
        "green|violet|blue|red|trust-model",
        "trust_wallpaper_count=2",
        "trust_rotation_seconds=1800",
        "/usr/share/hyperlab/themes/"
        "trust-model/wallpapers",
        "next reviewed HOST candidate",
        "delay=${trust_rotation_seconds}",
    ):
        require(
            marker in controller,
            f"missing runtime marker: {marker}",
        )

    shared = yaml.safe_load(
        text("group_vars/all/host-desktop.yml")
    )
    stage = shared["host_desktop_common_shell_stage"]

    require(
        stage["design_system"] == "c9-platform",
        "trust integration still targets a pre-C9 shell",
    )

    bar = text(QML + "HyperLabBar.qml")
    tokens = text(QML + "Tokens.qml")
    state = text(QML + "ShellState.qml")
    gpu = text(QML + "GpuBadge.qml")

    presentation = "\n".join(
        text(QML + name)
        for name in stage["surface_files"]
    )

    require(
        "readonly property int barHeight: 37" in tokens
        and "implicitHeight: bar.tokens.barHeight" in bar
        and "exclusiveZone: bar.tokens.barHeight" in bar,
        "37px definitive geometry changed",
    )

    require(
        "badge.claim.claimed" in gpu
        and "provenanceColor(badge.claim.identity)" in gpu,
        "C9 provenance indicator stopped following host claim",
    )

    require(
        not re.search(r"#[0-9a-fA-F]{6}", presentation),
        "shared QML gained literal trust or palette colour",
    )

    require(
        'candidate === "trust-model"' in state,
        "Quickshell cannot follow trust-model",
    )
    require(
        "function wallpaperLabel()" in state
        and 'candidate === "trust-model"' in state
        and 'return "Trust pool";' in state,
        "trust-model wallpaper presentation changed",
    )

    rendered = json.loads(
        text(
            "themes/trust-model/rendered/"
            "hyperlab-palette-quickshell.json"
        )
    )

    require(
        rendered["base"].lower() == "#07090d",
        "near-black base changed",
    )

    pool = (
        ROOT
        / "themes/assets/"
        "hyperlab-trust-v2/images"
    )

    for identity in expected:
        for number in ("01", "02"):
            require(
                (
                    pool
                    / identity
                    / f"{number}.png"
                ).is_file(),
                "missing reviewed wallpaper "
                f"{identity}/{number}",
            )

    print(
        "HyperLab staged trust-model runtime contract: OK"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
