#!/usr/bin/env bash
set -euo pipefail

# HyperLab focus provenance accent and trust RGB actuator.
#
#   privatestack-focus-accent run
#
# Runs the reviewed actuator from the HyperLab checkout, the same checkout
# whose resolver and rendered trust-model map it reads, then replaces itself
# with it so systemd supervises exactly one process. The actuator decides no
# identity: it mirrors the resolver and the host trust claim onto the focused
# window's border and, when enabled, the keyboard RGB.

readonly pointer=/etc/hyperlabctl/checkout
readonly python=/usr/bin/python3

usage() {
    printf 'usage: privatestack-focus-accent run\n' >&2
    exit 2
}

[[ $# -eq 1 && $1 == run ]] || usage

if [[ ! -r ${pointer} ]]; then
    printf 'focus accent: %s is missing\n' "${pointer}" >&2
    exit 3
fi

checkout="$(head -n 1 "${pointer}")"
readonly checkout
readonly actuator="${checkout}/tools/focus_accent.py"

if [[ ${checkout} != /* || ! -f ${actuator} ]]; then
    printf 'focus accent: no reviewed actuator in the checkout\n' >&2
    exit 3
fi

# -I ignores PYTHON* variables and the user site; -B keeps the checkout free
# of bytecode written on behalf of the session.
exec "${python}" -I -B "${actuator}" --repo "${checkout}" run
