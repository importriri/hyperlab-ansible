#!/usr/bin/env python3
"""Discover and validate declarative HyperLab theme packages."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml


MANIFEST_VERSION = 1

THEME_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

ROOT_KEYS = {
    "version",
    "id",
    "name",
    "status",
    "description",
    "selector",
    "surfaces",
    "wallpaper",
    "keyboard_rgb",
    "trust",
    "security",
}

SURFACES = {
    "quickshell",
    "gtk",
    "rofi",
    "lockscreen",
    "foot",
    "kitty",
    "wallpaper",
    "keyboard_rgb",
}

RGB_MODES = {
    "trust",
    "theme-sync",
    "static",
    "per-zone",
    "gradient",
    "load-temperature",
    "audio-reactive",
    "off",
}

STATUSES = {
    "scaffold",
    "ready",
    "retired",
}

TRUST_IDENTITIES = {
    "host": "neutral",
    "clean": "dom_clean",
    "dev": "dom_dev",
    "services": "dom_services",
    "dirty": "dom_dirty",
    "lab": "dom_lab",
}

FORBIDDEN_MANIFEST_KEYS = {
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


class ThemeError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ThemeError(message)


def exact_keys(
    value: dict[str, Any],
    expected: set[str],
    context: str,
) -> None:
    observed = set(value)
    require(
        observed == expected,
        (
            f"{context}: key set differs: "
            f"missing={sorted(expected - observed)} "
            f"unexpected={sorted(observed - expected)}"
        ),
    )


def reject_executable_keys(value: Any, path: str = "theme") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            lowered = str(key).lower()
            require(
                lowered not in FORBIDDEN_MANIFEST_KEYS,
                f"{path}: executable/privileged key forbidden: {key}",
            )
            reject_executable_keys(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            reject_executable_keys(child, f"{path}[{index}]")


def load_theme(path: Path) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    require(isinstance(raw, dict), f"{path}: manifest must be a mapping")
    exact_keys(raw, ROOT_KEYS, str(path))
    reject_executable_keys(raw)

    require(
        raw["version"] == MANIFEST_VERSION,
        f"{path}: unsupported manifest version",
    )

    theme_id = raw["id"]
    require(
        isinstance(theme_id, str) and THEME_ID.fullmatch(theme_id),
        f"{path}: invalid theme id",
    )
    require(
        path.parent.name == theme_id,
        f"{path}: directory and theme id differ",
    )

    require(
        isinstance(raw["name"], str) and raw["name"].strip(),
        f"{path}: name must be non-empty",
    )
    require(
        raw["status"] in STATUSES,
        f"{path}: invalid status",
    )
    require(
        isinstance(raw["description"], str)
        and raw["description"].strip(),
        f"{path}: description must be non-empty",
    )

    selector = raw["selector"]
    require(isinstance(selector, dict), f"{path}: selector must be mapping")
    exact_keys(selector, {"visible", "order"}, f"{path}: selector")
    require(
        isinstance(selector["visible"], bool),
        f"{path}: selector.visible must be boolean",
    )
    require(
        isinstance(selector["order"], int)
        and selector["order"] >= 0,
        f"{path}: selector.order must be non-negative integer",
    )

    surfaces = raw["surfaces"]
    require(isinstance(surfaces, dict), f"{path}: surfaces must be mapping")
    exact_keys(surfaces, SURFACES, f"{path}: surfaces")
    require(
        all(isinstance(value, bool) for value in surfaces.values()),
        f"{path}: every surface value must be boolean",
    )

    wallpaper = raw["wallpaper"]
    require(isinstance(wallpaper, dict), f"{path}: wallpaper must be mapping")
    exact_keys(
        wallpaper,
        {"policy", "asset_set"},
        f"{path}: wallpaper",
    )
    require(
        wallpaper["policy"]
        in {"collection", "trust-aware", "static", "none"},
        f"{path}: invalid wallpaper policy",
    )
    require(
        isinstance(wallpaper["asset_set"], str)
        and wallpaper["asset_set"].strip(),
        f"{path}: wallpaper asset_set must be non-empty",
    )

    rgb = raw["keyboard_rgb"]
    require(isinstance(rgb, dict), f"{path}: keyboard_rgb must be mapping")
    exact_keys(
        rgb,
        {
            "enabled",
            "mode",
            "provider",
            "capability",
            "zones",
            "brightness",
            "unavailable",
        },
        f"{path}: keyboard_rgb",
    )
    require(
        isinstance(rgb["enabled"], bool),
        f"{path}: keyboard_rgb.enabled must be boolean",
    )
    require(
        rgb["mode"] in RGB_MODES,
        f"{path}: unsupported RGB mode",
    )
    require(
        rgb["provider"] == "hyperlab-nitro-control",
        f"{path}: unreviewed RGB provider",
    )
    require(
        rgb["capability"] == "per_zone",
        f"{path}: unreviewed RGB capability",
    )
    require(
        rgb["zones"] == 4,
        f"{path}: HyperLab Nitro RGB contract requires four zones",
    )
    require(
        rgb["brightness"] == "preserve"
        or (
            isinstance(rgb["brightness"], int)
            and 0 <= rgb["brightness"] <= 100
        ),
        f"{path}: invalid RGB brightness policy",
    )
    require(
        rgb["unavailable"] == "continue-without-rgb",
        f"{path}: incompatible-hardware fallback changed",
    )

    trust = raw["trust"]
    require(isinstance(trust, dict), f"{path}: trust must be mapping")
    exact_keys(
        trust,
        {
            "authority",
            "source",
            "appearance_binding",
            "identities",
        },
        f"{path}: trust",
    )
    require(
        trust["authority"] == "host-owned",
        f"{path}: trust authority must remain host-owned",
    )
    require(
        trust["source"] == "hyperlab-trust-state",
        f"{path}: trust source changed",
    )
    require(
        trust["appearance_binding"] in {"dynamic", "preserve"},
        f"{path}: invalid trust appearance binding",
    )

    identities = trust["identities"]
    require(
        identities == TRUST_IDENTITIES,
        f"{path}: trust identity mapping changed",
    )

    security = raw["security"]
    require(isinstance(security, dict), f"{path}: security must be mapping")
    exact_keys(
        security,
        {
            "arbitrary_commands",
            "direct_sysfs",
            "direct_privilege",
            "guest_trust_authority",
        },
        f"{path}: security",
    )
    require(
        all(value is False for value in security.values()),
        f"{path}: theme security boundary was relaxed",
    )

    return raw


def discover(repo: Path) -> list[tuple[Path, dict[str, Any]]]:
    root = repo / "themes"

    require(root.is_dir(), f"theme root missing: {root}")

    manifests = sorted(root.glob("*/theme.yml"))

    require(manifests, "no HyperLab themes registered")

    result = []
    seen: set[str] = set()

    for path in manifests:
        require(not path.is_symlink(), f"manifest symlink forbidden: {path}")

        manifest = load_theme(path)
        theme_id = manifest["id"]

        require(theme_id not in seen, f"duplicate theme id: {theme_id}")
        seen.add(theme_id)

        result.append((path, manifest))

    return result


def compact_theme(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": manifest["id"],
        "name": manifest["name"],
        "status": manifest["status"],
        "visible": manifest["selector"]["visible"],
        "order": manifest["selector"]["order"],
        "wallpaper_policy": manifest["wallpaper"]["policy"],
        "wallpaper_asset_set": manifest["wallpaper"]["asset_set"],
        "keyboard_rgb": {
            "enabled": manifest["keyboard_rgb"]["enabled"],
            "mode": manifest["keyboard_rgb"]["mode"],
            "provider": manifest["keyboard_rgb"]["provider"],
            "capability": manifest["keyboard_rgb"]["capability"],
            "zones": manifest["keyboard_rgb"]["zones"],
            "brightness": manifest["keyboard_rgb"]["brightness"],
        },
        "trust_binding": manifest["trust"]["appearance_binding"],
    }


def command_validate(repo: Path) -> int:
    themes = discover(repo)

    print(f"THEME_REGISTRY_VERSION={MANIFEST_VERSION}")
    print(f"THEME_COUNT={len(themes)}")

    for _, manifest in themes:
        compact = compact_theme(manifest)
        print(f"THEME_ID={compact['id']}")
        print(f"THEME_STATUS={compact['status']}")
        print(
            "THEME_SELECTOR_VISIBLE="
            + ("YES" if compact["visible"] else "NO")
        )
        print(
            "THEME_RGB_MODE="
            + compact["keyboard_rgb"]["mode"]
        )

    print("THEME_REGISTRY=PASS")
    return 0


def command_list(repo: Path, as_json: bool) -> int:
    themes = [
        compact_theme(manifest)
        for _, manifest in discover(repo)
    ]

    themes.sort(key=lambda item: (item["order"], item["id"]))

    if as_json:
        print(
            json.dumps(
                {
                    "version": MANIFEST_VERSION,
                    "themes": themes,
                },
                separators=(",", ":"),
                sort_keys=True,
            )
        )
    else:
        for theme in themes:
            print(theme["id"])

    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()

    result.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )

    sub = result.add_subparsers(dest="command", required=True)

    sub.add_parser("validate")

    listing = sub.add_parser("list")
    listing.add_argument("--json", action="store_true")

    return result


def main() -> int:
    args = parser().parse_args()

    try:
        if args.command == "validate":
            return command_validate(args.repo)

        if args.command == "list":
            return command_list(args.repo, args.json)

        raise AssertionError("unreachable")

    except (OSError, ThemeError, yaml.YAMLError) as exc:
        print(f"HyperLab theme registry: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
