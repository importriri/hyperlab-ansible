#!/usr/bin/env bash
set -uo pipefail

config_home=${XDG_CONFIG_HOME:-"${HOME}/.config"}
state_home=${XDG_STATE_HOME:-"${HOME}/.local/state"}
config=${config_home}/waybar/config.jsonc
style=${config_home}/waybar/style.css
state_dir=${state_home}/hyperlab
log=${state_dir}/waybar.log
pid_file=${XDG_RUNTIME_DIR:-/tmp}/privatestack-waybar-supervisor.pid
lock_file=${XDG_RUNTIME_DIR:-/tmp}/privatestack-waybar-supervisor.lock
child_pid=""
stopping=0

native_bar() {
    swaymsg bar mode dock bar-0 >/dev/null 2>&1 || true
}

hide_native_bar() {
    swaymsg bar mode invisible bar-0 >/dev/null 2>&1 || true
}

owns_pid_file() {
    [[ -r ${pid_file} ]] && [[ $(<"${pid_file}") == "$$" ]]
}

pid_is_live() {
    local pid=$1
    local state=""

    kill -0 "${pid}" 2>/dev/null || return 1
    if [[ -r /proc/${pid}/status ]]; then
        state=$(awk '$1 == "State:" { print $2; exit }' "/proc/${pid}/status")
        [[ ${state} != Z ]] || return 1
    fi
}

cleanup() {
    if owns_pid_file; then
        rm -f "${pid_file}"
        native_bar
    fi
}

stop_supervisor() {
    stopping=1
    if [[ -n ${child_pid} ]] && kill -0 "${child_pid}" 2>/dev/null; then
        kill "${child_pid}" 2>/dev/null || true
        wait "${child_pid}" 2>/dev/null || true
    fi
    cleanup
    exit 0
}

acquire_supervisor_lock() {
    # Keep this descriptor open for the lifetime of the supervisor.  A pid
    # file alone cannot make startup atomic: two exec_always processes can read
    # the same old pid before either writes its own.  The child closes fd 9 so
    # an orphaned Waybar cannot keep the supervisor lock after its parent dies.
    exec 9>"${lock_file}"
    flock -n 9
}

retire_legacy_supervisor() {
    # The first release with flock may be started by a pre-lock supervisor.
    # Retire that one process while the new lock is already held; later reloads
    # simply fail acquire_supervisor_lock and leave the owner untouched.
    [[ -r ${pid_file} ]] || return 0

    old_pid=$(<"${pid_file}")
    [[ ${old_pid} =~ ^[0-9]+$ ]] || return 0
    [[ ${old_pid} != "$$" ]] || return 0
    pid_is_live "${old_pid}" || return 0

    old_cmd=$({ tr '\0' ' ' <"/proc/${old_pid}/cmdline"; } 2>/dev/null || true)
    if [[ ${old_cmd} != *privatestack-waybar* ]]; then
        # Disappearance between the liveness check and /proc read is harmless.
        # An unreadable but still-live unrelated process must never be killed.
        pid_is_live "${old_pid}" && return 1
        return 0
    fi

    kill -TERM "${old_pid}" 2>/dev/null || true
    for _ in {1..40}; do
        pid_is_live "${old_pid}" || return 0
        sleep 0.05
    done

    printf 'legacy supervisor pid=%s did not stop; keeping it active\n' \
        "${old_pid}" >>"${log}"
    return 1
}

start() {
    mkdir -p "${state_dir}"

    acquire_supervisor_lock || return 0
    retire_legacy_supervisor || return 0

    printf '%s\n' "$$" >"${pid_file}"
    trap stop_supervisor INT TERM HUP
    trap cleanup EXIT

    pkill -x waybar 2>/dev/null || true
    hide_native_bar

    failures=0
    while (( stopping == 0 )); do
        started=$(date +%s)
        {
            printf '\n=== %s ===\n' "$(date --iso-8601=seconds)"
            printf 'launcher: %s\nconfig: %s\nstyle: %s\n' "$0" "${config}" "${style}"
        } >>"${log}" 2>&1

        env GDK_BACKEND=wayland waybar -l info -c "${config}" -s "${style}" \
            9>&- >>"${log}" 2>&1 &
        child_pid=$!
        wait "${child_pid}"
        rc=$?
        child_pid=""
        (( stopping != 0 )) && break

        runtime=$(( $(date +%s) - started ))
        if (( runtime >= 20 )); then
            failures=0
        else
            failures=$(( failures + 1 ))
        fi
        printf 'waybar exited rc=%d after %ds (rapid failures=%d)\n' \
            "${rc}" "${runtime}" "${failures}" >>"${log}"

        if (( failures >= 3 )); then
            native_bar
            if command -v notify-send >/dev/null 2>&1; then
                notify-send -u critical 'HyperLab bar' \
                    'Waybar is unstable; the native Swaybar fallback was restored automatically.'
            fi
            return 0
        fi
        sleep 0.5
    done
}

toggle() {
    if pgrep -x waybar >/dev/null 2>&1; then
        pkill -x -USR1 waybar
    else
        swaymsg bar mode toggle bar-0 >/dev/null 2>&1 || true
    fi
}

case ${1:-start} in
    start) start ;;
    toggle) toggle ;;
    *) printf 'usage: %s [start|toggle]\n' "$0" >&2; exit 2 ;;
esac
