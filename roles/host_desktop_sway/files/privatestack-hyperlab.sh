#!/usr/bin/env bash
# waybar bridge for the Hyperlab cockpit.
#
#   privatestack-hyperlab <field>          one payload, then exit  (polled pill)
#   privatestack-hyperlab watch <field>    a payload per event     (stream)
#
# Deliberately NOT `set -e`: if hyperlabctl is missing or broken the module must
# still print a valid payload, because a waybar module that exits non-zero
# disappears from the bar - and a cockpit that vanishes when something is wrong
# is worse than no cockpit.
set -uo pipefail

declare -r cli=/usr/local/bin/hyperlabctl

fallback() {
    local reason="$1"
    printf '{"text":"?","alt":"error","class":"error","tooltip":"%s"}\n' "${reason}"
    return 0
}

usable() {
    if [[ ! -x ${cli} ]]; then
        fallback "hyperlabctl is not installed on this host"
        return 1
    fi
    return 0
}

once() {
    local field="$1" payload
    usable || return 0
    if ! payload="$(${cli} waybar --field "${field}" 2>/dev/null)"; then
        fallback "hyperlabctl failed: run ${cli} doctor in a terminal"
        return 0
    fi
    if [[ -z ${payload} ]]; then
        fallback "hyperlabctl printed nothing"
        return 0
    fi
    printf '%s\n' "${payload}"
    return 0
}

stream() {
    local field="$1"
    usable || return 0
    # No polling: hyperlabctl blocks on `virsh event` and prints when something
    # actually happens. waybar's restart-interval covers the case where libvirt
    # itself goes away underneath us.
    ${cli} watch --field "${field}" 2>/dev/null || fallback "hyperlabctl watch stopped"
    return 0
}

main() {
    if [[ ${1:-} == watch ]]; then
        stream "${2:-summary}"
        return 0
    fi
    once "${1:-summary}"
    return 0
}

main "$@"
