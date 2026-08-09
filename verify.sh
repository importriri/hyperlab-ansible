#!/usr/bin/env bash
# verify.sh - the whole verification battery, one command, from the repo
# root. Managed by hyperlab-ansible (part of the A1 scaffold).
set -u
cd "$(dirname "$0")" || exit 1

fail=0
render_password_file=""

cleanup_render_password_file() {
    if [ -n "${render_password_file}" ]; then
        rm -f -- "${render_password_file}"
        render_password_file=""
    fi
}
trap cleanup_render_password_file EXIT

if ! ansible-galaxy collection list community.general >/dev/null 2>&1 \
   || ! ansible-galaxy collection list community.libvirt >/dev/null 2>&1; then
    echo "Missing collections. Run: ansible-galaxy collection install -r collections/requirements.yml" >&2
    exit 1
fi

missing=""
for tool in ansible-lint ruff shellcheck bats python; do
    command -v "${tool}" >/dev/null 2>&1 || missing="${missing} ${tool}"
done
if [ -n "${missing}" ]; then
    echo "Missing tools:${missing}" >&2
    echo "On Arch: sudo pacman -S ansible-lint ruff shellcheck bats python" >&2
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
    local attempt
    local become_password
    local password_valid=0
    local runtime_dir

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
        # A sudo timestamp may be scoped to a process or terminal and therefore
        # unavailable to Ansible's become subprocess. Validate one credential
        # directly, then give Ansible that same credential through a private,
        # short-lived password file. This also avoids Ansible's non-retryable
        # duplicate-prompt failure after a typo.
        runtime_dir="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
        if [ ! -d "${runtime_dir}" ] || [ ! -O "${runtime_dir}" ]; then
            echo "Render tests require a private user runtime directory: ${runtime_dir}" >&2
            fail=1
            return
        fi

        render_password_file="$(mktemp "${runtime_dir}/privatestack-verify-become.XXXXXX")" \
            || {
                echo "Render tests could not create a private become password file." >&2
                fail=1
                return
            }
        if ! chmod 0600 "${render_password_file}"; then
            echo "Render tests could not protect the become password file." >&2
            cleanup_render_password_file
            fail=1
            return
        fi

        for attempt in 1 2 3; do
            printf 'BECOME password (attempt %s/3): ' "${attempt}" >&2
            if ! IFS= read -r -s become_password; then
                printf '\n' >&2
                echo "Render tests could not read sudo credentials." >&2
                unset become_password
                cleanup_render_password_file
                fail=1
                return
            fi
            printf '\n' >&2

            if [ -z "${become_password}" ]; then
                echo "The become password cannot be empty." >&2
                continue
            fi

            printf '%s\n' "${become_password}" >"${render_password_file}"
            unset become_password

            if awk 'NR == 1 { print; exit }' "${render_password_file}" \
                | sudo -S -k -p '' -v; then
                password_valid=1
                break
            fi
        done
        unset become_password

        if [ "${password_valid}" -ne 1 ]; then
            echo "Render tests could not validate sudo credentials." >&2
            cleanup_render_password_file
            fail=1
            return
        fi

        # Prove the render suite uses the supplied credential, not a timestamp
        # that happens to be valid in this shell.
        sudo -k
        become_args=(--become-password-file "${render_password_file}")
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

    cleanup_render_password_file
}

scripts="$(grep -rlE '^#!(/usr)?/bin/(env )?(ba)?sh' --exclude-dir=.git --exclude='*.md' . 2>/dev/null || true)"
if [ -n "${scripts}" ]; then
    step "level 0a - shellcheck (every shell script, discovered - this file included)"
    if echo "${scripts}" | xargs shellcheck; then
        echo "   OK"
    else
        echo "   FAIL"
        fail=1
    fi
fi

step "level 0b - static pipeline contract"
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

step "level 0f - shell structure (no display required)"
run sh tools/shell-tests/run.sh

step "level 0g - palette and open choices"
run python3 tools/palette/audit_palette.py tools/palette/palette.yml
run python3 tools/palette/verify_surfaces.py roles/host_desktop_sway/files/palette
run python3 tools/choices/choices.py check
run python3 tools/choices/test_choices.py
run python3 tools/choices/test_consistency.py

step "level 0h - ruff (every Python file, repo ruleset)"
run ruff check .

step "level 0i - ansible-lint (production profile)"
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
    step "level 2a - refusal suites (discovered)"
    for suite in "${refusal_suites[@]}"; do
        run ansible-playbook -i inventory.ini "${suite}"
    done
fi

step "level 2b - render / invariant tests"
run_render

if ls tests/*.bats >/dev/null 2>&1; then
    step "level 3 - protocol tests (bats, discovered)"
    run bats tests/*.bats
fi

printf '\n'
if [ "${fail}" -eq 0 ]; then
    echo "ALL GREEN - ready to commit."
    echo "(level 4 - the real world - runs on the host: --check --diff, run, changed=0)"
else
    echo "VERIFICATION FAILED - read above. No commit until this is green."
    exit 1
fi
