#!/usr/bin/env bash
set -euo pipefail

# HyperLab host compositor adapter.
#
# Owns compositor IPC translation only.
# Theme order, keyboard policy, trust, wallpaper selection and application
# opacity policy deliberately remain in their high-level controllers.

readonly backend_timeout=${HYPERLAB_COMPOSITOR_TIMEOUT_SECONDS:-5}

usage() {
    cat >&2 <<'EOF'
usage:
  privatestack-compositor-adapter backend
  privatestack-compositor-adapter keyboard-set LAYOUT INDEX ORDER_CSV
  privatestack-compositor-adapter wallpaper-set ABSOLUTE_IMAGE
  privatestack-compositor-adapter reload
  privatestack-compositor-adapter fullscreen-toggle
  privatestack-compositor-adapter focused-window
  privatestack-compositor-adapter opacity-set VALUE
  privatestack-compositor-adapter dpms enable|disable
  privatestack-compositor-adapter native-bar show|hide|toggle
  privatestack-compositor-adapter session-exit
EOF
}

detect_backend() {
    case ${HYPERLAB_COMPOSITOR_BACKEND:-} in
        sway|hyprland)
            printf '%s\n' \
                "${HYPERLAB_COMPOSITOR_BACKEND}"
            return 0
            ;;
        "")
            ;;
        *)
            printf \
                'unsupported HYPERLAB_COMPOSITOR_BACKEND=%s\n' \
                "${HYPERLAB_COMPOSITOR_BACKEND}" \
                >&2
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

    printf \
        'cannot determine active compositor backend\n' \
        >&2
    return 3
}

run_swaymsg() {
    command timeout \
        --signal=TERM \
        --kill-after=1s \
        "${backend_timeout}s" \
        swaymsg \
        "$@"
}

run_hyprctl() {
    command timeout \
        --signal=TERM \
        --kill-after=1s \
        "${backend_timeout}s" \
        hyprctl \
        "$@"
}

run_hyprshutdown() {
    command timeout \
        --signal=TERM \
        --kill-after=1s \
        "${backend_timeout}s" \
        hyprshutdown
}

focused_sway() {
    run_swaymsg -r -t get_tree |
        python3 -c '
import json
import sys


def find(node):
    if node.get("focused"):
        return node

    for key in ("nodes", "floating_nodes"):
        for child in node.get(key, []):
            result = find(child)

            if result is not None:
                return result

    return None


node = find(json.load(sys.stdin)) or {}
identity = node.get("id", "")
app = (
    node.get("app_id")
    or (node.get("window_properties") or {}).get("class")
    or ""
)

if identity != "":
    print(f"{identity}\t{app}")
'
}

focused_hyprland() {
    run_hyprctl activewindow -j |
        python3 -c '
import json
import sys


node = json.load(sys.stdin)
identity = node.get("address") or ""
app = (
    node.get("class")
    or node.get("initialClass")
    or ""
)

if identity:
    print(f"{identity}\t{app}")
'
}

backend="$(detect_backend)" ||
    exit $?

operation=${1:-}

case ${operation} in
    backend)
        printf '%s\n' "${backend}"
        ;;

    keyboard-set)
        layout=${2:-}
        index=${3:-}
        order_csv=${4:-}

        [[ -n ${layout} ]] || {
            usage
            exit 2
        }

        [[ ${index} =~ ^[0-9]+$ ]] || {
            printf \
                'keyboard index must be a non-negative integer\n' \
                >&2
            exit 2
        }

        [[ -n ${order_csv} ]] || {
            printf \
                'keyboard layout order must be explicit\n' \
                >&2
            exit 2
        }

        IFS=',' read -r -a declared_layouts \
            <<<"${order_csv}"

        if (( index >= ${#declared_layouts[@]} )) ||
           [[ ${declared_layouts[index]} != "${layout}" ]]
        then
            printf \
                'keyboard layout/index mismatch: layout=%s index=%s order=%s\n' \
                "${layout}" \
                "${index}" \
                "${order_csv}" \
                >&2
            exit 2
        fi

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
                # Hyprland switches by configured index. The caller must provide
                # the explicit ordered layout contract and we fail closed above
                # if LAYOUT and INDEX disagree with it.
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
            printf \
                'wallpaper path must be absolute\n' \
                >&2
            exit 2
        }

        [[ -r ${image} ]] || {
            printf \
                'wallpaper is not readable: %s\n' \
                "${image}" \
                >&2
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
                run_swaymsg \
                    -q \
                    "fullscreen toggle"
                ;;
            hyprland)
                run_hyprctl \
                    dispatch \
                    'hl.dsp.window.fullscreen({ action = "toggle", mode = "fullscreen" })'
                ;;
        esac
        ;;

    focused-window)
        case ${backend} in
            sway)
                focused_sway
                ;;
            hyprland)
                focused_hyprland
                ;;
        esac
        ;;

    opacity-set)
        value=${2:-}

        [[ ${value} =~ ^(0([.][0-9]+)?|1([.]0+)?)$ ]] || {
            printf \
                'opacity must be a value from 0 through 1\n' \
                >&2
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
                sway_mode=
                ;;
            *)
                usage
                exit 2
                ;;
        esac

        # Hyprland has no native Sway bar equivalent. Waybar/Quickshell are
        # layer surfaces, so this fallback primitive is intentionally a no-op.
        if [[ ${backend} == sway ]]; then
            if [[ ${action} == toggle ]]; then
                current_mode="$(
                    run_swaymsg \
                        -r \
                        -t \
                        get_bar_config \
                        bar-0 |
                        python3 -c '
import json
import sys

print(
    json.load(sys.stdin).get(
        "mode",
        "",
    )
)
'
                )"

                case ${current_mode} in
                    dock)
                        sway_mode=invisible
                        ;;
                    invisible)
                        sway_mode=dock
                        ;;
                    *)
                        printf \
                            'cannot toggle Sway bar from unsupported mode: %s\n' \
                            "${current_mode}" \
                            >&2
                        exit 2
                        ;;
                esac
            fi

            run_swaymsg \
                bar \
                mode \
                "${sway_mode}" \
                bar-0
        fi
        ;;

    session-exit)
        case ${backend} in
            sway)
                run_swaymsg exit
                ;;
            hyprland)
                if [[ ${HYPERLAB_SESSION_LIFECYCLE_MANAGED:-0} == 1 ]]; then
                    systemctl --user stop \
                        hyperlab-hyprland-session.target
                fi

                run_hyprshutdown
                ;;
        esac
        ;;

    *)
        usage
        exit 2
        ;;
esac
