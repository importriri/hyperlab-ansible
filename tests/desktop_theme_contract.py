#!/usr/bin/env python3
"""Structural contract for four palettes and public/personal wallpaper modes."""
from __future__ import annotations
import hashlib
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def require(condition: bool, message: str) -> None:
    if not condition: raise SystemExit(f"desktop theme contract: {message}")
def text(relative: str) -> str: return (ROOT / relative).read_text(encoding="utf-8")
def main() -> int:
    sway = text("roles/host_desktop_sway/files/sway.config")
    for marker in (
        "privatestack-waybar toggle", "privatestack-theme cycle",
        "privatestack-theme mode-toggle", "privatestack-theme daemon",
        "privatestack-hyperlab-domains --warm",
        "/usr/share/backgrounds/privatestack/public/green/01.png",
    ): require(marker in sway, f"Sway integration missing: {marker}")
    theme = text("roles/host_desktop_sway/files/privatestack-theme.sh")
    for marker in (
        "readonly themes=(green violet blue red)", "public_wallpaper_count=20",
        "personal_wallpaper_count", "active_wallpaper_count",
        "public_wallpaper_root", "personal_wallpaper_root", "wallpaper_mode_file",
        "mode-toggle", "mode-json", "hyperlab-palette-swaylock.conf",
        "lock_index=$(( (desktop_index + 3) % count ))",
    ): require(marker in theme, f"theme controller missing: {marker}")
    status = text("roles/host_desktop_sway/files/privatestack-swaybar-status.py")
    for variant in ("green", "violet", "blue", "red"):
        require(f'"{variant}"' in status, f"fallback Swaybar palette missing: {variant}")
    require('block("wallpaper"' in status and '"mode-toggle"' in status,
            "fallback wallpaper toggle missing")
    waybar = text("roles/host_desktop_sway/files/waybar.jsonc")
    require('"custom/wallpaper-mode"' in waybar and '"signal": 9' in waybar,
            "Waybar wallpaper-mode toggle missing")
    hashes: dict[str, Path] = {}
    for variant in ("green", "violet", "blue", "red"):
        files = sorted((ROOT / f"roles/host_desktop_sway/files/wallpapers/{variant}").glob("*.png"))
        require(len(files) == 20, f"{variant} does not contain twenty public wallpapers")
        for path in files:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            require(digest not in hashes, f"duplicate wallpaper: {path} and {hashes.get(digest)}")
            hashes[digest] = path
            require(path.stat().st_size > 25000, f"wallpaper suspiciously small: {path}")
        lock = ROOT / f"roles/host_desktop_sway/files/palette/{variant}/hyperlab-palette-swaylock.conf"
        require(lock.is_file(), f"swaylock palette missing: {variant}")
        content = lock.read_text(encoding="utf-8")
        require("ring-color=" in content and "inside-wrong-color=" in content,
                f"swaylock colors incomplete: {variant}")
    require("wallpapers/personal/" in text(".gitignore"),
            "personal wallpaper ignore rule missing")
    print("HyperLab four-theme and wallpaper-mode contract: OK")
    return 0
if __name__ == "__main__": raise SystemExit(main())
