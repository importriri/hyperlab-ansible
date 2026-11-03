#!/usr/bin/env bash
# waybar bridge for the HyperLab cockpit.
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
# Installed by nitro_sense when its control backend is enabled. It is an
# independent read: a host without hyperlabctl may still have this client.
declare -r nitro_client=/usr/local/bin/hyperlab-nitro-control

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

# The one Nitro read: a fixed `status` request, never a write. A missing
# client, a failure or empty output yields the same fixed fallback; the
# client's own error object is broker diagnostics and is not forwarded.
nitro_status() {
    local payload
    if [[ ! -x ${nitro_client} ]]; then
        fallback "Nitro status is unavailable"
        return 0
    fi
    if ! payload="$(${nitro_client} status 2>/dev/null)" || [[ -z ${payload} ]]; then
        fallback "Nitro status is unavailable"
        return 0
    fi
    printf '%s\n' "${payload}"
    return 0
}

once() {
    local field="$1" payload
    if [[ ${field} == nitro-status ]]; then
        nitro_status
        return 0
    fi
    usable || return 0
    if [[ ${field} == vms ]]; then
        if ! payload="$(${cli} machine inventory --json 2>/dev/null)"; then
            fallback "hyperlabctl Machine inventory failed"
            return 0
        fi
    elif [[ ${field} == network-inventory ]]; then
        if ! payload="$(${cli} --json net list 2>/dev/null)"; then
            fallback "hyperlabctl network inventory failed"
            return 0
        fi
    elif [[ ${field} == diagnostics-domains ]]; then
        # Raw libvirt observation feeds Diagnostics, read-only Not managed
        # rows in Machines and running counts. Existence is not membership.
        if ! payload="$(${cli} waybar --field vms 2>/dev/null)"; then
            fallback "hyperlabctl domain observation failed"
            return 0
        fi
    elif ! payload="$(${cli} waybar --field "${field}" 2>/dev/null)"; then
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
