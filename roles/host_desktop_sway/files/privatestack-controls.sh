#!/usr/bin/env bash
set -euo pipefail

# Compact Rofi control index for every desktop toggle and the most important
# cockpit actions. Hovering the Waybar button shows current state; clicking it
# opens this menu.
readonly rofi_theme=${XDG_CONFIG_HOME:-"${HOME}/.config"}/rofi/rofi-hyperlab.rasi
readonly theme_ctl=/usr/local/bin/privatestack-theme
readonly keyboard_ctl=/usr/local/bin/privatestack-keyboard

menu() {
    local prompt=$1
    shift
    printf '%s\n' "$@" | rofi -dmenu -no-show-icons -i -p "${prompt}" -theme "${rofi_theme}" || return 1
}

title_case() {
    case ${1:-} in
        green) printf 'Green\n' ;;
        violet) printf 'Violet\n' ;;
        blue) printf 'Blue\n' ;;
        red) printf 'Red\n' ;;
        public) printf 'Public\n' ;;
        personal) printf 'Personal\n' ;;
        *) printf '%s\n' "${1:-Unknown}" ;;
    esac
}

status_json() {
    local theme mode keyboard
    theme=$(${theme_ctl} status)
    mode=$(${theme_ctl} mode)
    keyboard=$(${keyboard_ctl} label)
    python3 - "${theme}" "${mode}" "${keyboard}" <<'PY'
import json
import sys

theme, mode, keyboard = sys.argv[1:]
payload = {
    "text": "󰒓 CTL",
    "tooltip": (
        f"Theme: {theme.title()}\n"
        f"Wallpaper: {mode.title()}\n"
        f"Keyboard: {keyboard}\n"
        "Click to open all controls\n"
        "Theme: Mod+Shift+T · Wallpaper: Mod+Shift+W · Keyboard: Mod+Ctrl+Space"
    ),
    "class": "controls",
}
print(json.dumps(payload, ensure_ascii=False))
PY
}

choose_theme() {
    local choice
    choice=$(menu 'Theme' 'Green' 'Violet' 'Blue' 'Red') || return 0
    [[ -n ${choice} ]] || return 0
    ${theme_ctl} set "${choice,,}"
}

choose_keyboard() {
    local choice
    choice=$(menu 'Keyboard layout' 'Italian' 'English (US)' 'Arabic') || return 0
    case ${choice:-} in
        Italian) ${keyboard_ctl} set it ;;
        'English (US)') ${keyboard_ctl} set us ;;
        Arabic) ${keyboard_ctl} set ara ;;
    esac
}

open_menu() {
    local theme mode keyboard choice
    theme=$(${theme_ctl} status)
    mode=$(${theme_ctl} mode)
    keyboard=$(${keyboard_ctl} label)
    choice=$(menu 'HyperLab Controls' \
        "Theme · $(title_case "${theme}")" \
        "Wallpaper · $(title_case "${mode}")" \
        "Keyboard · ${keyboard}" \
        'Terminal opacity · Toggle' \
        'Current window fullscreen · Toggle' \
        'Bar visibility · Toggle' \
        'Lock screen' \
        'HyperLab quick VM drawer' \
        'HyperLab quick diagnostics' \
        'HyperLab full Control Center' \
        'Power menu') || return 0

    case ${choice:-} in
        'Theme · '*) choose_theme ;;
        'Wallpaper · '*) ${theme_ctl} mode-toggle ;;
        'Keyboard · '*) choose_keyboard ;;
        'Terminal opacity · Toggle') /usr/local/bin/privatestack-opacity-toggle ;;
        'Current window fullscreen · Toggle') swaymsg -q fullscreen toggle >/dev/null ;;
        'Bar visibility · Toggle') /usr/local/bin/privatestack-waybar toggle ;;
        'Lock screen') /usr/local/bin/privatestack-swaylock ;;
        'HyperLab quick VM drawer') /usr/local/bin/privatestack-hyperlab-domains --surface drawer --section vms ;;
        'HyperLab quick diagnostics') /usr/local/bin/privatestack-hyperlab-domains --surface drawer --section diagnostics ;;
        'HyperLab full Control Center') /usr/local/bin/privatestack-hyperlab-domains --surface overlay --section vms ;;
        'Power menu') /usr/local/bin/privatestack-powermenu ;;
    esac
}

case ${1:-menu} in
    menu|open) open_menu ;;
    status-json|json) status_json ;;
    keyboard) choose_keyboard ;;
    theme) choose_theme ;;
    *) printf 'usage: %s {menu|status-json|keyboard|theme}\n' "$0" >&2; exit 2 ;;
esac
