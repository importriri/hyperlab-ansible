#!/usr/bin/python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

THEMES = {
    "sakura-circuit": {
        "background": "17111d",
        "foreground": "f7e8ff",
        "surface": "25192e",
        "accent": "ff70b7",
        "accent_alt": "59e1ff",
        "urgent": "ff557f",
    },
    "neon-terminal": {
        "background": "080b18",
        "foreground": "e8efff",
        "surface": "11172a",
        "accent": "886cff",
        "accent_alt": "24d9ff",
        "urgent": "ff4d8d",
    },
    "moon-library": {
        "background": "0d1224",
        "foreground": "e8eaff",
        "surface": "171d35",
        "accent": "b39cff",
        "accent_alt": "86c8ff",
        "urgent": "ff6f91",
    },
    "glitch-lab": {
        "background": "111315",
        "foreground": "f0fff4",
        "surface": "1b2021",
        "accent": "ff3cac",
        "accent_alt": "72ff72",
        "urgent": "ff5252",
    },
}

ORDER = tuple(THEMES)
HOME = Path.home()
CONFIG = HOME / ".config"
STATE_DIR = HOME / ".local/state/privatestack-guest-theme"
STATE_FILE = STATE_DIR / "state.json"
WALL_ROOT = Path("/usr/share/backgrounds/privatestack-guest")


def write_if_changed(path: Path, content: str) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.is_file() and path.read_text() == content:
        return False

    temporary = path.with_name(path.name + ".new")
    temporary.write_text(content)
    temporary.chmod(0o644)
    temporary.replace(path)
    return True


def load_state() -> dict[str, object]:
    if not STATE_FILE.is_file():
        return {}

    try:
        data = json.loads(STATE_FILE.read_text())
    except json.JSONDecodeError:
        return {}

    return data if isinstance(data, dict) else {}


def available_images(theme: str, surface: str) -> list[Path]:
    pool = WALL_ROOT / theme / surface
    return sorted(
        path
        for path in pool.glob("*.png")
        if path.is_file()
    )


def choose_image(
    theme: str,
    surface: str,
    previous: str,
    rotate: bool,
) -> Path:
    images = available_images(theme, surface)

    if not images:
        raise RuntimeError(
            f"No {surface} wallpapers are installed for {theme}"
        )

    previous_path = Path(previous) if previous else None

    if (
        not rotate
        and previous_path is not None
        and previous_path in images
    ):
        return previous_path

    if previous_path is not None and previous_path in images:
        current_index = images.index(previous_path)
        return images[(current_index + 1) % len(images)]

    return images[0]


def gtk_css(
    background: str,
    foreground: str,
    surface: str,
    accent: str,
    urgent: str,
) -> str:
    return f"""@define-color theme_bg_color #{background};
@define-color theme_fg_color #{foreground};
@define-color theme_base_color #{surface};
@define-color theme_text_color #{foreground};
@define-color theme_selected_bg_color #{accent};
@define-color theme_selected_fg_color #{background};
@define-color error_color #{urgent};

window,
dialog,
.background {{
    background-color: @theme_bg_color;
    color: @theme_fg_color;
}}

headerbar,
toolbar,
.sidebar {{
    background-color: @theme_base_color;
    color: @theme_fg_color;
}}

selection,
*:selected {{
    background-color: @theme_selected_bg_color;
    color: @theme_selected_fg_color;
}}
"""


