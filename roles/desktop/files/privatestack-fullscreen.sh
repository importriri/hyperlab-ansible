#!/usr/bin/env bash
set -euo pipefail

state_home=${XDG_STATE_HOME:-"${HOME}/.local/state"}
state_dir=${state_home}/hyperlab
mode_file=${state_dir}/fullscreen-transparency.mode
mkdir -p "${state_dir}"

notify() {
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "HyperLab" "$1" || true
  fi
}

readarray -t focused < <(
  swaymsg -r -t get_tree | python3 -c '
import json, sys

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
rect = node.get("rect") or {}
app = node.get("app_id") or (node.get("window_properties") or {}).get("class") or ""
print(node.get("id", ""))
print(node.get("fullscreen_mode", 0))
print(node.get("floating", "user_off"))
print(rect.get("x", 0))
print(rect.get("y", 0))
print(rect.get("width", 0))
print(rect.get("height", 0))
print(app)
print("hyperlab-transparent-fullscreen" in (node.get("marks") or []))
'
)

con_id=${focused[0]:-}
fullscreen_mode=${focused[1]:-0}
floating=${focused[2]:-user_off}
x=${focused[3]:-0}
y=${focused[4]:-0}
width=${focused[5]:-0}
height=${focused[6]:-0}
app_id=${focused[7]:-}
marked=${focused[8]:-False}
[[ -n ${con_id} ]] || exit 0

case ${app_id} in
  foot) opacity=0.82 ;;
  floatterm) opacity=0.80 ;;
  superfile) opacity=0.88 ;;
  hyperlab-operation) opacity=0.84 ;;
  firefox|org.mozilla.firefox) opacity=0.90 ;;
  *) opacity=0.90 ;;
esac

[[ -f ${mode_file} ]] || printf 'enabled\n' >"${mode_file}"

if [[ ${1:-} == --toggle-mode ]]; then
  if [[ $(<"${mode_file}") == enabled ]]; then
    printf 'disabled\n' >"${mode_file}"
    swaymsg -q "[con_id=${con_id}] opacity set 1.0"
    notify "Fullscreen transparency: OFF"
  else
    printf 'enabled\n' >"${mode_file}"
    swaymsg -q "[con_id=${con_id}] opacity set ${opacity}"
    notify "Fullscreen transparency: ON"
  fi
  exit 0
fi

mode=$(<"${mode_file}")
state_file=${state_dir}/fullscreen-${con_id}.state

if [[ ${mode} != enabled ]]; then
  if (( fullscreen_mode > 0 )); then
    swaymsg -q "[con_id=${con_id}] fullscreen disable"
  else
    swaymsg -q "[con_id=${con_id}] fullscreen enable"
  fi
  swaymsg -q "[con_id=${con_id}] opacity set 1.0"
  exit 0
fi

# Transparent mode uses a borderless pseudo-fullscreen floating container.
# This avoids compositor/direct-scanout paths that can force native fullscreen
# opaque on some systems while preserving the same Mod+F enter/leave gesture.
if [[ ${marked} == True ]]; then
  swaymsg -q "[con_id=${con_id}] unmark hyperlab-transparent-fullscreen"
  if [[ -f ${state_file} ]]; then
    read -r old_floating old_x old_y old_w old_h <"${state_file}"
    if [[ ${old_floating} == user_on || ${old_floating} == auto_on ]]; then
      swaymsg -q "[con_id=${con_id}] resize set ${old_w} ${old_h}"
      swaymsg -q "[con_id=${con_id}] move position ${old_x} ${old_y}"
    else
      swaymsg -q "[con_id=${con_id}] floating disable"
    fi
    rm -f "${state_file}"
  fi
  swaymsg -q "[con_id=${con_id}] opacity set ${opacity}"
  exit 0
fi

readarray -t output < <(
  swaymsg -r -t get_outputs | python3 -c '
import json, sys
outputs = [o for o in json.load(sys.stdin) if o.get("active")]
out = next((o for o in outputs if o.get("focused")), outputs[0] if outputs else {})
r = out.get("rect") or {}
print(r.get("x", 0))
print(r.get("y", 0))
print(r.get("width", 0))
print(r.get("height", 0))
'
)
out_x=${output[0]:-0}
out_y=${output[1]:-0}
out_w=${output[2]:-0}
out_h=${output[3]:-0}
(( out_w > 0 && out_h > 0 )) || exit 1

printf '%s %s %s %s %s\n' \
  "${floating}" "${x}" "${y}" "${width}" "${height}" >"${state_file}"
swaymsg -q "[con_id=${con_id}] fullscreen disable"
swaymsg -q "[con_id=${con_id}] mark --add hyperlab-transparent-fullscreen"
swaymsg -q "[con_id=${con_id}] floating enable"
swaymsg -q "[con_id=${con_id}] move position ${out_x} ${out_y}"
swaymsg -q "[con_id=${con_id}] resize set ${out_w} ${out_h}"
swaymsg -q "[con_id=${con_id}] opacity set ${opacity}"
