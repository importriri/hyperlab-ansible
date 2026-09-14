#!/usr/bin/env bash
# rofi power menu for the privatestack cockpit.
#
# Destructive actions ask twice; lock and suspend do not. Everything goes
# through logind/systemd and the narrow compositor adapter; no sudo is used.
set -euo pipefail

declare -r theme="${HOME}/.config/rofi/rofi-powermenu.rasi"
declare -r compositor_adapter=${HYPERLAB_COMPOSITOR_ADAPTER:-/usr/local/bin/privatestack-compositor-adapter}
declare -r lock="  lock"
declare -r suspend="  suspend"
declare -r logout="  log out"
declare -r reboot="  reboot"
declare -r poweroff="  power off"

menu() {
    local prompt="$1"
    shift
    printf '%s\n' "$@" \
        | rofi -dmenu -no-show-icons -i -p "${prompt}" -theme "${theme}" \
        || return 1
}

confirm() {
    local what="$1"
    local answer
    answer="$(menu "${what}?" "  no" "  yes")" || return 1
    [[ ${answer} == *yes* ]] || return 1
    return 0
}

main() {
    local choice
    choice="$(menu "power" "${lock}" "${suspend}" "${logout}" "${reboot}" "${poweroff}")" || return 0
    [[ -n ${choice} ]] || return 0

    case ${choice} in
        "${lock}")     /usr/local/bin/privatestack-lock || return 1 ;;
        "${suspend}")  systemctl suspend || return 1 ;;
        "${logout}")   confirm "log out" && { "${compositor_adapter}" session-exit || return 1; } ;;
        "${reboot}")   confirm "reboot" && { systemctl reboot || return 1; } ;;
        "${poweroff}") confirm "power off" && { systemctl poweroff || return 1; } ;;
        *)             echo "unknown choice: ${choice}" >&2; return 1 ;;
    esac
    return 0
}

main "$@"
