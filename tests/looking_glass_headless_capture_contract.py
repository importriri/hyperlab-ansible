#!/usr/bin/env python3
"""Narrow contract for deterministic Linux guest Looking Glass capture."""
from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/guest_looking_glass_linux"


def main() -> int:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    tasks = (ROLE / "tasks/main.yml").read_text()

    assert defaults["guest_looking_glass_linux_capture_output"] == "HEADLESS-0"
    assert defaults["guest_looking_glass_linux_capture_max_fps"] == 144
    assert defaults["guest_looking_glass_linux_xdph_picker"] == (
        "/usr/local/bin/privatestack-looking-glass-xdph-picker"
    )
    assert defaults["guest_looking_glass_linux_xdph_config"] == (
        "/home/{{ admin_user }}/.config/hypr/xdph.conf"
    )

    assert "xdph-headless-picker.sh.j2" in tasks
    assert "xdph.conf.j2" in tasks
    assert "systemctl enable looking-glass-host" not in tasks

    env = Environment(
        loader=FileSystemLoader(str(ROLE / "templates")),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )

    picker = env.get_template("xdph-headless-picker.sh.j2").render(
        guest_looking_glass_linux_capture_output="HEADLESS-0",
    )
    assert "/usr/bin/hyprctl -j monitors" in picker
    assert "json.load(sys.stdin)" in picker
    assert "guest_looking_glass_linux_capture_output='HEADLESS-0'" in picker
    assert "[SELECTION]/screen:%s\\n" in picker

    shellcheck = subprocess.run(
        ["shellcheck", "-s", "bash", "-"],
        input=picker,
        text=True,
        capture_output=True,
        check=False,
    )
    assert shellcheck.returncode == 0, shellcheck.stderr

    config = env.get_template("xdph.conf.j2").render(
        guest_looking_glass_linux_capture_max_fps=144,
        guest_looking_glass_linux_xdph_picker=(
            "/usr/local/bin/privatestack-looking-glass-xdph-picker"
        ),
    )
    assert "max_fps = 144" in config
    assert (
        "custom_picker_binary = "
        "/usr/local/bin/privatestack-looking-glass-xdph-picker"
    ) in config

    print("Looking Glass headless capture contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
