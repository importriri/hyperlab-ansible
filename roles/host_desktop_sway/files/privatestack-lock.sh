#!/usr/bin/env bash
set -euo pipefail

readonly compositor_adapter=${HYPERLAB_COMPOSITOR_ADAPTER:-/usr/local/bin/privatestack-compositor-adapter}

backend="$("${compositor_adapter}" backend)"

case ${backend} in
    sway)
        image=$(/usr/local/bin/privatestack-theme lock-image)
        exec swaylock \
            --config "${XDG_CONFIG_HOME:-${HOME}/.config}/swaylock/config" \
            --image "${image}" \
            --scaling fill \
            "$@"
        ;;

    hyprland)
        if command -v pidof >/dev/null 2>&1 &&
           pidof hyprlock >/dev/null 2>&1
        then
            exit 0
        fi
        exec hyprlock "$@"
        ;;

    *)
        printf 'unsupported compositor backend: %s\n' "${backend}" >&2
        exit 2
        ;;
esac
