#!/usr/bin/env python3
"""Narrow ownership contract for the host Looking Glass role."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/looking_glass"

required = [
    ROLE / "defaults/main.yml",
    ROLE / "tasks/main.yml",
    ROLE / "handlers/main.yml",
    ROLE / "templates/client.ini.j2",
]
for path in required:
    assert path.is_file(), path

tasks = (ROLE / "tasks/main.yml").read_text(encoding="utf-8")
defaults = (ROLE / "defaults/main.yml").read_text(encoding="utf-8")
client = (ROLE / "templates/client.ini.j2").read_text(encoding="utf-8")

assert "looking_glass" in tasks.lower()
assert "looking_glass" in defaults.lower()
assert client.strip()
print("Looking Glass host role ownership contract: OK")
