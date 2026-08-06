#!/usr/bin/env bash
# /usr/local/bin/hyperlabctl - the cockpit's way of reaching the CLI by name.
#
# The CLI lives in the repository, not in /usr/local: it reads group_vars, and a
# copy detached from the checkout would answer from a contract that no longer
# exists. So this wrapper only has to know WHERE the checkout is, and it reads
# that from one plain line written by the desktop brick.
#
# Deliberately not a template. The repository shellchecks every file that starts
# with a bash shebang, discovered rather than listed, and a Jinja expression
# inside bash is not shell - it fails to parse before it fails to run.
set -euo pipefail

declare -r pointer=/etc/hyperlabctl/checkout

if [[ ! -r ${pointer} ]]; then
    printf 'hyperlabctl: %s is missing\n' "${pointer}" >&2
    printf 'run playbooks/host-desktop-sway.yml to write it\n' >&2
    exit 127
fi

declare checkout
checkout="$(head -n 1 "${pointer}")"

if [[ -z ${checkout} || ! -x ${checkout}/tools/hyperlabctl/bin/hyperlabctl ]]; then
    printf 'hyperlabctl: no checkout at %s\n' "${checkout:-<empty>}" >&2
    printf 'set desktop_hyperlab_checkout and re-run playbooks/host-desktop-sway.yml\n' >&2
    exit 127
fi

exec "${checkout}/tools/hyperlabctl/bin/hyperlabctl" "$@"
