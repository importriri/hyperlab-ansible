#!/usr/bin/env bash
set -euo pipefail

# Persisted host keyboard-layout controller.
# Desktop language remains English; only the active XKB layout changes.
# Layout policy/state lives here. Compositor IPC lives in the shared adapter.

readonly config_home=${XDG_CONFIG_HOME:-"${HOME}/.config"}
readonly config_dir=${config_home}/hyperlab
readonly state_file=${config_dir}/keyboard-layout
readonly layouts=(it us ara)
readonly compositor_adapter=${HYPERLAB_COMPOSITOR_ADAPTER:-/usr/local/bin/privatestack-compositor-adapter}

layout_order="$(IFS=,; printf '%s' "${layouts[*]}")"
readonly layout_order

mkdir -p "${config_dir}"

valid_layout() {
    local candidate

    for candidate in "${layouts[@]}"; do
        [[ ${1:-} == "${candidate}" ]] &&
            return 0
    done

    return 1
}

layout_label() {
    case ${1:-it} in
        it) printf 'IT\n' ;;
        us) printf 'EN\n' ;;
        ara) printf 'AR\n' ;;
    esac
}

layout_name() {
    case ${1:-it} in
        it) printf 'Italian\n' ;;
        us) printf 'English (US)\n' ;;
        ara) printf 'Arabic\n' ;;
    esac
}

layout_index() {
    local index

    for index in "${!layouts[@]}"; do
        if [[ ${1:-it} == "${layouts[$index]}" ]]; then
            printf '%s\n' "${index}"
            return 0
        fi
    done

    return 1
}

current_layout() {
    local value=it

    if [[ -r ${state_file} ]]; then
        IFS= read -r value <"${state_file}" || true
    fi

    valid_layout "${value}" ||
        value=it

    printf '%s\n' "${value}"
}

write_atomic() {
    local value=$1
    local temporary="${state_file}.tmp.$$"

    printf '%s\n' "${value}" >"${temporary}"
    chmod 0644 "${temporary}"
    mv -f "${temporary}" "${state_file}"
}

signal_bar() {
    pkill -SIGRTMIN+10 -x waybar 2>/dev/null || true
    pkill -SIGRTMIN+11 -x waybar 2>/dev/null || true
}

apply_layout() {
    local layout=$1
    local index

    valid_layout "${layout}" || {
        printf 'usage: %s set it|us|ara\n' "$0" >&2
        return 2
    }

    index="$(layout_index "${layout}")"

    if ! "${compositor_adapter}" \
        keyboard-set \
        "${layout}" \
        "${index}" \
        "${layout_order}" \
        >/dev/null
    then
        printf \
            'HyperLab: compositor rejected keyboard layout %s (index %s, order %s).\n' \
            "${layout}" \
            "${index}" \
            "${layout_order}" \
            >&2
        return 1
    fi

    write_atomic "${layout}"
    signal_bar

    if [[ ${2:-} != --quiet ]] &&
       command -v notify-send >/dev/null 2>&1
    then
        notify-send \
            'HyperLab keyboard' \
            "Layout: $(layout_name "${layout}")"
    fi
}

cycle_layout() {
    local current
    local index
    local count
    local next

    current="$(current_layout)"
    index="$(layout_index "${current}")"
    count="${#layouts[@]}"
    next="${layouts[(index + 1) % count]}"

    apply_layout "${next}"
}

status_json() {
    local layout
    local label
    local name

    layout="$(current_layout)"
    label="$(layout_label "${layout}")"
    name="$(layout_name "${layout}")"

    printf \
        '{"text":" %s","tooltip":"Keyboard layout: %s\\nClick: next layout\\nRight-click: all controls","class":"%s"}\n' \
        "${label}" \
        "${name}" \
        "${layout}"
}

case ${1:-current} in
    current|status)
        current_layout
        ;;
    name)
        layout_name "$(current_layout)"
        ;;
    label)
        layout_label "$(current_layout)"
        ;;
    set)
        apply_layout "${2:-}"
        ;;
    cycle|toggle)
        cycle_layout
        ;;
    apply|session-start)
        apply_layout "$(current_layout)" --quiet
        ;;
    status-json|json)
        status_json
        ;;
    *)
        printf \
            'usage: %s {current|name|label|set it|us|ara|cycle|apply|status-json}\n' \
            "$0"             >&2
        exit 2
        ;;
esac
