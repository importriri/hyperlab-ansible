#!/usr/bin/env python3
"""Structural contract for the Nitro Control Board in HyperLab."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANAGER = ROOT / "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py"

manager = MANAGER.read_text(encoding="utf-8")
compile(manager, str(MANAGER), "exec")

for marker in (
    'NITRO_CONTROL = "/usr/local/bin/hyperlab-nitro-control"',
    'THEME_CONTROL = "/usr/local/bin/privatestack-theme"',
    'DESKTOP_THEMES = ("green", "violet", "blue", "red")',
    '("nitro", "Nitro")',
    '"nitro": self._build_nitro',
    "def run_nitro_json(",
    "def run_theme(",
    "def _nitro_set_theme(",
    "def _nitro_theme_card(",
    "def _build_nitro(",
    '"Nitro Control Board"',
    '"Apply fan values"',
    '"Apply battery limiter"',
    '"Apply four-zone RGB"',
    '"Appearance only. Trust colors keep their fixed semantic meaning."',
):
    assert marker in manager, marker

assert "/sys/module/linuwu_sense" not in manager
assert "pkexec" not in manager
assert "sudo " not in manager
assert "shell=True" not in manager
assert "os.system" not in manager

nitro_start = manager.index("    def _nitro_write(")
nitro_end = manager.index("    def _build_activity(", nitro_start)
nitro = manager[nitro_start:nitro_end]

assert "run_nitro_json(*args)" in nitro
assert 'run_theme("set", theme)' in nitro
assert 'run_theme("status")' in nitro
assert 'capabilities.get("fan") is True' in nitro
assert 'capabilities.get("battery_limiter") is True' in nitro
assert 'capabilities.get("per_zone") is True' in nitro
assert "backlight_timeout" not in nitro
assert "four_zone_mode" not in nitro
assert "effect" not in nitro
assert "Theme Sync" not in nitro
assert "Trust Sync" not in nitro
assert "timeout_add" not in nitro
assert "threading.Thread" not in nitro

theme_helper = (
    ROOT / "roles/host_desktop_sway/files/privatestack-theme.sh"
).read_text(encoding="utf-8")
assert 'readonly themes=(green violet blue red)' in theme_helper
assert 'set) set_theme "${2:-}"' in theme_helper

print("Nitro Control Board v2 contract: OK")
