#!/usr/bin/env bash
set -euo pipefail

# Toggle the focused window between the reviewed application opacity and fully
# opaque. App policy stays here; compositor discovery/mutation lives only in the
# shared adapter.

readonly compositor_adapter=${HYPERLAB_COMPOSITOR_ADAPTER:-/usr/local/bin/privatestack-compositor-adapter}

state_home=${XDG_STATE_HOME:-"${HOME}/.local/state"}
state_dir=${state_home}/hyperlab
mkdir -p "${state_dir}"

focused="$("${compositor_adapter}" focused-window)"
[[ -n ${focused} ]] || exit 0

IFS=$'\t' read -r con_id app_id <<<"${focused}"
[[ -n ${con_id} ]] || exit 0

case ${app_id} in
    foot) opacity=0.82 ;;
    floatterm) opacity=0.80 ;;
    hyperlab-operation) opacity=0.84 ;;
    firefox|org.mozilla.firefox) opacity=0.90 ;;
    *) opacity=0.90 ;;
esac

state_file=${state_dir}/opacity-${con_id}.state

if [[ -f ${state_file} ]]; then
    "${compositor_adapter}" opacity-set "${opacity}" >/dev/null
    rm -f "${state_file}"
else
    "${compositor_adapter}" opacity-set 1.0 >/dev/null
    printf 'opaque\n' >"${state_file}"
fi
