#!/usr/bin/env bash
set -euo pipefail

readonly compositor_adapter=${HYPERLAB_COMPOSITOR_ADAPTER:-/usr/local/bin/privatestack-compositor-adapter}

backend="$("${compositor_adapter}" backend)"

# Tell the HyperLab shell the session is locking, so nothing armed (a
# destructive confirmation, the launcher, the system panel) survives behind
# the locker. Fixed receiver, no arguments, backgrounded and time-bounded:
# a missing or hung shell can never delay or prevent the lock.
if command -v qs >/dev/null 2>&1; then
    (timeout 2 qs -c hyperlab ipc call session locking || true) \
        </dev/null >/dev/null 2>&1 &
fi

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
