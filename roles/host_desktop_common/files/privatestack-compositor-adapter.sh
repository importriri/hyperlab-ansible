#!/usr/bin/env bash
set -euo pipefail

# HyperLab host compositor adapter.
#
# Owns compositor IPC translation only.
# Theme order, keyboard policy, trust, wallpaper selection and application
# opacity policy deliberately remain in their high-level controllers.

readonly backend_timeout=${HYPERLAB_COMPOSITOR_TIMEOUT_SECONDS:-5}

# Event watchers re-publish their snapshot after this many quiet seconds, so
# a healthy stream with no events is still observably alive. The shell treats
# about three missed heartbeats as stale; inactivity is not failure. Tests may
# shorten it; anything outside 1-60 falls back to the reviewed 30.
watch_heartbeat_seconds=${HYPERLAB_WATCH_HEARTBEAT_SECONDS:-30}
if ! [[ ${watch_heartbeat_seconds} =~ ^[1-9][0-9]?$ ]] ||
   (( watch_heartbeat_seconds > 60 ))
then
    watch_heartbeat_seconds=30
fi
readonly watch_heartbeat_seconds

# Reads one event line into event_line. Returns 0 for an event, 1 for a
# quiet heartbeat interval, and 2 when the stream has ended.
event_line=""

read_event() {
    local status

    if IFS= read -r -t "${watch_heartbeat_seconds}" event_line; then
        return 0
    else
        status=$?
    fi

    if (( status > 128 )); then
        return 1
    fi

    return 2
}

usage() {
    cat >&2 <<'EOF'
usage:
  privatestack-compositor-adapter backend
  privatestack-compositor-adapter workspaces-json
  privatestack-compositor-adapter workspace-watch
  privatestack-compositor-adapter workspace-select SLOT
  privatestack-compositor-adapter keyboard-set LAYOUT INDEX ORDER_CSV
  privatestack-compositor-adapter wallpaper-set ABSOLUTE_IMAGE
  privatestack-compositor-adapter reload
  privatestack-compositor-adapter fullscreen-toggle
  privatestack-compositor-adapter shell-window-focus
  privatestack-compositor-adapter focused-window
  privatestack-compositor-adapter focused-window-json
  privatestack-compositor-adapter focused-window-watch
  privatestack-compositor-adapter opacity-set VALUE
  privatestack-compositor-adapter window-identities-json
  privatestack-compositor-adapter focus-accent-set WINDOW_ID #RRGGBB STABLE_ID
  privatestack-compositor-adapter focus-accent-clear WINDOW_ID #RRGGBBAA STABLE_ID
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


focused_sway_json() {
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


node = find(json.load(sys.stdin))

if node is None:
    payload = {
        "pid": None,
        "app_id": "",
        "window_id": "",
        "title": "",
    }
else:
    raw_pid = node.get("pid")
    pid = (
        raw_pid
        if isinstance(raw_pid, int)
        and not isinstance(raw_pid, bool)
        and raw_pid > 0
        else None
    )

    payload = {
        "pid": pid,
        "app_id": (
            node.get("app_id")
            or (node.get("window_properties") or {}).get("class")
            or ""
        ),
        "window_id": str(node.get("id") or ""),
        "title": node.get("name") or "",
    }

print(
    json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    )
)
'
}

focused_hyprland_json() {
    run_hyprctl activewindow -j |
        python3 -c '
import json
import sys


node = json.load(sys.stdin)

raw_pid = node.get("pid")
pid = (
    raw_pid
    if isinstance(raw_pid, int)
    and not isinstance(raw_pid, bool)
    and raw_pid > 0
    else None
)

payload = {
    "pid": pid,
    "app_id": (
        node.get("class")
        or node.get("initialClass")
        or ""
    ),
    "window_id": str(
        node.get("address")
        or ""
    ),
    "title": node.get("title") or "",
}

print(
    json.dumps(
        payload,
        separators=(",", ":"),
        sort_keys=True,
    )
)
'
}

focused_window_json() {
    case ${backend} in
        sway)
            focused_sway_json
            ;;
        hyprland)
            focused_hyprland_json
            ;;
    esac
}

