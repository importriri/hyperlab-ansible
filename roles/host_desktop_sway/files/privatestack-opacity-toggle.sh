#!/usr/bin/env bash
set -euo pipefail

# Replaces `pkill -SIGUSR1 -x waybar` on $mod+o. That signal toggled the bar's
# visibility, which stopped making sense once privatestack-waybar took over the
# layer-shell surface standalone and waybar.css lost its `.hidden` rule.
#
# What $mod+o does now is what its name always suggested: it toggles the
# opacity of the focused window between its per-application value and fully
# opaque, so a terminal can be made readable over a busy background without
# editing sway.config.

state_home=${XDG_STATE_HOME:-"${HOME}/.local/state"}
state_dir=${state_home}/hyperlab
mkdir -p "${state_dir}"

read -r con_id app_id < <(
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
app = node.get("app_id") or (node.get("window_properties") or {}).get("class") or ""
print(node.get("id", ""), app)
'
)
[[ -n ${con_id} ]] || exit 0

# The same table as privatestack-fullscreen.sh and the for_window rules in
# sway.config. Three places is two too many, but splitting it into a file the
# scripts source would need that file installed before either can run.
case ${app_id} in
  foot) opacity=0.82 ;;
  floatterm) opacity=0.80 ;;
  superfile) opacity=0.88 ;;
  hyperlab-operation) opacity=0.84 ;;
  firefox|org.mozilla.firefox) opacity=0.90 ;;
  *) opacity=0.90 ;;
esac

state_file=${state_dir}/opacity-${con_id}.state

if [[ -f ${state_file} ]]; then
  swaymsg -q "opacity set ${opacity}"
  rm -f "${state_file}"
else
  swaymsg -q opacity set 1.0
  printf 'opaque\n' >"${state_file}"
fi