def palette_files(
    theme: str,
    desktop_wallpaper: Path,
    lock_wallpaper: Path,
) -> dict[Path, str]:
    palette = THEMES[theme]
    background = palette["background"]
    foreground = palette["foreground"]
    surface = palette["surface"]
    accent = palette["accent"]
    accent_alt = palette["accent_alt"]
    urgent = palette["urgent"]

    generated_gtk_css = gtk_css(
        background,
        foreground,
        surface,
        accent,
        urgent,
    )

    return {
        CONFIG / "hypr/theme.lua": f"""hl.config({{
    general = {{
        col = {{
            active_border = {{
                colors = {{
                    "rgba({accent}ff)",
                    "rgba({accent_alt}ff)",
                }},
                angle = 45,
            }},

            inactive_border = "rgba({surface}ff)",
        }},
    }},

    decoration = {{
        shadow = {{
            color = "rgba({background}cc)",
        }},
    }},
}})
""",
        CONFIG / "hypr/hyprlock-theme.conf": f"""$guest_foreground = rgb({foreground})
$guest_surface = rgb({surface})
$guest_accent = rgb({accent})
$guest_lock_wallpaper = {lock_wallpaper}
""",
        CONFIG / "waybar/theme.css": f"""@define-color guest_background #{background};
@define-color guest_foreground #{foreground};
@define-color guest_surface #{surface};
@define-color guest_accent #{accent};
@define-color guest_accent_alt #{accent_alt};
@define-color guest_urgent #{urgent};
""",
        CONFIG / "kitty/theme.conf": f"""background #{background}
foreground #{foreground}
selection_background #{accent}
selection_foreground #{background}
cursor #{accent_alt}
cursor_text_color #{background}
url_color #{accent_alt}
active_border_color #{accent}
inactive_border_color #{surface}
active_tab_background #{accent}
active_tab_foreground #{background}
inactive_tab_background #{surface}
inactive_tab_foreground #{foreground}
color0 #{background}
color1 #{urgent}
color2 #{accent_alt}
color3 #{accent}
color4 #{accent_alt}
color5 #{accent}
color6 #{accent_alt}
color7 #{foreground}
""",
        CONFIG / "rofi/theme.rasi": f"""* {{
    background: #{background}ee;
    foreground: #{foreground};
    surface: #{surface};
    accent: #{accent};
    accent-alt: #{accent_alt};
    urgent: #{urgent};
}}

window {{
    width: 46%;
    border: 2px;
    border-color: @accent;
    border-radius: 14px;
    background-color: @background;
    padding: 18px;
}}

mainbox {{
    background-color: transparent;
    spacing: 12px;
}}

inputbar {{
    background-color: @surface;
    text-color: @foreground;
    border-radius: 10px;
    padding: 10px;
}}

listview {{
    background-color: transparent;
    columns: 1;
    lines: 9;
    spacing: 5px;
}}

element {{
    background-color: transparent;
    text-color: @foreground;
    border-radius: 9px;
    padding: 8px;
}}

element selected {{
    background-color: @accent;
    text-color: #{background};
}}
""",
        CONFIG / "mako/config": f"""font=JetBrainsMono Nerd Font 11
background-color=#{background}ee
text-color=#{foreground}
border-color=#{accent}
border-size=2
border-radius=12
padding=12
default-timeout=6000
anchor=top-right
width=360
max-visible=5
""",
        CONFIG / "gtk-3.0/gtk.css": generated_gtk_css,
        CONFIG / "gtk-4.0/gtk.css": generated_gtk_css,
        CONFIG / "privatestack-guest/current-desktop-wallpaper": (
            f"{desktop_wallpaper}\n"
        ),
        CONFIG / "privatestack-guest/current-lock-wallpaper": (
            f"{lock_wallpaper}\n"
        ),
    }


def save_state(state: dict[str, object]) -> bool:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    content = json.dumps(
        state,
        indent=2,
        sort_keys=True,
    ) + "\n"
    return write_if_changed(STATE_FILE, content)


