#!/usr/bin/env bash
set -euo pipefail

# HyperLab focused-surface provenance bridge.
#
#   privatestack-surface-provenance stream
#
# Runs the reviewed read-only resolver from the HyperLab checkout, the same
# checkout whose launcher publishes managed surface registrations, so both
# sides pin the same VM specifications. The shell writes one correlated focus
# request per line on stdin and reads one answer per line on stdout.
#
# This bridge owns no trust decision and mutates nothing: it only locates the
# resolver, the per-user registry and /proc, then replaces itself with the
# resolver so the shell owns exactly one process.

readonly pointer=/etc/hyperlabctl/checkout
readonly python=/usr/bin/python3

usage() {
    printf 'usage: privatestack-surface-provenance stream\n' >&2
    exit 2
}

[[ $# -eq 1 && $1 == stream ]] || usage

if [[ ! -r ${pointer} ]]; then
    printf 'surface provenance: %s is missing\n' "${pointer}" >&2
    exit 3
fi

checkout="$(head -n 1 "${pointer}")"
readonly checkout
readonly resolver="${checkout}/tools/surface_provenance.py"

if [[ ${checkout} != /* || ! -f ${resolver} ]]; then
    printf 'surface provenance: no reviewed resolver in the checkout\n' >&2
    exit 3
fi

runtime_dir=${XDG_RUNTIME_DIR:-/run/user/$(id -u)}
readonly runtime_dir

# -I ignores PYTHON* variables and the user site; -B keeps the checkout free
# of bytecode written on behalf of the shell.
exec "${python}" -I -B "${resolver}" \
    --repo "${checkout}" \
    --proc-root /proc \
    stream \
    --registry "${runtime_dir}/hyperlab/surface-provenance.json"
