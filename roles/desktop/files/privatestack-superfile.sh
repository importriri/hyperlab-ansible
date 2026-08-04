#!/usr/bin/env bash
set -euo pipefail

state_home=${XDG_STATE_HOME:-"${HOME}/.local/state"}
state_dir=${state_home}/hyperlab
mkdir -p "${state_dir}"

app_id=superfile
width=${HYPERLAB_SUPERFILE_WIDTH:-1200}
height=${HYPERLAB_SUPERFILE_HEIGHT:-800}
min_rows=${HYPERLAB_SUPERFILE_MIN_ROWS:-24}
min_columns=${HYPERLAB_SUPERFILE_MIN_COLUMNS:-60}

# This branch runs inside Foot. Superfile must not start until Sway has applied
# the floating geometry; otherwise it observes the small tiled geometry and
# exits before the outer launcher can resize the window.
if [[ ${1:-} == --session ]]; then
  report=${state_dir}/superfile-size.log
  for attempt in $(seq 1 100); do
    read -r rows columns < <(stty size)
    printf 'attempt=%s rows=%s columns=%s\n' \
      "${attempt}" "${rows}" "${columns}" >"${report}"

    if (( rows >= min_rows && columns >= min_columns )); then
      printf 'READY rows=%s columns=%s\n' \
        "${rows}" "${columns}" >>"${report}"
      exec spf
    fi
    sleep 0.05
  done

  printf 'FAILED: terminal remained below %sx%s\n' \
    "${min_columns}" "${min_rows}" >>"${report}"
  cat "${report}"
  printf '\nPress Enter to close.'
  read -r _
  exit 1
fi

existing=$(
  swaymsg -r -t get_tree | python3 -c '
import json, sys
wanted = sys.argv[1]

def walk(node):
    yield node
    for key in ("nodes", "floating_nodes"):
        for child in node.get(key, []):
            yield from walk(child)

for node in walk(json.load(sys.stdin)):
    if node.get("app_id") == wanted:
        print(node.get("id", ""))
        break
' "${app_id}"
)

if [[ -n ${existing} ]]; then
  swaymsg -q "[con_id=${existing}] focus"
  exit 0
fi

read -r out_w out_h < <(
  swaymsg -r -t get_outputs | python3 -c '
import json, sys
outputs = [o for o in json.load(sys.stdin) if o.get("active")]
out = next((o for o in outputs if o.get("focused")), outputs[0] if outputs else {})
rect = out.get("rect") or {}
print(rect.get("width", 0), rect.get("height", 0))
'
)
if (( out_w > 0 && out_h > 0 )); then
  (( width > out_w - 80 )) && width=$(( out_w - 80 ))
  (( height > out_h - 80 )) && height=$(( out_h - 80 ))
fi

foot --app-id="${app_id}" --window-size-chars=100x32 "$0" --session &

for _ in $(seq 1 80); do
  sleep 0.05
  id=$(
    swaymsg -r -t get_tree | python3 -c '
import json, sys
wanted = sys.argv[1]

def walk(node):
    yield node
    for key in ("nodes", "floating_nodes"):
        for child in node.get(key, []):
            yield from walk(child)

for node in walk(json.load(sys.stdin)):
    if node.get("app_id") == wanted:
        print(node.get("id", ""))
        break
' "${app_id}"
  )
  if [[ -n ${id} ]]; then
    swaymsg -q "[con_id=${id}] floating enable"
    swaymsg -q "[con_id=${id}] resize set ${width} ${height}"
    swaymsg -q "[con_id=${id}] move position center"
    exit 0
  fi
done

exit 1
