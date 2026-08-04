#!/usr/bin/env bash
set -euo pipefail

# Persisted Sway keyboard layout controller. The desktop language stays English;
# only the active XKB layout changes.
readonly config_home=${XDG_CONFIG_HOME:-"${HOME}/.config"}
readonly config_dir=${config_home}/hyperlab
readonly state_file=${config_dir}/keyboard-layout
readonly layouts=(it us ara)

mkdir -p "${config_dir}"

valid_layout() {
    local candidate
    for candidate in "${layouts[@]}"; do
        [[ ${1:-} == "${candidate}" ]] && return 0
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
    [[ -r ${state_file} ]] && IFS= read -r value <"${state_file}" || true
    valid_layout "${value}" || value=it
    printf '%s\n' "${value}"
}

write_atomic() {
    local value=$1 temporary="${state_file}.tmp.$$"
    printf '%s\n' "${value}" >"${temporary}"
    chmod 0644 "${temporary}"
    mv -f "${temporary}" "${state_file}"
}

signal_bar() {
    pkill -SIGRTMIN+10 -x waybar 2>/dev/null || true
    pkill -SIGRTMIN+11 -x waybar 2>/dev/null || true
}

apply_layout() {
    local layout=$1 index
    valid_layout "${layout}" || {
        printf 'usage: %s set it|us|ara\n' "$0" >&2
        return 2
    }
    index=$(layout_index "${layout}")
    # Set the layout by name instead of switching an index. This remains
    # reliable across reloads and machine-specific input files, including a
    # temporary single-layout configuration.
    if ! swaymsg -q input type:keyboard xkb_layout "${layout}" >/dev/null; then
        printf 'HyperLab: Sway rejected keyboard layout %s (index %s).\n'             "${layout}" "${index}" >&2
        return 1
    fi
    write_atomic "${layout}"
    signal_bar
    if [[ ${2:-} != --quiet ]] && command -v notify-send >/dev/null 2>&1; then
        notify-send 'HyperLab keyboard' "Layout: $(layout_name "${layout}")"
    fi
}

cycle_layout() {
    local current index next
    current=$(current_layout)
    index=$(layout_index "${current}")
    next=${layouts[$(( (index + 1) % ${#layouts[@]} ))]}
    apply_layout "${next}"
}

status_json() {
    local layout label name
    layout=$(current_layout)
    label=$(layout_label "${layout}")
    name=$(layout_name "${layout}")
    printf '{"text":" %s","tooltip":"Keyboard layout: %s\\nClick: next layout\\nRight-click: all controls","class":"%s"}\n' \
        "${label}" "${name}" "${layout}"
}

case ${1:-current} in
    current|status) current_layout ;;
    name) layout_name "$(current_layout)" ;;
    label) layout_label "$(current_layout)" ;;
    set) apply_layout "${2:-}" ;;
    cycle|toggle) cycle_layout ;;
    apply|session-start) apply_layout "$(current_layout)" --quiet ;;
    status-json|json) status_json ;;
    *)
        printf 'usage: %s {current|name|label|set it|us|ara|cycle|apply|status-json}\n' "$0" >&2
        exit 2
        ;;
esac
