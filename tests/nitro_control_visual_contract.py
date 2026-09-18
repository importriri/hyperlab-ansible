#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

CSS = (
    ROOT
    / "roles"
    / "host_desktop_sway"
    / "files"
    / "hyperlab-gtk.css"
).read_text(encoding="utf-8")


required = (
    "dropdown {",
    "dropdown button {",
    "dropdown arrow {",
    "popover listview {",
    "popover listview row {",
    "popover listview row label {",
    "popover listview row:hover {",
    "popover listview row:selected {",
    "popover listview row:selected label {",
)

for selector in required:
    assert CSS.count(selector) == 1, selector

assert "background-color: @hl_base;" in CSS
assert "color: @hl_text;" in CSS

disabled = CSS.split(
    "button:disabled {",
    1,
)[1].split("}", 1)[0]

assert "alpha(@hl_subtext, 0.82)" in disabled
assert "alpha(@hl_accent, 0.18)" in disabled

popup = CSS.split(
    "popover listview {",
    1,
)[1]

assert "row:hover" in popup
assert "row:selected" in popup
assert "row:selected label" in popup

print("Nitro Control Center visual contract: OK")