def ensure_awww() -> None:
    if not shutil.which("awww"):
        return

    query = subprocess.run(
        ["awww", "query"],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    if query.returncode == 0:
        return

    if not shutil.which("awww-daemon"):
        return

    subprocess.Popen(
        ["awww-daemon"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    time.sleep(0.5)


def runtime_refresh(desktop_wallpaper: Path) -> None:
    wayland_active = bool(os.environ.get("WAYLAND_DISPLAY"))

    if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
        subprocess.run(
            ["hyprctl", "reload"],
            check=False,
        )

    if wayland_active:
        subprocess.run(
            ["pkill", "-x", "waybar"],
            check=False,
        )
        subprocess.Popen(
            ["waybar"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

    if shutil.which("makoctl"):
        subprocess.run(
            ["makoctl", "reload"],
            check=False,
        )

    if shutil.which("kitty"):
        subprocess.run(
            [
                "kitty",
                "@",
                "set-colors",
                "--all",
                str(CONFIG / "kitty/theme.conf"),
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    if wayland_active:
        ensure_awww()

        subprocess.run(
            [
                "awww",
                "img",
                str(desktop_wallpaper),
                "--transition-type",
                "grow",
                "--transition-duration",
                "1.1",
            ],
            check=False,
        )


def apply_theme(
    theme: str,
    runtime: bool,
    rotate: bool,
) -> bool:
    if theme not in THEMES:
        raise RuntimeError(
            f"Unknown guest theme: {theme}"
        )

    previous_state = load_state()
    previous_desktop = str(
        previous_state.get("desktop_wallpaper", "")
    )
    previous_lock = str(
        previous_state.get("lock_wallpaper", "")
    )

    desktop_wallpaper = choose_image(
        theme,
        "desktop",
        previous_desktop,
        rotate,
    )
    lock_wallpaper = choose_image(
        theme,
        "lockscreen",
        previous_lock,
        rotate,
    )

    changed = False

    for path, content in palette_files(
        theme,
        desktop_wallpaper,
        lock_wallpaper,
    ).items():
        changed = write_if_changed(path, content) or changed

    history_desktop = (
        previous_desktop
        if rotate
        else str(
            previous_state.get(
                "previous_desktop_wallpaper",
                "",
            )
        )
    )

    history_lock = (
        previous_lock
        if rotate
        else str(
            previous_state.get(
                "previous_lock_wallpaper",
                "",
            )
        )
    )

    state = {
        "theme": theme,
        "desktop_wallpaper": str(desktop_wallpaper),
        "lock_wallpaper": str(lock_wallpaper),
        "previous_desktop_wallpaper": history_desktop,
        "previous_lock_wallpaper": history_lock,
    }

    changed = save_state(state) or changed

    if runtime:
        runtime_refresh(desktop_wallpaper)

    return changed


def current_theme() -> str:
    state = load_state()
    theme = state.get("theme")

    if isinstance(theme, str) and theme in THEMES:
        return theme

    return ORDER[0]


def next_theme() -> str:
    current = current_theme()
    current_index = ORDER.index(current)
    return ORDER[(current_index + 1) % len(ORDER)]


def rofi_menu() -> None:
    process = subprocess.run(
        ["rofi", "-dmenu", "-p", "Guest theme"],
        input="\n".join(ORDER) + "\n",
        text=True,
        capture_output=True,
        check=False,
    )

    selected = process.stdout.strip()

    if selected in THEMES:
        apply_theme(
            selected,
            runtime=True,
            rotate=True,
        )


def main() -> None:
    action = (
        sys.argv[1]
        if len(sys.argv) > 1
        else "status"
    )

    if action == "status":
        print(current_theme())
        return

    if action == "prepare":
        changed = apply_theme(
            current_theme(),
            runtime=False,
            rotate=False,
        )

        print(
            "GUEST_THEME_CHANGED"
            if changed
            else "GUEST_THEME_READY"
        )
        return

    if action == "session-start":
        selected = current_theme()

        apply_theme(
            selected,
            runtime=True,
            rotate=False,
        )

        print(selected)
        return

    if action == "set":
        if len(sys.argv) < 3:
            raise RuntimeError(
                "set requires a theme name"
            )

        selected = sys.argv[2]
        apply_theme(
            selected,
            runtime=True,
            rotate=True,
        )
        print(selected)
        return

    if action == "next":
        selected = next_theme()
        apply_theme(
            selected,
            runtime=True,
            rotate=True,
        )
        print(selected)
        return

    if action == "wallpaper-next":
        selected = current_theme()
        apply_theme(
            selected,
            runtime=True,
            rotate=True,
        )
        print(selected)
        return

    if action == "menu":
        rofi_menu()
        return

    raise RuntimeError(
        f"Unknown guest theme action: {action}"
    )


main()
