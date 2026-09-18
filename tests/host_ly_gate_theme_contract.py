#!/usr/bin/env python3
"""HyperLab // Gate host Ly presentation contract."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read(path):
    return (ROOT / path).read_text(encoding="utf-8")


def main():
    defaults = read("roles/host_desktop_sway/defaults/main.yml")
    tasks = read("roles/host_desktop_sway/tasks/main.yml")
    startup = read(
        "roles/host_desktop_sway/templates/ly-hyperlab-startup.sh.j2"
    )

    require(
        "host_desktop_sway_ly_gate_theme:" in defaults,
        "dedicated Gate theme declaration missing",
    )
    require(
        "host_desktop_sway_ly_palettes:" not in defaults,
        "legacy desktop-coupled Ly palettes remain declared",
    )

    for marker in (
        'bg: "0x00070608"',
        'fg: "0x00D8DADF"',
        'border_fg: "0x01C92D49"',
        'error_bg: "0x0015080D"',
        'error_fg: "0x01FF5870"',
        'matrix_fg: "0x0080192C"',
        'matrix_head_col: "0x01FF3657"',
        'box_title: "HyperLab Gate"',
        'initial_info_text: "HyperLab host gateway"',
    ):
        require(marker in defaults, f"Gate default missing: {marker}")

    start = tasks.index("- name: Validate the dedicated HyperLab Gate theme")
    end = tasks.index("- name: Enable ly on tty2")
    ly_section = tasks[start:end]

    require(
        "{{ desktop_palette" not in ly_section
        and "host_desktop_sway_ly_palettes[" not in ly_section
        and "host_desktop_sway_ly_palettes.get" not in ly_section,
        "Ly Gate contains an active desktop-palette reference",
    )
    require(
        "host_desktop_sway_ly_palettes" not in ly_section,
        "legacy Ly palette map remains active",
    )

    for marker in (
        'animation, value: "matrix"',
        'animation_frame_delay, value: "25"',
        "cmatrix_fg",
        "cmatrix_head_col",
        "host_desktop_sway_ly_gate_theme",
        'bigclock, value: "en"',
        'start_cmd, value: "/etc/ly/hyperlab-startup.sh"',
    ):
        require(marker in ly_section, f"Gate task marker missing: {marker}")

    for retired in (
        "colormix_col1",
        "colormix_col2",
        "colormix_col3",
    ):
        require(
            retired not in ly_section,
            f"retired colormix key remains active: {retired}",
        )

    require(
        "host_desktop_sway_ly_gate_theme" in startup,
        "VT palette is disconnected from Gate",
    )
    require(
        "desktop_palette" not in startup,
        "VT palette still follows the desktop theme",
    )
    require(
        "\\033]P0" in startup and "\\033]PF" in startup,
        "VT palette hook is incomplete",
    )

    print("host Ly Gate theme contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
