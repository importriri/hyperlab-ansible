#!/usr/bin/env python3
"""Every declared choice must describe the implementation."""
from __future__ import annotations

import json
import re
from pathlib import Path

import choices as mod

HERE = Path(__file__).parent
REPO = HERE.parent.parent
MANAGER = REPO / "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py"
WAYBAR = REPO / "roles/host_desktop_sway/files/waybar.jsonc"

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, declared, actual) -> None:
    ok = str(declared) == str(actual)
    (PASSED if ok else FAILED).append(name)
    print(f"  {'ok  ' if ok else 'FAIL'} {name:44} declared={declared!s:20} actual={actual!s}")


def waybar() -> dict:
    return json.loads(re.sub(r"(?m)^\s*//.*$", "", WAYBAR.read_text(encoding="utf-8")))


def main() -> int:
    doc = mod.load()["choices"]
    bar = waybar()
    source = MANAGER.read_text(encoding="utf-8") if MANAGER.is_file() else None
    if source is None:
        print("  (manager absent; manager-specific checks skipped)")
    print("=== choices against code")

    left = bar.get("modules-left", [])
    legacy = "custom/cava" in left or "custom/logo" in left
    if legacy:
        print("  (pre-M11 Waybar detected; current shell choices skipped)")
    else:
        check("waybar_height", doc["waybar_height"]["value"], bar.get("height"))
        shape = (
            "brand_and_trust_drawer"
            if left[:2] == ["custom/brand", "group/hyperlab"]
            else "single_combined_launcher"
            if "custom/hyperlab-launcher" in left
            else "unknown"
        )
        check("waybar_launcher_shape", doc["waybar_launcher_shape"]["value"], shape)

    if source is not None:
        mapping = re.search(
            r'def _section_to_drawer_tab\(.*?\).*?'
            r'if section in \{[^}]*"domains"[^}]*\}:\s*return "(\w+)"',
            source,
            re.DOTALL,
        )
        check("drawer_domains_section_tab",
              doc["drawer_domains_section_tab"]["value"],
              mapping.group(1) if mapping else "not found")
        snapshot = "disabled_until_m12" if "Snapshot & Backup stage" in source else "enabled"
        check("snapshot_actions", doc["snapshot_actions"]["value"], snapshot)
        enumeration = "vm_only" if "qrexec" not in source else "guest_agent"
        check("drawer_app_enumeration", doc["drawer_app_enumeration"]["value"], enumeration)

    palette = REPO / "tools/palette/palette.yml"
    if palette.is_file():
        import yaml
        variants = set(yaml.safe_load(palette.read_text())["variants"])
        check("desktop_palette exists",
              doc["desktop_palette"]["value"] in variants, True)
        check("all desktop_palette alternatives exist",
              set(map(str, doc["desktop_palette"]["options"])) <= variants, True)

    print(f"\n{'=' * 74}\npassed {len(PASSED)}, failed {len(FAILED)}")
    if FAILED:
        print("The choices source does not describe the code.")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
