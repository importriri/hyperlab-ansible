#!/usr/bin/env bash
# rofi command palette for the HyperLab.
#
# The list and the final argv both come from hyperlabctl. This shell never joins
# target values into a command: `actions --resolve` validates the selected
# repository target. Unprivileged actions are executed from the JSON argv with
# Python's subprocess API, never through a command-string shell.
#
# Privileged actions are displayed, never executed from the desktop session.
set -euo pipefail

declare -r theme="${HOME}/.config/rofi/rofi-hyperlab.rasi"
declare -r cli=/usr/local/bin/hyperlabctl
declare -r term=foot
declare -r python=/usr/bin/python

menu() {
    local prompt="$1"
    rofi -dmenu -no-show-icons -i -p "${prompt}" -theme "${theme}" || return 1
}

# id \t rendered label \t target \t privileged
actions_table() {
    "${cli}" --json actions | "${python}" -c '
import json, sys
for action in json.load(sys.stdin):
    mark = "!" if action["destructive"] else ("#" if action["privileged"] else " ")
    print("\t".join([
        action["id"],
        "%s %s" % (mark, action["label"]),
        action["target"] or "",
        "yes" if action["privileged"] else "no",
    ]))
' || return 1
}

domain_names() {
    "${cli}" --json vm list | "${python}" -c '
import json, sys
for domain in json.load(sys.stdin):
    print(domain["name"])
' || return 1
}

target_names() {
    "${cli}" actions --choices "$1" || return 1
}

field_by_id() {
    local table="$1" id="$2" column="$3"
    printf '%s\n' "${table}" \
        | awk -F'\t' -v id="${id}" -v column="${column}" '$1 == id { print $column; exit }'
}

show_message() {
    local title="$1" message="$2"
    "${term}" --app-id=floatterm --title="${title}" \
        bash -lc "printf '%s\\n' \"\$1\"; printf '\\n[press Enter to close] '; read -r _" \
        _ "${message}" || return 1
}

show_prepared() {
    local title="$1" command="$2"
    "${term}" --app-id=floatterm --title="${title}" \
        bash -lc "printf '%s\\n\\n%s\\n' 'privileged - review it, then run it yourself:' \"\$1\"; printf '\\n[press Enter to close] '; read -r _" \
        _ "${command}" || return 1
}

run_argv() {
    local title="$1" argv_json="$2"
    "${term}" --app-id=floatterm --title="${title}" \
        "${python}" -c '
import json, subprocess, sys
argv = json.loads(sys.argv[1])
rc = subprocess.call(argv)
input("\n[exit %d - press Enter to close] " % rc)
raise SystemExit(rc)
' "${argv_json}" || return 1
}

open_panel() {
    local argv_json="$1"
    "${term}" --app-id=hyperlab-panel \
        "${python}" -c '
import json, os, sys
argv = json.loads(sys.argv[1])
os.execvp(argv[0], argv)
' "${argv_json}" &
}

main() {
    local table choice id target privileged command argv_json domain spec manifest
    local -a resolve_args
    if ! table="$(actions_table)"; then
        show_message "hyperlab" "hyperlabctl is not responding; run: ${cli} doctor"
        return 0
    fi

    choice="$(printf '%s\n' "${table}" | cut -f1,2 | menu "hyperlab")" || return 0
    [[ -n ${choice} ]] || return 0
    id="${choice%%$'\t'*}"
    target="$(field_by_id "${table}" "${id}" 3)"
    privileged="$(field_by_id "${table}" "${id}" 4)"
    [[ -n ${id} ]] || return 0

    resolve_args=(actions --resolve "${id}")
    case "${target}" in
        domain)
            domain="$(domain_names | menu "${id}: domain")" || return 0
            [[ -n ${domain} ]] || return 0
            resolve_args+=(--domain "${domain}")
            ;;
        spec)
            spec="$(target_names spec | menu "${id}: VM spec")" || return 0
            [[ -n ${spec} ]] || return 0
            resolve_args+=(--spec "${spec}")
            ;;
        manifest)
            manifest="$(target_names manifest | menu "${id}: image manifest")" || return 0
            [[ -n ${manifest} ]] || return 0
            resolve_args+=(--manifest "${manifest}")
            ;;
        "")
            ;;
        *)
            show_message "hyperlab: ${id}" "unsupported target: ${target}"
            return 0
            ;;
    esac

    command="$("${cli}" "${resolve_args[@]}")" || return 0
    if [[ ${privileged} == yes ]]; then
        show_prepared "hyperlab: ${id}" "${command}"
        return 0
    fi

    argv_json="$("${cli}" --json "${resolve_args[@]}")" || return 0
    if [[ ${id} == panel.open ]]; then
        open_panel "${argv_json}"
        return 0
    fi

    run_argv "hyperlab: ${id}" "${argv_json}"
    return 0
}

main "$@"
