#!/usr/bin/env bash
set -euo pipefail

# Runtime theme + wallpaper controller. Root-owned public pools are safe to
# publish. User-owned personal pools are never read by Ansible and never enter Git.

readonly palette_root=${HYPERLAB_PALETTE_ROOT:-/usr/share/hyperlab/palettes}
readonly public_wallpaper_root=${HYPERLAB_PUBLIC_WALLPAPER_ROOT:-/usr/share/backgrounds/privatestack/public}
readonly data_home=${XDG_DATA_HOME:-"${HOME}/.local/share"}
readonly personal_wallpaper_root=${HYPERLAB_PERSONAL_WALLPAPER_ROOT:-${data_home}/hyperlab/wallpapers/personal}
readonly config_home=${XDG_CONFIG_HOME:-"${HOME}/.config"}
readonly state_home=${XDG_STATE_HOME:-"${HOME}/.local/state"}
readonly config_dir=${config_home}/hyperlab
readonly state_dir=${state_home}/hyperlab
readonly theme_file=${config_dir}/theme
readonly wallpaper_mode_file=${config_dir}/wallpaper-mode
readonly desktop_index_file=${state_dir}/wallpaper-index
readonly desktop_path_file=${state_dir}/desktop-wallpaper
readonly sway_socket=${SWAYSOCK:-}
readonly daemon_key=${sway_socket##*/}
readonly daemon_lock=${XDG_RUNTIME_DIR:-${state_dir}}/hyperlab-wallpaper-${daemon_key:-sway}.lock
readonly wallpaper_count=20
readonly rotation_seconds=${HYPERLAB_WALLPAPER_INTERVAL:-60}
readonly themes=(green violet blue red)

mkdir -p "${config_dir}" "${state_dir}" "${personal_wallpaper_root}"

notify() {
    if command -v notify-send >/dev/null 2>&1; then
        notify-send "HyperLab" "$1" || true
    fi
}

valid_theme() { case ${1:-} in green|violet|blue|red) return 0 ;; *) return 1 ;; esac; }
valid_mode() { case ${1:-} in public|personal) return 0 ;; *) return 1 ;; esac; }

current_theme() {
    local value=green
    if [[ -r ${theme_file} ]]; then
        IFS= read -r value <"${theme_file}" || true
    fi
    valid_theme "${value}" || value=green
    printf '%s\n' "${value}"
}

current_mode() {
    local value=public
    if [[ -r ${wallpaper_mode_file} ]]; then
        IFS= read -r value <"${wallpaper_mode_file}" || true
    fi
    valid_mode "${value}" || value=public
    printf '%s\n' "${value}"
}

write_atomic() {
    local destination=$1 value=$2 temporary
    mkdir -p "$(dirname "${destination}")"
    temporary="${destination}.tmp.$$"
    printf '%s\n' "${value}" >"${temporary}"
    chmod 0644 "${temporary}"
    mv -f "${temporary}" "${destination}"
}

copy_atomic() {
    local source=$1 destination=$2 temporary
    [[ -r ${source} ]] || { printf 'HyperLab: missing file: %s\n' "${source}" >&2; return 1; }
    mkdir -p "$(dirname "${destination}")"
    temporary="${destination}.tmp.$$"
    cp -- "${source}" "${temporary}"
    chmod 0644 "${temporary}"
    mv -f "${temporary}" "${destination}"
}

read_index() {
    local value=0
    if [[ -r ${desktop_index_file} ]]; then
        IFS= read -r value <"${desktop_index_file}" || true
    fi
    [[ ${value} =~ ^[0-9]+$ ]] || value=0
    printf '%s\n' "$(( value % wallpaper_count ))"
}

public_wallpaper_path() { printf '%s/%s/%02d.png\n' "${public_wallpaper_root}" "$1" "$(( $2 + 1 ))"; }
personal_wallpaper_path() { printf '%s/%s/%02d.png\n' "${personal_wallpaper_root}" "$1" "$(( $2 + 1 ))"; }

wallpaper_path() {
    local theme=$1 index=$2 mode image
    mode=$(current_mode)
    if [[ ${mode} == personal ]]; then
        image=$(personal_wallpaper_path "${theme}" "${index}")
        if [[ -r ${image} ]]; then printf '%s\n' "${image}"; return 0; fi
    fi
    image=$(public_wallpaper_path "${theme}" "${index}")
    [[ -r ${image} ]] || { printf 'HyperLab: missing public wallpaper: %s\n' "${image}" >&2; return 1; }
    printf '%s\n' "${image}"
}

install_active_palette() {
    local theme=$1 source_dir=${palette_root}/$1
    copy_atomic "${source_dir}/hyperlab-palette.sway" "${config_dir}/palette.sway"
    copy_atomic "${source_dir}/hyperlab-palette.rasi" "${config_dir}/palette.rasi"
    copy_atomic "${source_dir}/hyperlab-palette-foot.ini" "${config_dir}/palette-foot.ini"
    copy_atomic "${source_dir}/hyperlab-palette-gtk.css" "${config_home}/gtk-3.0/hyperlab-palette.css"
    copy_atomic "${source_dir}/hyperlab-palette-gtk.css" "${config_home}/gtk-4.0/hyperlab-palette.css"
    copy_atomic "${source_dir}/hyperlab-palette-waybar.css" "${config_home}/waybar/palette.css"
    copy_atomic "${source_dir}/hyperlab-palette-superfile.toml" "${config_home}/superfile/theme/hyperlab.toml"
    copy_atomic "${source_dir}/hyperlab-palette-swaylock.conf" "${config_home}/swaylock/config"
}

