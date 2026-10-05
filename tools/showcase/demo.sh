#!/bin/sh
# HyperLab showcase: the shots of docs/showcase.md, in order.
#
#   tools/showcase/demo.sh NAME     NAME is the Machine the take creates
#
# The script never changes the host. It checks the session, prints what a
# reviewer must not let on screen, then walks the shots: it opens the shell
# surfaces through their reviewed IPC targets, tells the operator what to do,
# and waits for the inventory to show the result before the next shot.
# Creating the Machine is done by hand in the shell, as the film shows it;
# the password is typed in the operation window, never here.
set -eu

name="${1:-}"
case "${name}" in
    [a-z][a-z0-9-]*[a-z0-9]) ;;
    *)
        echo "usage: tools/showcase/demo.sh NAME (lowercase letters, digits and dashes)" >&2
        exit 2
        ;;
esac
if [ "${#name}" -gt 31 ]; then
    echo "demo: the Machine name must be at most 31 characters" >&2
    exit 2
fi

shell_ipc() {
    qs -c hyperlab ipc call "$1" "$2" >/dev/null
}

shot() {
    printf '\n== Shot %s: %s\n%s\n' "$1" "$2" "$3"
    printf 'Press Enter when the shot is done. '
    read -r _
}

state_of() {
    hyperlabctl machine inventory --json 2>/dev/null | python3 -c '
import json, sys
name = sys.argv[1]
for row in json.load(sys.stdin).get("machines", []):
    if row.get("name") == name:
        print(row.get("state", "unknown"))
        break
' "$1"
}

wait_running() {
    printf 'Waiting for %s to run' "$1"
    waited=0
    while [ "$(state_of "$1")" != "running" ]; do
        if [ "${waited}" -ge 900 ]; then
            printf '\ndemo: %s is not running after 15 minutes; stop the take\n' "$1" >&2
            exit 1
        fi
        printf '.'
        sleep 5
        waited=$((waited + 5))
    done
    printf ' running\n'
}

# Preflight: the shell answers and the Machine does not exist yet.
command -v hyperlabctl >/dev/null || { echo "demo: hyperlabctl is not installed" >&2; exit 1; }
command -v qs >/dev/null || { echo "demo: Quickshell is not installed" >&2; exit 1; }
shell_ipc workspace close || { echo "demo: the HyperLab shell does not answer" >&2; exit 1; }
if [ -n "$(state_of "${name}")" ]; then
    echo "demo: ${name} already exists; pick a new name for a clean take" >&2
    exit 1
fi

printf 'Never on screen in the published take:\n'
printf '  host name   %s\n' "$(command cat /proc/sys/kernel/hostname)"
printf '  user name   %s\n' "$(id -un)"
printf '  home path   %s\n' "${HOME}"
ip -4 -o addr show scope global 2>/dev/null | while read -r _ device _ address _; do
    printf '  address     %s (%s)\n' "${address%/*}" "${device}"
done

shot 1 "The quiet desktop" \
    "Wallpaper and the rail only. Hold three seconds."

shell_ipc workspace machines
shot 2 "Create from workstation-dev" \
    "New Machine, Development Workstation, name ${name}, network dev, Balanced, Create. Type the password in the operation window off camera."

wait_running "${name}"
shot 3 "First boot with the rice" \
    "The Machine's card turns Running; open it and show its Template, image digest and network."

shot 4 "The GPU" \
    "The GPU badge shows the Machine holding the GPU. The per-run GPU lease is not built yet (ADR 0019): skip its shot."

hyperlabctl open looking-glass "${name}" >/dev/null 2>&1 &
shot 5 "Looking Glass and the Desks" \
    "In the guest: ALT+1, ALT+2 between Desks, ALT+D for the overview, ALT+Space for the launcher. Release the capture with Right CTRL."

shell_ipc workspace diagnostics
shot 6 "The host frame" \
    "The frame colour is the Machine's network identity; Diagnostics shows the GPU class and the trust ladder."

shell_ipc workspace close
printf '\nTake complete. Review it against the list above before publishing (docs/showcase.md).\n'
