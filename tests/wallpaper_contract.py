#!/usr/bin/env python3
"""Contract for publishable nature pools and untracked personal wallpaper data."""
from __future__ import annotations

import hashlib
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POOL = ROOT / "roles/host_desktop_sway/files/wallpapers"
THEMES = ("green", "violet", "blue", "red")
EXPECTED = tuple(f"{index:02d}.png" for index in range(1, 21))


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"wallpaper contract: {message}")


def main() -> int:
    hashes: dict[str, Path] = {}
    for theme in THEMES:
        paths = sorted((POOL / theme).glob("*.png"))
        require(tuple(path.name for path in paths) == EXPECTED,
                f"{theme} must contain exactly 01.png through 20.png")
        for path in paths:
            require(path.stat().st_size > 25_000, f"suspiciously small asset: {path}")
            header = path.read_bytes()[:24]
            require(header[:8] == b"\x89PNG\r\n\x1a\n", f"not a PNG: {path}")
            width, height = struct.unpack(">II", header[16:24])
            require((width, height) == (1600, 900),
                    f"not 16:9 1600x900: {path}")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            require(digest not in hashes,
                    f"byte-identical public assets: {path} and {hashes.get(digest)}")
            hashes[digest] = path

    require(not (POOL / "personal").exists(),
            "personal wallpaper data must never exist in the repository tree")
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    require("roles/host_desktop_sway/files/wallpapers/personal/" in ignored,
            "repository-local personal pool is not explicitly ignored")
    require("personal-wallpapers/" in ignored,
            "package-staging personal pool is not explicitly ignored")
    print("public/personal wallpaper boundary contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
