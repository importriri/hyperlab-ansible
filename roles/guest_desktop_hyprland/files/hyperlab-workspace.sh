#!/bin/sh
# hyperlab-workspace - start the guest Workspace Shell, or reach it.
#
#   hyperlab-workspace session       run the shell for this Hyprland session
#   hyperlab-workspace launcher      ALT+Space
#   hyperlab-workspace overview      ALT+D
#   hyperlab-workspace new-project   ALT+N
#   hyperlab-workspace cheatsheet    ALT+H
#
# The key bindings always call this script, never the shell directly, so
# every key keeps working when the shell is not running: the launcher falls
# back to rofi, the Desk overview and new-project prompts to rofi menus over
# hyperlab-desk. A session whose shell keeps failing falls back to Waybar,
# so the desktop is never left without a bar.
set -u

config=hyperlab-workspace
keys_file=/etc/xdg/quickshell/hyperlab-workspace/keys.json
state_dir="${XDG_STATE_HOME:-${HOME}/.local/state}/hyperlab-workspace"

shell_running() {
    pgrep -u "$(id -u)" -f "(^|/)qs -c ${config}\$" >/dev/null 2>&1
}

# Reach the running shell. A shell that is up but slow to answer is asked
# again, never replaced by rofi: the plain tools are only for a session
# whose shell is really not running.
shell_call() {
    command -v qs >/dev/null 2>&1 || return 1
    attempt=0
    while [ "${attempt}" -lt 3 ]; do
        qs -c "${config}" ipc call workspace "$1" >/dev/null 2>&1 && return 0
        shell_running || return 1
        attempt=$(( attempt + 1 ))
        sleep 0.2
    done
    mkdir -p "${state_dir}"
    echo "hyperlab-workspace: the running shell did not answer $1" >>"${state_dir}/shell.log"
    return 0
}

pick_desk() {
    hyperlab-desk model 2>/dev/null \
        | python3 -c 'import json, sys
for desk in json.load(sys.stdin)["desks"]:
    print(desk["index"], desk["name"], sep="  ")' \
        | rofi -dmenu -i -p "Desk" \
        | cut -d' ' -f1
}

current_desk() {
    hyperlab-desk status 2>/dev/null \
        | python3 -c 'import json, sys; print(json.load(sys.stdin).get("desk") or 1)'
}

session() {
    mkdir -p "${state_dir}"
    log="${state_dir}/shell.log"
    failures=0
    while [ "${failures}" -lt 3 ]; do
        started="$(date +%s)"
        # The shell is deployed as many files; a live watcher would reload it
        # part-way through a deployment, so reloads are a fresh session.
        QS_DISABLE_FILE_WATCHER=1 qs -c "${config}" >>"${log}" 2>&1
        status=$?
        lived=$(( $(date +%s) - started ))
        # A long run that ends is a crash to restart, not a broken install.
        if [ "${lived}" -ge 30 ]; then
            failures=0
        else
            failures=$(( failures + 1 ))
        fi
        echo "hyperlab-workspace: shell exited ${status} after ${lived}s" >>"${log}"
        sleep 1
    done
    echo "hyperlab-workspace: shell failed three times, starting Waybar" >>"${log}"
    exec waybar
}

case "${1:-}" in
    session)
        session
        ;;
    launcher)
        shell_call launcher || exec rofi -show drun
        ;;
    overview)
        if ! shell_call overview; then
            desk="$(pick_desk)"
            [ -n "${desk}" ] && exec hyperlab-desk desk "${desk}"
        fi
        ;;
    new-project)
        if ! shell_call newProject; then
            name="$(rofi -dmenu -p "New project" </dev/null)"
            [ -n "${name}" ] && exec hyperlab-desk project-new "$(current_desk)" "${name}"
        fi
        ;;
    cheatsheet)
        if ! shell_call cheatsheet; then
            jq -r '.groups[] | "── \(.title)", (.keys[] | "\(.keys)\t\(.does)")' \
                "${keys_file}" | rofi -dmenu -i -p "Keys" >/dev/null
        fi
        ;;
    *)
        echo "usage: hyperlab-workspace session|launcher|overview|new-project|cheatsheet" >&2
        exit 2
        ;;
esac