focused_watch_sway() {
    local status

    focused_sway_json

    while true; do
        status=0
        read_event || status=$?
        (( status == 2 )) && break
        focused_sway_json
    done < <(
        command swaymsg \
            -m \
            -t subscribe \
            '["window","workspace"]'
    )
}

focused_watch_hyprland() {
    local runtime_dir socket_path status

    focused_hyprland_json

    runtime_dir=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
    socket_path="${runtime_dir}/hypr/${HYPRLAND_INSTANCE_SIGNATURE}/.socket2.sock"

    [[ -S ${socket_path} ]] || {
        printf \
            'Hyprland event socket is unavailable: %s\n' \
            "${socket_path}" \
            >&2
        return 4
    }

    while true; do
        status=0
        read_event || status=$?
        (( status == 2 )) && break

        if (( status == 1 )); then
            focused_hyprland_json
            continue
        fi

        case ${event_line} in
            activewindow\>\>*|\
            activewindowv2\>\>*|\
            closewindow\>\>*|\
            openwindow\>\>*|\
            workspace\>\>*|\
            workspacev2\>\>*)
                focused_hyprland_json
                ;;
        esac
    done < <(
        python3 - "${socket_path}" <<'PY_INNER'
import socket
import sys

path = sys.argv[1]

connection = socket.socket(
    socket.AF_UNIX,
    socket.SOCK_STREAM,
)
connection.connect(path)

buffer = ""

while True:
    chunk = connection.recv(4096)

    if not chunk:
        break

    buffer += chunk.decode(
        "utf-8",
        errors="replace",
    )

    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        print(line, flush=True)
PY_INNER
    )
}

focused_window_watch() {
    case ${backend} in
        sway)
            focused_watch_sway
            ;;
        hyprland)
            focused_watch_hyprland
            ;;
    esac
}

workspace_snapshot_sway() {
    local payload

    payload="$(run_swaymsg -r -t get_workspaces)"

    python3 - "${payload}" <<'PY_INNER'
import json
import re
import sys

items = json.loads(sys.argv[1])

active = 0
output = ""
occupied = []
urgent = []

for item in items:
    if item.get("focused"):
        output = item.get("output") or ""

    number = item.get("num")

    if (
        not isinstance(number, int)
        or isinstance(number, bool)
        or number < 1
        or number > 9
    ):
        continue

    occupied.append(number)

    if item.get("focused"):
        active = number

    if item.get("urgent"):
        urgent.append(number)

# The focused output is a plain connector name; anything else is withheld
# rather than passed on.
if not isinstance(output, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", output):
    output = ""

print(
    json.dumps(
        {
            "active": active,
            "output": output,
            "occupied": sorted(set(occupied)),
            "urgent": sorted(set(urgent)),
        },
        separators=(",", ":"),
    )
)
PY_INNER
}

workspace_snapshot_hyprland() {
    local workspaces active clients

    workspaces="$(run_hyprctl workspaces -j)"
    active="$(run_hyprctl activeworkspace -j)"
    clients="$(run_hyprctl clients -j)"

    python3 - \
        "${workspaces}" \
        "${active}" \
        "${clients}" <<'PY_INNER'
import json
import re
import sys

workspaces = json.loads(sys.argv[1])
active_workspace = json.loads(sys.argv[2])
clients = json.loads(sys.argv[3])

active = active_workspace.get("id", 0)

# The focused output is a plain connector name; anything else is withheld
# rather than passed on.
output = active_workspace.get("monitor") or ""

if not isinstance(output, str) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", output):
    output = ""

if (
    not isinstance(active, int)
    or isinstance(active, bool)
    or active < 1
    or active > 9
):
    active = 0

occupied = set()

for item in workspaces:
    number = item.get("id")

    if (
        isinstance(number, int)
        and not isinstance(number, bool)
        and 1 <= number <= 9
    ):
        occupied.add(number)

urgent = set()

for client in clients:
    if not client.get("urgent"):
        continue

    workspace = client.get("workspace") or {}
    number = workspace.get("id")

    if (
        isinstance(number, int)
        and not isinstance(number, bool)
        and 1 <= number <= 9
    ):
        urgent.add(number)

print(
    json.dumps(
        {
            "active": active,
            "output": output,
            "occupied": sorted(occupied),
            "urgent": sorted(urgent),
        },
        separators=(",", ":"),
    )
)
PY_INNER
}

workspace_snapshot() {
    case ${backend} in
        sway)
            workspace_snapshot_sway
            ;;
        hyprland)
            workspace_snapshot_hyprland
            ;;
    esac
}

