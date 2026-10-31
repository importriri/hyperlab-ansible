#!/usr/bin/env python3
"""Discover and validate declarative HyperLab theme packages."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
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
            f"missing={sorted(expected - observed, key=str)} "
            f"unexpected={sorted(observed - expected, key=str)}"
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
    return validate_theme(path, raw)


def validate_theme(path: Path, raw: Any) -> dict[str, Any]:
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
        isinstance(raw["status"], str) and raw["status"] in STATUSES,
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
        isinstance(wallpaper["policy"], str) and wallpaper["policy"]
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
        isinstance(rgb["mode"], str) and rgb["mode"] in RGB_MODES,
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
        isinstance(trust["appearance_binding"], str)
        and trust["appearance_binding"] in {"dynamic", "preserve"},
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


APPEARANCE_KEYS = {
    "base", "mantle", "surface", "overlay", "text", "subtext",
    "accent", "accent2", "ok", "warn", "bad",
}
DOMAIN_KEYS = {"dom_" + identity for identity in TRUST_IDENTITIES}
COLOUR = re.compile(r"#[0-9a-fA-F]{6}")


class PreviewLoader(yaml.SafeLoader):
    """Reject aliases and duplicate keys instead of accepting overwritten input."""

    def compose_node(self, parent: Any, index: Any) -> Any:
        require(not self.check_event(yaml.AliasEvent), "YAML aliases forbidden in preview inputs")
        return super().compose_node(parent, index)

    def construct_mapping(self, node: Any, deep: bool = False) -> dict[Any, Any]:
        require(isinstance(node, yaml.MappingNode), "YAML input must be a mapping")
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            require(isinstance(key, (str, int, float, type(None))), "YAML mapping key must be scalar")
            require(key not in result, f"duplicate YAML mapping key: {key}")
            result[key] = self.construct_object(value_node, deep=deep)
        return result


def unique_json(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON mapping key: {key}")
        result[key] = value
    return result


def read_source(repo: Path, relative: str) -> str:
    """Open only regular files beneath a resolved root, without following links.

    Each directory is opened relative to the preceding descriptor. A replaced
    ancestor therefore cannot redirect a subsequent open outside the root.
    """
    parts = Path(relative).parts
    require(parts and all(part not in {".", "..", "/"} for part in parts),
            "invalid preview input path")
    flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW
    directory = os.open(repo, flags | os.O_DIRECTORY)
    try:
        for part in parts[:-1]:
            child = os.open(part, flags | os.O_DIRECTORY, dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], flags | os.O_NONBLOCK, dir_fd=directory)
        with os.fdopen(descriptor, "r", encoding="utf-8") as stream:
            mode = os.fstat(stream.fileno()).st_mode
            require(stat.S_ISREG(mode),
                    f"{relative}: preview input must be a regular file")
            require(bool(mode & 0o444), f"{relative}: preview input is unreadable")
            return stream.read()
    finally:
        os.close(directory)


def source_yaml(repo: Path, relative: str) -> dict[str, Any]:
    doc = yaml.load(read_source(repo, relative), Loader=PreviewLoader)
    require(isinstance(doc, dict), f"{relative}: document must be a mapping")
    return doc


def mapping_field(doc: dict[str, Any], key: str) -> dict[str, Any]:
    value = doc.get(key)
    require(isinstance(value, dict), f"{key}: expected a mapping")
    return value


def valid_ids(values: Any) -> list[str]:
    require(isinstance(values, list) and bool(values), "runtime options must be a non-empty list")
    seen: set[str] = set()
    for value in values:
        require(isinstance(value, str) and THEME_ID.fullmatch(value), "invalid runtime preset id")
        require(value not in seen, f"duplicate runtime preset id: {value}")
        seen.add(value)
    return values


def valid_colour(value: Any, context: str) -> None:
    require(isinstance(value, str) and COLOUR.fullmatch(value), f"{context}: invalid colour")


def palette_summaries(repo: Path) -> dict[str, Any]:
    repo = repo.resolve(strict=True)
    source = source_yaml(repo, "tools/choices/choices.yml")
    choice = mapping_field(mapping_field(source, "choices"), "desktop_palette")
    options = valid_ids(list(mapping_field(choice, "options")))
    generated = source_yaml(repo, "group_vars/all/choices.yml")
    generated_options = valid_ids(generated.get("desktop_palette_options"))
    require(set(options) == set(generated_options), "source and generated runtime options disagree")

    palette_source = source_yaml(repo, "tools/palette/palette.yml")
    variants = mapping_field(palette_source, "variants")
    domains = mapping_field(palette_source, "domains")
    exact_keys(domains, DOMAIN_KEYS, "canonical domains")
    for key, value in domains.items():
        valid_colour(value, f"canonical domain {key}")

    rows = []
    for theme_id in sorted(options):
        if theme_id in variants:
            variant = mapping_field(variants, theme_id)
            label = variant.get("label")
            require(isinstance(label, str) and bool(label.strip()), f"{theme_id}: invalid label")
            source_kind = "legacy"
            manifest_status = None
            manifest_visible = None
            relative = f"roles/host_desktop_sway/files/palette/{theme_id}/hyperlab-palette-quickshell.json"
        else:
            relative_manifest = f"themes/{theme_id}/theme.yml"
            manifest = validate_theme(repo / relative_manifest, source_yaml(repo, relative_manifest))
            label = manifest["name"]
            source_kind = "declarative"
            manifest_status = manifest["status"]
            manifest_visible = manifest["selector"]["visible"]
            relative = f"themes/{theme_id}/rendered/hyperlab-palette-quickshell.json"

        palette = json.loads(read_source(repo, relative), object_pairs_hook=unique_json)
        require(isinstance(palette, dict), f"{relative}: palette must be a mapping")
        exact_keys(palette, APPEARANCE_KEYS | DOMAIN_KEYS | {"name"}, theme_id)
        require(palette["name"] == theme_id, f"{theme_id}: wrong palette name")
        for key in sorted(APPEARANCE_KEYS | DOMAIN_KEYS):
            valid_colour(palette[key], f"{theme_id}.{key}")
        require(all(palette[key] == domains[key] for key in DOMAIN_KEYS),
                f"{theme_id}: canonical domain colours differ")
        rows.append({
            "id": theme_id,
            "label": label,
            "source_kind": source_kind,
            "manifest_status": manifest_status,
            "manifest_visible": manifest_visible,
            "appearance": {key: palette[key] for key in sorted(APPEARANCE_KEYS)},
        })
    return {"version": 1, "scope": "source-runtime-presets", "presets": rows}


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

    summaries = sub.add_parser("palette-summaries")
    summaries.add_argument("--json", action="store_true", required=True)

    return result


def main() -> int:
    args = parser().parse_args()

    try:
        if args.command == "validate":
            return command_validate(args.repo)

        if args.command == "list":
            return command_list(args.repo, args.json)

        if args.command == "palette-summaries":
            payload = palette_summaries(args.repo)
            print(json.dumps(payload, separators=(",", ":"), sort_keys=True))
            return 0

        raise AssertionError("unreachable")

    except (OSError, ThemeError, yaml.YAMLError, json.JSONDecodeError, UnicodeError) as exc:
        print(f"HyperLab theme registry: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
