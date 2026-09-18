#!/usr/bin/env bash
set -euo pipefail

readonly managed_marker=1
readonly runtime_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

user_id="$(id -u)"
readonly user_id

readonly hyper_target="hyperlab-hyprland-session.target"
readonly sway_target=hyperlab-sway-session.target

usage() {
    cat >&2 <<'USAGE'
usage:
  privatestack-session-lifecycle launch hyprland
  privatestack-session-lifecycle launch sway
USAGE
}

require_backend() {
    case "${1:-}" in
        hyprland|sway) ;;
        *)
            usage
            exit 2
            ;;
    esac
}

stop_portals() {
    systemctl --user stop \
        xdg-desktop-portal.service \
        xdg-desktop-portal-hyprland.service \
        xdg-desktop-portal-wlr.service \
        >/dev/null 2>&1 || true
}

stop_hyperlab_hyprland_target() {
    systemctl --user stop "${hyper_target}" \
        >/dev/null 2>&1 || true
}

stop_hyperlab_sway_target() {
    systemctl --user stop "${sway_target}" \
        >/dev/null 2>&1 || true
}

stop_graphical_session() {
    systemctl --user stop graphical-session.target \
        >/dev/null 2>&1 || true
}

clear_systemd_environment() {
    systemctl --user unset-environment \
        WAYLAND_DISPLAY \
        SWAYSOCK \
        HYPRLAND_INSTANCE_SIGNATURE \
        XDG_CURRENT_DESKTOP \
        XDG_SESSION_DESKTOP \
        XDG_SESSION_TYPE \
        HYPERLAB_SESSION_LIFECYCLE_MANAGED
}

clear_dbus_environment() {
    dbus-update-activation-environment \
        --systemd \
        WAYLAND_DISPLAY= \
        SWAYSOCK= \
        HYPRLAND_INSTANCE_SIGNATURE= \
        XDG_CURRENT_DESKTOP= \
        XDG_SESSION_DESKTOP= \
        XDG_SESSION_TYPE= \
        HYPERLAB_SESSION_LIFECYCLE_MANAGED=
}

clear_session_environment() {
    stop_hyperlab_hyprland_target
    stop_hyperlab_sway_target
    stop_portals
    stop_graphical_session
    clear_systemd_environment
    clear_dbus_environment

    unset WAYLAND_DISPLAY
    unset SWAYSOCK
    unset HYPRLAND_INSTANCE_SIGNATURE
}

publish_base_environment() {
    local desktop=$1

    export XDG_CURRENT_DESKTOP="${desktop}"
    export XDG_SESSION_DESKTOP="${desktop}"
    export XDG_SESSION_TYPE=wayland
    export HYPERLAB_SESSION_LIFECYCLE_MANAGED="${managed_marker}"

    systemctl --user set-environment \
        "XDG_CURRENT_DESKTOP=${XDG_CURRENT_DESKTOP}" \
        "XDG_SESSION_DESKTOP=${XDG_SESSION_DESKTOP}" \
        "XDG_SESSION_TYPE=${XDG_SESSION_TYPE}" \
        "HYPERLAB_SESSION_LIFECYCLE_MANAGED=${managed_marker}"

    dbus-update-activation-environment \
        --systemd \
        XDG_CURRENT_DESKTOP \
        XDG_SESSION_DESKTOP \
        XDG_SESSION_TYPE \
        HYPERLAB_SESSION_LIFECYCLE_MANAGED
}

prepare_session() {
    local backend=$1

    clear_session_environment

    case "${backend}" in
        hyprland)
            publish_base_environment Hyprland
            ;;
        sway)
            publish_base_environment sway
            ;;
    esac
}

refuse_concurrent_compositor() {
    if pgrep -u "${user_id}" -x Hyprland >/dev/null 2>&1; then
        echo "refusing managed session: Hyprland already exists" >&2
        return 1
    fi

    if pgrep -u "${user_id}" -x sway >/dev/null 2>&1; then
        echo "refusing managed session: Sway already exists" >&2
        return 1
    fi
}

