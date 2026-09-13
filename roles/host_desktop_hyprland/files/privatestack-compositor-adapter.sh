#!/usr/bin/env bash
set -euo pipefail

# HyperLab compositor adapter.
#
# This file owns only compositor IPC translation. It deliberately does not own
# theme names, keyboard-layout order, wallpaper selection, trust classes or any
# other HyperLab policy.

usage() {
    cat >&2 <<'EOF'
usage:
  privatestack-compositor-adapter backend
  privatestack-compositor-adapter keyboard-set LAYOUT INDEX
  privatestack-compositor-adapter wallpaper-set ABSOLUTE_IMAGE
  privatestack-compositor-adapter reload
  privatestack-compositor-adapter fullscreen-toggle
  privatestack-compositor-adapter opacity-set VALUE
  privatestack-compositor-adapter dpms enable|disable
  privatestack-compositor-adapter native-bar show|hide|toggle
EOF
}

detect_backend() {
    case ${HYPERLAB_COMPOSITOR_BACKEND:-} in
        sway|hyprland)
            printf '%s\n' "${HYPERLAB_COMPOSITOR_BACKEND}"
            return 0
            ;;
        "")
            ;;
        *)
            printf 'unsupported HYPERLAB_COMPOSITOR_BACKEND=%s\n' \
                "${HYPERLAB_COMPOSITOR_BACKEND}" >&2
            return 2
            ;;
    esac

    if [[ -n ${HYPRLAND_INSTANCE_SIGNATURE:-} ]]; then
        printf 'hyprland\n'
        return 0
    fi

    if [[ -n ${SWAYSOCK:-} ]]; then
        printf 'sway\n'
        return 0
    fi

    printf 'cannot determine active compositor backend\n' >&2
    return 3
}

run_swaymsg() {
    command swaymsg "$@"
}

run_hyprctl() {
    command hyprctl "$@"
}

backend="$(detect_backend)" || exit $?
operation=${1:-}

case ${operation} in
    backend)
        printf '%s\n' "${backend}"
        ;;

    keyboard-set)
        layout=${2:-}
        index=${3:-}

        [[ -n ${layout} ]] || {
            usage
            exit 2
        }

        [[ ${index} =~ ^[0-9]+$ ]] || {
            printf 'keyboard index must be a non-negative integer\n' >&2
            exit 2
        }

        case ${backend} in
            sway)
                run_swaymsg \
                    -q \
                    input \
                    type:keyboard \
                    xkb_layout \
                    "${layout}"
                ;;
            hyprland)
                run_hyprctl \
                    switchxkblayout \
                    all \
                    "${index}"
                ;;
        esac
        ;;

    wallpaper-set)
        image=${2:-}

        [[ ${image} == /* ]] || {
            printf 'wallpaper path must be absolute\n' >&2
            exit 2
        }

        [[ -r ${image} ]] || {
            printf 'wallpaper is not readable: %s\n' "${image}" >&2
            exit 2
        }

        case ${backend} in
            sway)
                run_swaymsg \
                    -q \
                    output \
                    '*' \
                    bg \
                    "${image}" \
                    fill
                ;;
            hyprland)
                run_hyprctl \
                    hyprpaper \
                    wallpaper \
                    ", ${image}, cover"
                ;;
        esac
        ;;

    reload)
        case ${backend} in
            sway)
                run_swaymsg -q reload
                ;;
            hyprland)
                run_hyprctl reload
                ;;
        esac
        ;;

    fullscreen-toggle)
        case ${backend} in
            sway)
                run_swaymsg -q "fullscreen toggle"
                ;;
            hyprland)
                run_hyprctl \
                    dispatch \
                    'hl.dsp.window.fullscreen({ action = "toggle", mode = "fullscreen" })'
                ;;
        esac
        ;;

    opacity-set)
        value=${2:-}

        [[ ${value} =~ ^(0([.][0-9]+)?|1([.]0+)?)$ ]] || {
            printf 'opacity must be a value from 0 through 1\n' >&2
            exit 2
        }

        case ${backend} in
            sway)
                run_swaymsg \
                    -q \
                    "opacity set ${value}"
                ;;
            hyprland)
                run_hyprctl \
                    dispatch \
                    "hl.dsp.window.set_prop({ prop = \"opacity\", value = \"${value}\" })"
                ;;
        esac
        ;;

    dpms)
        action=${2:-}

        case ${action} in
            enable)
                sway_action=on
                ;;
            disable)
                sway_action=off
                ;;
            *)
                usage
                exit 2
                ;;
        esac

        case ${backend} in
            sway)
                run_swaymsg \
                    -q \
                    output \
                    '*' \
                    dpms \
                    "${sway_action}"
                ;;
            hyprland)
                run_hyprctl \
                    dispatch \
                    "hl.dsp.dpms({ action = \"${action}\" })"
                ;;
        esac
        ;;

    native-bar)
        action=${2:-}

        case ${action} in
            show)
                sway_mode=dock
                ;;
            hide)
                sway_mode=invisible
                ;;
            toggle)
                sway_mode=toggle
                ;;
            *)
                usage
                exit 2
                ;;
        esac

        # Hyprland has no native Swaybar recovery surface. The command is an
        # intentional no-op there; Waybar/Quickshell own layer-shell surfaces.
        if [[ ${backend} == sway ]]; then
            run_swaymsg \
                bar \
                mode \
                "${sway_mode}" \
                bar-0
        fi
        ;;

    *)
        usage
        exit 2
        ;;
esac