workspace_watch_sway() {
    local status

    workspace_snapshot_sway

    while true; do
        status=0
        read_event || status=$?
        (( status == 2 )) && break
        workspace_snapshot_sway
    done < <(
        command swaymsg \
            -m \
            -t subscribe \
            '["workspace"]'
    )
}

workspace_watch_hyprland() {
    local runtime_dir socket_path status

    workspace_snapshot_hyprland

    runtime_dir=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
    socket_path="${runtime_dir}/hypr/${HYPRLAND_INSTANCE_SIGNATURE}/.socket2.sock"

    [[ -S ${socket_path} ]] || {
        printf \
            'Hyprland event socket is unavailable: %s\n' \
            "${socket_path}" \
            >&2
        return 4
    }

    while true; do
        status=0
        read_event || status=$?
        (( status == 2 )) && break

        if (( status == 1 )); then
            workspace_snapshot_hyprland
            continue
        fi

        case ${event_line} in
            workspace\>\>*|\
            workspacev2\>\>*|\
            focusedmon\>\>*|\
            createworkspace\>\>*|\
            createworkspacev2\>\>*|\
            destroyworkspace\>\>*|\
            destroyworkspacev2\>\>*|\
            moveworkspace\>\>*|\
            moveworkspacev2\>\>*|\
            movewindow\>\>*|\
            movewindowv2\>\>*|\
            openwindow\>\>*|\
            closewindow\>\>*|\
            urgent\>\>*)
                workspace_snapshot_hyprland
                ;;
        esac
    done < <(
        python3 - "${socket_path}" <<'PY_INNER'
import socket
import sys

path = sys.argv[1]

connection = socket.socket(
    socket.AF_UNIX,
    socket.SOCK_STREAM,
)
connection.connect(path)

buffer = ""

while True:
    chunk = connection.recv(4096)

    if not chunk:
        break

    buffer += chunk.decode(
        "utf-8",
        errors="replace",
    )

    while "\n" in buffer:
        line, buffer = buffer.split("\n", 1)
        print(line, flush=True)
PY_INNER
    )
}

workspace_watch() {
    case ${backend} in
        sway)
            workspace_watch_sway
            ;;
        hyprland)
            workspace_watch_hyprland
            ;;
    esac
}

# Focus one of the nine reviewed compositor slots. The slot is the only value
# that crosses this boundary and it is re-validated here, so no caller can
# widen it into a compositor command.
workspace_select() {
    local slot=$1

    case ${backend} in
        sway)
            run_swaymsg -q workspace number "${slot}"
            ;;
        hyprland)
            run_hyprctl dispatch "hl.dsp.focus({ workspace = ${slot} })"
            ;;
    esac
}

# Bring the HyperLab product workspace window forward. It takes no argument:
# the window is the single one owned by the calling HyperLab shell process
# (this adapter's parent, because the reviewed action bridge execs it) whose
# title carries the workspace prefix. A same-titled window from any other
# process -- an operation terminal, a guest -- can never match.
readonly shell_window_title_prefix='HyperLab · '

shell_window_focus() {
    local owner=${PPID} target

    case ${backend} in
        sway)
            target="$(
                run_swaymsg -r -t get_tree |
                    python3 -c '
import json
import sys

owner = int(sys.argv[1])
prefix = sys.argv[2]
found = []


def walk(node):
    if (
        node.get("pid") == owner
        and str(node.get("name") or "").startswith(prefix)
        and isinstance(node.get("id"), int)
    ):
        found.append(node["id"])
    for key in ("nodes", "floating_nodes"):
        for child in node.get(key) or []:
            walk(child)