set_desktop_wallpaper() {
    local theme=$1 index=$2 image
    image=$(wallpaper_path "${theme}" "${index}")
    write_atomic "${desktop_index_file}" "${index}"
    write_atomic "${desktop_path_file}" "${image}"
    swaymsg -q output '*' bg "${image}" fill >/dev/null
}

reload_palette_consumers() {
    pkill -USR2 -x waybar 2>/dev/null || true
    /usr/local/bin/privatestack-hyperlab-domains --reload-theme >/dev/null 2>&1 || true
}

signal_wallpaper_mode() { pkill -SIGRTMIN+9 -x waybar 2>/dev/null || true; }
signal_controls() { pkill -SIGRTMIN+11 -x waybar 2>/dev/null || true; }

session_start() {
    local theme index
    theme=$(current_theme); index=$(read_index)
    install_active_palette "${theme}"
    set_desktop_wallpaper "${theme}" "${index}"
    reload_palette_consumers
    signal_wallpaper_mode
    signal_controls
}

set_theme() {
    local theme=$1
    valid_theme "${theme}" || { printf 'usage: %s set green|violet|blue|red\n' "$0" >&2; return 2; }
    write_atomic "${theme_file}" "${theme}"
    write_atomic "${desktop_index_file}" 0
    install_active_palette "${theme}"
    set_desktop_wallpaper "${theme}" 0
    reload_palette_consumers
    signal_wallpaper_mode
    signal_controls
    swaymsg -q reload >/dev/null
    notify "Theme: ${theme^^}"
}

cycle_theme() {
    local current next=green i
    current=$(current_theme)
    for i in "${!themes[@]}"; do
        if [[ ${themes[$i]} == "${current}" ]]; then next=${themes[$(( (i + 1) % ${#themes[@]} ))]}; break; fi
    done
    set_theme "${next}"
}

set_mode() {
    local mode=$1 theme index
    valid_mode "${mode}" || { printf 'usage: %s mode-set public|personal\n' "$0" >&2; return 2; }
    write_atomic "${wallpaper_mode_file}" "${mode}"
    theme=$(current_theme); index=$(read_index)
    set_desktop_wallpaper "${theme}" "${index}"
    signal_wallpaper_mode
    signal_controls
    if [[ ${mode} == personal ]] && [[ ! -r $(personal_wallpaper_path "${theme}" "${index}") ]]; then
        notify "PERSONAL mode is active but its local asset is missing; using the ${theme^^} public fallback."
    else
        notify "Wallpaper: ${mode^^}"
    fi
}

toggle_mode() {
    if [[ $(current_mode) == public ]]; then
        set_mode personal
    else
        set_mode public
    fi
}

mode_json() {
    local mode theme sample available=true
    mode=$(current_mode); theme=$(current_theme)
    sample=$(personal_wallpaper_path "${theme}" "$(read_index)")
    [[ ${mode} == personal && ! -r ${sample} ]] && available=false
    if [[ ${mode} == public ]]; then
        printf '{"text":" PUB","tooltip":"Public / chill wallpaper · click: personal","class":"public"}\n'
    elif [[ ${available} == true ]]; then
        printf '{"text":" PVT","tooltip":"Local personal wallpaper · click: public","class":"personal"}\n'
    else
        printf '{"text":" PVT?","tooltip":"PERSONAL is selected but the local pool is missing; using the public fallback","class":"fallback"}\n'
    fi
}

next_wallpaper() {
    local quiet=${1:-} theme index
    theme=$(current_theme); index=$(( ($(read_index) + 1) % wallpaper_count ))
    set_desktop_wallpaper "${theme}" "${index}"
    [[ ${quiet} == --quiet ]] || notify "Wallpaper ${theme^^}/$(current_mode) $(( index + 1 ))/${wallpaper_count}"
}

lock_image() {
    local theme desktop_index lock_index
    theme=$(current_theme); desktop_index=$(read_index)
    lock_index=$(( (desktop_index + 3) % wallpaper_count ))
    wallpaper_path "${theme}" "${lock_index}"
}

run_daemon() {
    [[ ${rotation_seconds} =~ ^[0-9]+$ ]] || { printf 'HYPERLAB_WALLPAPER_INTERVAL must be an integer.\n' >&2; return 2; }
    (( rotation_seconds >= 30 )) || { printf 'Minimum supported interval: 30 seconds.\n' >&2; return 2; }
    exec 9>"${daemon_lock}"; flock -n 9 || exit 0
    while sleep "${rotation_seconds}"; do next_wallpaper --quiet || exit 0; done
}

case ${1:-status} in
    status|current) current_theme ;;
    session-start|apply) session_start ;;
    set) set_theme "${2:-}" ;;
    toggle|cycle) cycle_theme ;;
    next) next_wallpaper ;;
    lock-image) lock_image ;;
    mode) current_mode ;;
    mode-set) set_mode "${2:-}" ;;
    mode-toggle) toggle_mode ;;
    mode-json) mode_json ;;
    daemon) run_daemon ;;
    *) printf 'usage: %s {status|session-start|set THEME|cycle|next|lock-image|mode|mode-set MODE|mode-toggle|mode-json|daemon}\n' "$0" >&2; exit 2 ;;
esac
