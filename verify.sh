#!/usr/bin/env bash
# verify.sh - the whole verification battery, one command, from the repo
# root. Managed by privatestack-ansible (part of the A1 scaffold).
set -u
cd "$(dirname "$0")" || exit 1

fail=0

if ! ansible-galaxy collection list community.general >/dev/null 2>&1 \
   || ! ansible-galaxy collection list community.libvirt >/dev/null 2>&1; then
    echo "Missing collections. Run: ansible-galaxy collection install -r collections/requirements.yml" >&2
    exit 1
fi

step() { printf '\n== %s\n' "$1"; }

run() {
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
    local -a become_args=()

    # A supplied password file is authoritative even when verify.sh runs in the
    # background or with redirected stdin. TTY detection is only a fallback for
    # interactive runs that did not provide a password file.
    if [ -n "${PRIVATESTACK_BECOME_PASSWORD_FILE:-}" ]; then
        if [ ! -r "${PRIVATESTACK_BECOME_PASSWORD_FILE}" ]; then
            echo "Configured become password file is not readable." >&2
            fail=1
            return
        fi
        become_args=(--become-password-file "${PRIVATESTACK_BECOME_PASSWORD_FILE}")
    elif [ -t 0 ]; then
        # Interactive runs always pass the password explicitly to Ansible.
        # Do not rely on a sudo timestamp that may expire during earlier tests.
        become_args=(-K)
    elif sudo -n true 2>/dev/null; then
        # Non-interactive CI may use passwordless sudo.
        become_args=()
    else
        echo "Render tests require sudo credentials. Set PRIVATESTACK_BECOME_PASSWORD_FILE or run interactively." >&2
        fail=1
        return
    fi

    if [ -t 1 ]; then
        if ansible-playbook "${become_args[@]}" -i inventory.ini tests/render.yml \
            --extra-vars '{"hardware_profiles":{"nitro-3060":{"vfio_ids":["10de:2520","10de:228e"]}}}'; then
            echo "   OK"
        else
            echo "   FAIL"
            fail=1
        fi
    else
        run ansible-playbook "${become_args[@]}" -i inventory.ini tests/render.yml \
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

contracts=(tests/*_contract.py)
if [ -e "${contracts[0]}" ]; then
    step "level 0e - per-brick structural contracts (discovered)"
    for contract in "${contracts[@]}"; do
        run python "${contract}"
    done
fi

step "level 0g - shell structure (no display required)"
run sh tools/shell-tests/run.sh

step "level 0f - palette and open choices"
run python3 tools/palette/audit_palette.py tools/palette/palette.yml
run python3 tools/palette/verify_surfaces.py roles/desktop/files/palette
run python3 tools/choices/choices.py check
run python3 tools/choices/test_choices.py
run python3 tools/choices/test_consistency.py

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

refusal_suites=(tests/*-refusals.yml)
if [ -e "${refusal_suites[0]}" ]; then
    step "level 2b - refusal suites (discovered)"
    for suite in "${refusal_suites[@]}"; do
        run ansible-playbook -i inventory.ini "${suite}"
    done
fi

step "level 2 - render / invariant tests"
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