walk(json.load(sys.stdin))
if len(found) != 1:
    raise SystemExit(3)
print(found[0])
' "${owner}" "${shell_window_title_prefix}"
            )" || {
                printf 'HyperLab workspace window not found\n' >&2
                return 3
            }

            [[ ${target} =~ ^[0-9]+$ ]] || return 3
            run_swaymsg -q "[con_id=${target}] focus"
            ;;
        hyprland)
            target="$(
                run_hyprctl clients -j |
                    python3 -c '
import json
import re
import sys

owner = int(sys.argv[1])
prefix = sys.argv[2]
found = [
    str(client.get("stableId") or "")
    for client in json.load(sys.stdin)
    if client.get("pid") == owner
    and str(client.get("title") or "").startswith(prefix)
]
if len(found) != 1 or not re.fullmatch(r"[0-9a-fA-F]{1,16}", found[0]):
    raise SystemExit(3)
print(found[0])
' "${owner}" "${shell_window_title_prefix}"
            )" || {
                printf 'HyperLab workspace window not found\n' >&2
                return 3
            }

            [[ ${target} =~ ^[0-9a-fA-F]+$ ]] || return 3
            run_hyprctl dispatch \
                "hl.dsp.focus({ window = \"stableid:${target}\" })"
            ;;
    esac
}

backend="$(detect_backend)" ||
    exit $?

operation=${1:-}

case ${operation} in
    backend)
        printf '%s\n' "${backend}"
        ;;

    workspaces-json)
        workspace_snapshot
        ;;

    workspace-watch)
        workspace_watch
        ;;

    workspace-select)
        slot=${2:-}

        [[ ${slot} =~ ^[1-9]$ ]] || {
            printf \
                'workspace slot must be an integer from 1 through 9\n' \
                >&2
            exit 2
        }

        workspace_select "${slot}"
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

    shell-window-focus)
        shell_window_focus
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

    focused-window-json)
        focused_window_json
        ;;

    focused-window-watch)
        focused_window_watch
        ;;

    window-identities-json)
        [[ $# -eq 1 ]] || { usage; exit 2; }
        [[ ${backend} == hyprland ]] || exit 3
        run_hyprctl clients -j | python3 -c '
import json
import re
import sys

windows = []
for node in json.load(sys.stdin):
    address, stable = node.get("address"), node.get("stableId")
    if (node.get("mapped", True) is True and isinstance(address, str)
            and re.fullmatch(r"0x[0-9a-f]{1,16}", address)
            and isinstance(stable, str) and re.fullmatch(r"[0-9a-fA-F]{1,16}", stable)):
        windows.append({"window_id": address, "stable_id": stable.lower()})
print(json.dumps({"windows": windows}, separators=(",", ":")))
'
        ;;

    focus-accent-set|focus-accent-clear)
        # Caller supplies presentation values; this bridge only translates IPC.
        window=${2:-}
        stable=${4:-}
        [[ $# -eq 4 && ${window} =~ ^0x[0-9a-f]{1,16}$ &&
           ${stable} =~ ^[0-9a-f]{1,16}$ ]] || {
            printf 'window address and stable id required\n' >&2
            exit 2
        }
        [[ ${3:-} =~ ^#[0-9a-f]{6}([0-9a-f]{2})?$ ]] || {
            printf 'colour must be #rrggbb or #rrggbbaa\n' >&2
            exit 2
        }
        if [[ ${#3} -eq 7 ]]; then
            value="rgb(${3#\#})"
        else
            value="rgba(${3#\#})"
        fi
        case ${backend} in
            sway)
                printf 'per-window border colour unsupported\n' >&2
                exit 3
                ;;
            hyprland)
                # Stable targeting prevents a recycled address from reaching a
                # different window between the caller snapshot and this write.
                run_hyprctl dispatch \
                    "hl.dsp.window.set_prop({ prop = \"active_border_color\", value = \"${value}\", window = \"stableid:${stable}\" })"
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
