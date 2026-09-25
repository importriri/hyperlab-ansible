#!/usr/bin/env python3
"""Contract for the declarative HyperLab theme registry."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

THEME = ROOT / "themes/trust-model/theme.yml"
TOOL = ROOT / "tools/theme_registry.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(
            f"HyperLab theme registry contract: {message}"
        )


def main() -> int:
    require(THEME.is_file(), "trust-model manifest missing")
    require(TOOL.is_file(), "theme registry tool missing")
    require(bool(TOOL.stat().st_mode & 0o111),
            "theme registry tool is not executable")

    manifests = sorted((ROOT / "themes").glob("*/theme.yml"))

    require(
        [path.parent.name for path in manifests] == ["trust-model"],
        "scaffold must register exactly trust-model",
    )

    doc = yaml.safe_load(THEME.read_text(encoding="utf-8"))

    require(doc["version"] == 1, "manifest version drifted")
    require(doc["id"] == "trust-model", "theme id drifted")
    require(doc["status"] == "scaffold", "theme must remain scaffold")
    require(doc["selector"]["visible"] is False,
            "unfinished theme became selectable")

    expected_surfaces = {
        "quickshell": True,
        "gtk": True,
        "rofi": True,
        "lockscreen": True,
        "foot": True,
        "kitty": True,
        "wallpaper": True,
        "keyboard_rgb": True,
    }

    require(
        doc["surfaces"] == expected_surfaces,
        "theme surface ownership changed",
    )

    require(
        doc["wallpaper"] == {
            "policy": "trust-aware",
            "asset_set": "hyperlab-trust-v2",
        },
        "trust-model wallpaper policy changed",
    )

    rgb = doc["keyboard_rgb"]

    require(rgb["enabled"] is True, "theme RGB was disabled")
    require(rgb["mode"] == "trust", "trust-model RGB mode changed")
    require(
        rgb["provider"] == "hyperlab-nitro-control",
        "RGB escaped the reviewed broker",
    )
    require(rgb["capability"] == "per_zone",
            "RGB capability changed")
    require(rgb["zones"] == 4, "Nitro four-zone contract changed")
    require(rgb["brightness"] == "preserve",
            "theme unexpectedly forces keyboard brightness")
    require(
        rgb["unavailable"] == "continue-without-rgb",
        "non-RGB hardware fallback changed",
    )

    require(
        doc["trust"] == {
            "authority": "host-owned",
            "source": "hyperlab-trust-state",
            "appearance_binding": "dynamic",
            "identities": {
                "host": "neutral",
                "clean": "dom_clean",
                "dev": "dom_dev",
                "services": "dom_services",
                "dirty": "dom_dirty",
                "lab": "dom_lab",
            },
        },
        "trust-model authority or identities changed",
    )

    require(
        all(value is False for value in doc["security"].values()),
        "theme manifest relaxed its security boundary",
    )

    forbidden_keys = {
        "command",
        "commands",
        "exec",
        "execute",
        "shell",
        "sudo",
        "pkexec",
        "sysfs",
        "script",
    }

    def reject_forbidden_keys(value, location="theme"):
        if isinstance(value, dict):
            for key, child in value.items():
                lowered = str(key).lower()

                require(
                    lowered not in forbidden_keys,
                    (
                        "executable theme primitive introduced: "
                        f"{location}.{key}"
                    ),
                )

                reject_forbidden_keys(
                    child,
                    f"{location}.{key}",
                )

        elif isinstance(value, list):
            for index, child in enumerate(value):
                reject_forbidden_keys(
                    child,
                    f"{location}[{index}]",
                )

    reject_forbidden_keys(doc)

    validation = subprocess.run(
        [
            "python3",
            str(TOOL),
            "--repo",
            str(ROOT),
            "validate",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    require(
        validation.returncode == 0,
        "registry validator failed:\n"
        + validation.stdout
        + validation.stderr,
    )

    listing = subprocess.run(
        [
            "python3",
            str(TOOL),
            "--repo",
            str(ROOT),
            "list",
            "--json",
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    require(
        listing.returncode == 0,
        "registry JSON listing failed",
    )

    payload = json.loads(listing.stdout)

    require(payload["version"] == 1, "registry JSON version drifted")
    require(len(payload["themes"]) == 1,
            "registry JSON theme count changed")

    registered = payload["themes"][0]

    require(
        registered["id"] == "trust-model",
        "registry JSON selected wrong theme",
    )
    require(
        registered["keyboard_rgb"]["mode"] == "trust",
        "registry JSON lost RGB policy",
    )

    legacy = {"green", "violet", "blue", "red"}

    require(
        legacy.isdisjoint(
            {path.parent.name for path in manifests}
        ),
        "legacy palettes were registered as plugin themes",
    )

    print("HyperLab declarative theme registry contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
