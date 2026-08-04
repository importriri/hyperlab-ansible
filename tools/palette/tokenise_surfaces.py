#!/usr/bin/env python3
"""Move Waybar, Sway and GTK onto the manager's shared tokens.

All three surfaces already support variables. The problem is that each declares its own names and values, so the same desktop carries multiple palettes. Migration is a rename plus an include, not a rewrite.

Mappings are semantic names rather than colour-distance guesses.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# waybar.css / gtk3.css / gtk4.css: declared name -> token
CSS_MAP = {
    "glass": "base", "panel": "mantle", "surface": "surface", "border": "overlay",
    "text": "text", "subtext": "subtext", "cyan": "accent", "teal": "accent2",
    "green": "ok", "yellow": "warn", "orange": "dom_dirty", "violet": "dom_lab",
    "red": "bad",
    "hyper_bg": "base", "hyper_glass": "mantle", "hyper_surface": "surface",
    "hyper_border": "overlay", "hyper_text": "text", "hyper_muted": "subtext",
    "hyper_cyan": "accent", "hyper_violet": "dom_lab",
    # Cover both the public Catppuccin names and the staged glass/cyan names.
    "crust": "base", "mantle": "base", "base": "mantle",
    "surface0": "surface", "surface1": "overlay", "surface2": "overlay",
    "overlay0": "overlay", "overlay1": "overlay", "overlay2": "subtext",
    "subtext0": "subtext", "subtext1": "subtext",
    "lavender": "accent", "mauve": "accent",
    "blue": "dom_dev", "sapphire": "accent2", "sky": "accent2",
    "peach": "dom_dirty", "maroon": "bad",
}
# sway.config is mapped by semantic role in client.* lines, not Catppuccin naming.
SWAY_MAP = {
    "crust": "base", "mantle": "base", "base": "mantle", "surface1": "overlay",
    "overlay0": "overlay", "text": "text", "subtext0": "subtext",
    "mauve": "accent", "lavender": "accent", "red": "bad",
}
INCLUDE = {
    "css": '@import url("file:///usr/share/hyperlab/palette-{fragment}.css");',
    "sway": "include /usr/share/hyperlab/palette.sway",
}


def tokenise_css(text: str, fragment: str) -> tuple[str, list[str]]:
    orphans: list[str] = []
    declared = dict(re.findall(r"^@define-color\s+(\w+)\s+([^;]+);", text, re.M))
    for name in declared:
        if name not in CSS_MAP:
            orphans.append(name)
    body = re.sub(r"^@define-color\s+\w+\s+[^;]+;\s*\n", "", text, flags=re.M)

    def swap(match: re.Match) -> str:
        name = match.group(1)
        return f"@hl_{CSS_MAP[name]}" if name in CSS_MAP else match.group(0)

    body = re.sub(r"@(\w+)\b", swap, body)

    # Convert an exact token colour from rgba() to alpha(@token, a).
    def rgba(match: re.Match) -> str:
        r, g, b, a = match.groups()
        tint = "#%02x%02x%02x" % (int(r), int(g), int(b))
        for name, token in CSS_MAP.items():
            if declared.get(name, "").strip().lower() == tint:
                return f"alpha(@hl_{token}, {a})"
        return match.group(0)

    body = re.sub(r"rgba\(\s*(\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\s*\)", rgba, body)
    header = INCLUDE["css"].format(fragment=fragment)
    return f"{header}\n{body.lstrip()}", orphans


def tokenise_sway(text: str) -> tuple[str, list[str]]:
    orphans: list[str] = []
    declared = re.findall(r"^set \$(\w+)\s+#[0-9a-fA-F]{6}\s*$", text, re.M)
    for name in declared:
        if name not in SWAY_MAP:
            orphans.append(name)
    body = re.sub(r"^set \$\w+\s+#[0-9a-fA-F]{6}\s*\n", "", text, flags=re.M)
    # Generated fragments already emit client.* lines; keeping them here would duplicate the source.
    body = re.sub(r"^client\.\w+\s+.*\n", "", body, flags=re.M)

    def swap(match: re.Match) -> str:
        name = match.group(1)
        return f"$hl_{SWAY_MAP[name]}" if name in SWAY_MAP else match.group(0)

    body = re.sub(r"\$(\w+)\b", swap, body)
    return body.replace("# Catppuccin Mocha", INCLUDE["sway"], 1) \
        if "# Catppuccin Mocha" in body else f"{INCLUDE['sway']}\n{body.lstrip()}", orphans


TARGETS = {
    "waybar.css": ("css", "waybar"),
    "gtk3.css": ("css", "gtk"),
    "gtk4.css": ("css", "gtk"),
    "hyperlab-gtk.css": ("css", "gtk"),
    "sway.config": ("sway", None),
}


def main(argv: list[str]) -> int:
    source = Path(argv[1] if len(argv) > 1 else "surfaces")
    out = source / "tokenised"
    out.mkdir(exist_ok=True)
    total_before = total_after = 0
    all_orphans: dict[str, list[str]] = {}

    for name, (dialect, fragment) in TARGETS.items():
        path = source / name
        if not path.is_file():
            print(f"  missing: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        before = len(set(re.findall(r"#[0-9a-fA-F]{6}", text)))
        result, orphans = (tokenise_css(text, fragment) if dialect == "css"
                           else tokenise_sway(text))
        after = len(set(re.findall(r"#[0-9a-fA-F]{6}", result)))
        (out / name).write_text(result, encoding="utf-8")
        total_before += before
        total_after += after
        if orphans:
            all_orphans[name] = orphans
        print(f"  {name:16} colours {before:3} -> {after:3}"
              f"{'   unmapped: ' + ', '.join(orphans) if orphans else ''}")

    print(f"\ntotal unique colours across the three surfaces: {total_before} -> {total_after}")

    # Remaining values are derived colours and must be reviewed rather than silently flattened.
    residual: dict[str, list[str]] = {}
    for name in TARGETS:
        path = out / name
        if path.is_file():
            found = sorted(set(re.findall(r"#[0-9a-fA-F]{6}", path.read_text())))
            if found:
                residual[name] = found
    if residual:
        print("\nremaining inline derived colours:")
        for name, tints in residual.items():
            for tint in tints:
                note = " (shadow, not a palette colour)" if tint == "#000000" else ""
                print(f"  {name}: {tint}{note}")
        print("  -> flatten them to @hl_text or express them as "
              "mix(@hl_text, @hl_<token>, .2): this is a design decision, not a measurement")
    if all_orphans:
        print("\nnames without tokens, left unchanged for explicit review:")
        for name, orphans in all_orphans.items():
            for orphan in orphans:
                print(f"  {name}: @{orphan}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
