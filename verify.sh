#!/usr/bin/env bash
# verify.sh - the whole verification battery, one command, from the repo
# root. Managed by privatestack-ansible (part of the A1 scaffold).
#
# Mirrors what CI runs, BY DISCOVERY: the same script is correct at every
# stage of the repo, because it checks what exists instead of what is
# enumerated. Adding a brick never requires touching this file - same
# contract as the CI workflow.
#
# Run it before every commit. It also works as a git pre-commit hook:
#     ln -s ../../verify.sh .git/hooks/pre-commit
#
# Exit code: 0 only if EVERY level of the pyramid is green.
set -u
cd "$(dirname "$0")" || exit 1

fail=0

if ! ansible-galaxy collection list community.general >/dev/null 2>&1 \
   || ! ansible-galaxy collection list community.libvirt >/dev/null 2>&1; then
    echo "Missing collections. Run: ansible-galaxy collection install -r collections/requirements.yml" >&2
    exit 1
fi

step() {
    printf '\n== %s\n' "$1"
}

run() {
    # capture quietly, show the tail only on failure
    local log
    log="$(mktemp)"
    if "$@" >"${log}" 2>&1; then
        echo "   OK"
    else
        echo "   FAIL - last lines:"
        tail -n 25 "${log}" | sed 's/^/   | /'
        fail=1
    fi
    rm -f "${log}"
}

run_render() {
    # tests/render.yml validates nftables with become. CI has passwordless
    # sudo and no TTY; an operator's terminal normally needs the become
    # password. Do not hide that prompt inside run()'s captured stderr.
    if [ -t 0 ]; then
        if ansible-playbook -K -i inventory.ini tests/render.yml \
            --extra-vars '{"hardware_profiles":{"nitro-3060":{"vfio_ids":["10de:2520","10de:228e"]}}}'; then
            echo "   OK"
        else
            echo "   FAIL"
            fail=1
        fi
    else
        run ansible-playbook -i inventory.ini tests/render.yml \
            --extra-vars '{"hardware_profiles":{"nitro-3060":{"vfio_ids":["10de:2520","10de:228e"]}}}'
    fi
}

step "level 0a - static pipeline contract"
run python tests/static_contract.py

step "level 0c - image manifest and VM spec schemas"
run python tests/schema_validate.py

step "level 0d - contract mutation tests"
run python tests/schema_mutations.py
run python tests/contract_mutations.py

step "level 0 - ansible-lint (production profile)"
run ansible-lint

step "level 1 - syntax-check (every playbook, discovered)"
ok=1
for pb in playbooks/*.yml; do
    if ! ansible-playbook --syntax-check -i inventory.ini "${pb}" >/dev/null 2>&1; then
        echo "   FAIL: ${pb}"
        ok=0
    fi
done
if [ "${ok}" -eq 1 ]; then echo "   OK"; else fail=1; fi

step "level 2 - render / invariant tests"
# M0's renderer still names the old variable in one isolated fake-data
# expression. Supply that fixture explicitly while production data and every
# M1 contract use host_profiles. Remove this bridge with the test-only render
# migration; never restore the legacy key to production group_vars.
run_render

if ls tests/*.bats >/dev/null 2>&1; then
    step "level 3 - protocol tests (bats, discovered)"
    run bats tests/*.bats
fi

scripts="$(grep -rlE '^#!(/usr)?/bin/(env )?(ba)?sh' --exclude-dir=.git --exclude='*.md' . 2>/dev/null || true)"
if [ -n "${scripts}" ]; then
    step "level 0b - shellcheck (every shell script, discovered - this file included)"
    if echo "${scripts}" | xargs shellcheck; then
        echo "   OK"
    else
        echo "   FAIL"
        fail=1
    fi
fi

printf '\n'
if [ "${fail}" -eq 0 ]; then
    echo "ALL GREEN - ready to commit."
    echo "(level 4 - the real world - runs on the host: --check --diff, run, changed=0)"
else
    echo "VERIFICATION FAILED - read above. No commit until this is green."
    exit 1
fi
