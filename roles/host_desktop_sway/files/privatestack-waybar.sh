#!/usr/bin/env bash
set -uo pipefail

config_home=${XDG_CONFIG_HOME:-"${HOME}/.config"}
state_home=${XDG_STATE_HOME:-"${HOME}/.local/state"}
config=${config_home}/waybar/config.jsonc
style=${config_home}/waybar/style.css
state_dir=${state_home}/hyperlab
log=${state_dir}/waybar.log
pid_file=${XDG_RUNTIME_DIR:-/tmp}/privatestack-waybar-supervisor.pid
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

start() {
    mkdir -p "${state_dir}"

    if [[ -r ${pid_file} ]]; then
        old_pid=$(<"${pid_file}")
        if [[ ${old_pid} =~ ^[0-9]+$ ]] && kill -0 "${old_pid}" 2>/dev/null; then
            old_cmd=$(tr '\0' ' ' <"/proc/${old_pid}/cmdline" 2>/dev/null || true)
            if [[ ${old_cmd} == *privatestack-waybar* ]]; then
                kill "${old_pid}" 2>/dev/null || true
                for _ in {1..20}; do
                    kill -0 "${old_pid}" 2>/dev/null || break
                    sleep 0.05
                done
            fi
        fi
    fi

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

        env GDK_BACKEND=wayland waybar -l info -c "${config}" -s "${style}" >>"${log}" 2>&1 &
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