publish_hyprland_runtime() {
    local instance=$1
    local socket=$2

    export WAYLAND_DISPLAY="${socket}"
    export HYPRLAND_INSTANCE_SIGNATURE="${instance}"
    unset SWAYSOCK

    systemctl --user unset-environment SWAYSOCK

    systemctl --user set-environment \
        "WAYLAND_DISPLAY=${WAYLAND_DISPLAY}" \
        "HYPRLAND_INSTANCE_SIGNATURE=${HYPRLAND_INSTANCE_SIGNATURE}" \
        "XDG_CURRENT_DESKTOP=Hyprland" \
        "XDG_SESSION_DESKTOP=Hyprland" \
        "XDG_SESSION_TYPE=wayland" \
        "HYPERLAB_SESSION_LIFECYCLE_MANAGED=${managed_marker}"

    dbus-update-activation-environment \
        --systemd \
        SWAYSOCK= \
        WAYLAND_DISPLAY \
        HYPRLAND_INSTANCE_SIGNATURE \
        XDG_CURRENT_DESKTOP \
        XDG_SESSION_DESKTOP \
        XDG_SESSION_TYPE \
        HYPERLAB_SESSION_LIFECYCLE_MANAGED

    # HyperLab owns the compositor-session target on Arch. The custom
    # target requires graphical-session.target and starts the reviewed
    # Hyprland-only helper set after the compositor socket is proven.
    systemctl --user start "${hyper_target}"
    systemctl --user start xdg-desktop-portal.service
}

wait_for_hyprland_runtime() {
    local retries=0
    local instances
    local count
    local instance
    local socket

    while [ "${retries}" -lt 150 ]; do
        retries=$((retries + 1))

        instances="$(hyprctl instances -j 2>/dev/null || true)"

        count="$(
            printf '%s\n' "${instances}" |
                jq -r '
                    if type == "array"
                    then length
                    else 0
                    end
                ' 2>/dev/null || printf '0'
        )"

        if [ "${count}" = "1" ]; then
            instance="$(
                printf '%s\n' "${instances}" |
                    jq -er '.[0].instance // empty' 2>/dev/null || true
            )"

            socket="$(
                printf '%s\n' "${instances}" |
                    jq -er '.[0].wl_socket // empty' 2>/dev/null || true
            )"

            if [ -n "${instance}" ] && [ -n "${socket}" ]; then
                publish_hyprland_runtime "${instance}" "${socket}"

                printf '%s\n' \
                    "HYPERLAB_HYPRLAND_RUNTIME_READY=1" \
                    "HYPRLAND_INSTANCE_SIGNATURE=${instance}" \
                    "WAYLAND_DISPLAY=${socket}"

                return 0
            fi
        elif [ "${count}" -gt 1 ]; then
            echo \
                "refusing ambiguous Hyprland runtime: ${count} instances" \
                >&2
            return 8
        fi

        sleep 0.1
    done

    echo "managed Hyprland runtime did not become ready" >&2

    pkill -TERM -u "${user_id}" -x Hyprland \
        >/dev/null 2>&1 || true

    return 9
}

