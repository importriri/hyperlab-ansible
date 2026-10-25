#!/bin/sh
# HyperLab showcase: the shots of docs/showcase.md, in order.
#
#   tools/showcase/demo.sh NAME     NAME is the Machine the take creates
#
# The script never changes the host. It checks the session, prints the
# generic list of what a reviewer must not let on screen, then walks the
# shots: it opens the shell surfaces through their reviewed IPC targets,
# tells the operator what to do, and waits for the inventory to show the
# result before the next shot. Creating the Machine is done by hand in the
# shell, as the film shows it; the password is typed in the operation
# window, never here.
#
# This terminal may be on camera. The script never asks who or where the
# host is, and a failing tool is reported by a fixed reason, never by the
# tool's own output, which can carry paths, sockets and addresses.
set -eu

fail() {
    printf 'demo: %s\n' "$1" >&2
    exit 1
}

usage() {
    echo "usage: tools/showcase/demo.sh NAME (2 to 31 lowercase letters, digits and dashes, starting with a letter)" >&2
    exit 2
}

[ "$#" -eq 1 ] || usage
name="$1"
case "${name}" in
    [a-z]*[a-z0-9]) ;;
    *) usage ;;
esac
# The pattern above checks only the first and last characters.
case "${name}" in
    *[!a-z0-9-]*) usage ;;
esac
[ "${#name}" -le 31 ] || usage

shell_ipc() {
    qs -c hyperlab ipc call "$1" "$2" >/dev/null 2>&1 \
        || fail "the HyperLab shell did not open $1 $2; stop the take"
}

shot() {
    printf '\n== Shot %s: %s\n%s\n' "$1" "$2" "$3"
    printf 'Press Enter when the shot is done. '
    read -r _ || fail "no answer from the terminal; stop the take"
}

# Prints the Machine's inventory state, or "absent". An inventory that
# cannot be read, or that names the Machine twice, fails instead.
state_of() {
    inventory="$(hyperlabctl machine inventory --json 2>/dev/null)" || return 1
    printf '%s' "${inventory}" | python3 -I -c '
import json, re, sys
document = json.load(sys.stdin)
rows = document.get("machines") if isinstance(document, dict) else None
if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
    sys.exit(1)
states = [row.get("state") for row in rows if row.get("name") == sys.argv[1]]
if not states:
    print("absent")
elif len(states) == 1 and isinstance(states[0], str) and re.fullmatch(r"[a-z-]+", states[0]):
    print(states[0])
else:
    sys.exit(1)
' "$1" 2>/dev/null
}

wait_running() {
    printf 'Waiting for %s to run' "$1"
    waited=0
    while :; do
        state="$(state_of "$1")" || { printf '\n'; fail "the Machine inventory is not readable; stop the take"; }
        if [ "${state}" = "running" ]; then
            break
        fi
        if [ "${waited}" -ge 900 ]; then
            printf '\n'
            fail "$1 is not running after 15 minutes; stop the take"
        fi
        printf '.'
        sleep 5 >/dev/null 2>&1 || { printf '\n'; fail "the wait for $1 was interrupted; stop the take"; }
        waited=$((waited + 5))
    done
    printf ' running\n'
}

# The Looking Glass client runs on after the take, so only a client that
# has already ended is judged: an error status stops the take.
viewer=""
check_looking_glass() {
    [ -n "${viewer}" ] || return 0
    if kill -0 "${viewer}" 2>/dev/null; then
        return 0
    fi
    wait "${viewer}" 2>/dev/null || fail "Looking Glass failed for ${name}; stop the take"
    viewer=""
}

# Preflight: the tools exist, the shell answers and the Machine does not
# exist yet.
for tool in hyperlabctl qs python3 sleep; do
    command -v "${tool}" >/dev/null 2>&1 || fail "${tool} is not installed"
done
qs -c hyperlab ipc call workspace close >/dev/null 2>&1 \
    || fail "the HyperLab shell does not answer; start the session first"
state="$(state_of "${name}")" || fail "the Machine inventory is not readable"
[ "${state}" = "absent" ] || fail "${name} already exists; pick a new name for a clean take"

printf '%s\n' \
    'Never on screen in the published take:' \
    '  - a host name, a user name or a home path (prompts, title bars, dialogs)' \
    '  - an IP or MAC address, an SSH key fingerprint or a host key' \
    '  - a path under /run/user, a token or a file kept private' \
    '  - a window outside the storyboard, or a notification' \
    'The password is typed in the operation window, off camera.'

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
viewer=$!
shot 5 "Looking Glass and the Desks" \
    "In the guest: ALT+1, ALT+2 between Desks, ALT+D for the overview, ALT+Space for the launcher. Release the capture with Right CTRL."
check_looking_glass

shell_ipc workspace diagnostics
shot 6 "The host frame" \
    "The frame colour is the Machine's network identity; Diagnostics shows the GPU class and the trust ladder."

check_looking_glass
shell_ipc workspace close
printf '\nTake complete. Review every frame where text is on screen against the list above before publishing (docs/showcase.md).\n'