publish_sway_runtime() {
    local socket=$1
    local wayland_display=$2

    export SWAYSOCK="${socket}"
    export WAYLAND_DISPLAY="${wayland_display}"
    unset HYPRLAND_INSTANCE_SIGNATURE

    systemctl --user unset-environment \
        HYPRLAND_INSTANCE_SIGNATURE

    systemctl --user set-environment \
        "SWAYSOCK=${SWAYSOCK}" \
        "WAYLAND_DISPLAY=${WAYLAND_DISPLAY}" \
        "XDG_CURRENT_DESKTOP=sway" \
        "XDG_SESSION_DESKTOP=sway" \
        "XDG_SESSION_TYPE=wayland" \
        "HYPERLAB_SESSION_LIFECYCLE_MANAGED=${managed_marker}"

    dbus-update-activation-environment \
        --systemd \
        HYPRLAND_INSTANCE_SIGNATURE= \
        SWAYSOCK \
        WAYLAND_DISPLAY \
        XDG_CURRENT_DESKTOP \
        XDG_SESSION_DESKTOP \
        XDG_SESSION_TYPE \
        HYPERLAB_SESSION_LIFECYCLE_MANAGED

    systemctl --user start "${sway_target}"
    systemctl --user start xdg-desktop-portal.service
}

wait_for_sway_runtime() {
    local sway_pid=$1
    local retries=0
    local socket="${runtime_dir}/sway-ipc.${user_id}.${sway_pid}.sock"
    local -a wayland_sockets
    local wayland_display

    while [ "${retries}" -lt 150 ]; do
        retries=$((retries + 1))

        kill -0 "${sway_pid}" 2>/dev/null || return 10

        mapfile -t wayland_sockets < <(
            find "${runtime_dir}" \
                -maxdepth 1 \
                -type s \
                -name 'wayland-[0-9]*' \
                -print 2>/dev/null
        )

        if [ -S "${socket}" ] &&
           [ "${#wayland_sockets[@]}" -eq 1 ]; then

            wayland_display="${wayland_sockets[0]##*/}"

            if SWAYSOCK="${socket}" \
                swaymsg -r -t get_version \
                >/dev/null 2>&1; then

                publish_sway_runtime \
                    "${socket}" \
                    "${wayland_display}"

                printf '%s\n' \
                    "HYPERLAB_SWAY_RUNTIME_READY=1" \
                    "SWAYSOCK=${socket}" \
                    "WAYLAND_DISPLAY=${wayland_display}"

                return 0
            fi
        fi

        sleep 0.1
    done

    echo "managed Sway runtime did not become ready" >&2
    kill -TERM "${sway_pid}" >/dev/null 2>&1 || true
    return 12
}

launch_hyprland() {
    local watcher_pid
    local launch_rc
    local watcher_rc

    prepare_session hyprland
    systemctl --user daemon-reload

    wait_for_hyprland_runtime &
    watcher_pid=$!

    set +e
    # Arch's Hyprland package does not ship a persistent
    # hyprland-session.target. Suppress Hyprland's optional target request;
    # the proven runtime watcher activates HyperLab's own target instead.
    HYPRLAND_NO_SD_TARGET=1 /usr/bin/start-hyprland
    launch_rc=$?
    wait "${watcher_pid}"
    watcher_rc=$?
    set -e

    clear_session_environment

    if [ "${watcher_rc}" -ne 0 ]; then
        return "${watcher_rc}"
    fi

    return "${launch_rc}"
}

launch_sway() {
    local sway_pid
    local launch_rc
    local watcher_rc

    prepare_session sway
    systemctl --user daemon-reload

    set +e
    /usr/bin/sway &
    sway_pid=$!

    wait_for_sway_runtime "${sway_pid}"
    watcher_rc=$?

    if [ "${watcher_rc}" -eq 0 ]; then
        wait "${sway_pid}"
        launch_rc=$?
    else
        kill -TERM "${sway_pid}" >/dev/null 2>&1 || true
        wait "${sway_pid}" >/dev/null 2>&1 || true
        launch_rc="${watcher_rc}"
    fi
    set -e

    clear_session_environment
    return "${launch_rc}"
}

main() {
    local operation=${1:-}
    local backend=${2:-}

    [ "${operation}" = "launch" ] || {
        usage
        return 2
    }

    require_backend "${backend}"
    refuse_concurrent_compositor

    case "${backend}" in
        hyprland)
            launch_hyprland
            ;;
        sway)
            launch_sway
            ;;
    esac
}

main "$@"
