#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = (ROOT / "run-nitro-m9-cockpit-gate.sh").read_text()
VERIFY = (ROOT / "verify.sh").read_text()


def main() -> int:
    prompt = 'step "Read the become password once for all automated host gates"'
    verify = 'step "Complete repository verification battery"'
    assert prompt in GATE and verify in GATE
    assert GATE.index(prompt) < GATE.index(verify)

    assert 'mktemp "${runtime_dir}/privatestack-become.XXXXXX"' in GATE
    assert 'chmod 0600 "${BECOME_PASSWORD_FILE}"' in GATE
    assert 'trap cleanup_become_password EXIT' in GATE
    assert "IFS= read -r -s become_password" in GATE
    assert "unset become_password" in GATE
    assert 'ansible-playbook --become-password-file "${BECOME_PASSWORD_FILE}"' in GATE
    assert 'PRIVATESTACK_BECOME_PASSWORD_FILE="${BECOME_PASSWORD_FILE}"' in GATE
    assert "feed_become_password()" in GATE
    assert 'awk \'NR == 1 { print; exit }\' "${BECOME_PASSWORD_FILE}"' in GATE
    assert "feed_become_password | sudo -S -k -p '' -v" in GATE
    assert 'feed_become_password | sudo -S -k -p \'\' "$@"' in GATE
    assert 'sudo -S -k -p \'\' -v <"${BECOME_PASSWORD_FILE}"' not in GATE
    assert 'sudo -S -k -p \'\' "$@" <"${BECOME_PASSWORD_FILE}"' not in GATE
    assert "sudo_keepalive_pid" not in GATE
    assert "sudo -n -v" not in GATE
    assert "ansible-playbook -K" not in GATE

    assert 'step "Rofi parser checks on the installed Nitro version"' in GATE
    assert 'rofi -config roles/desktop/files/rofi-config.rasi -dump-config' in GATE
    assert 'rofi -no-config -theme roles/desktop/files/rofi-launcher.rasi -dump-theme' in GATE
    assert 'rofi -no-config -theme roles/desktop/files/rofi-hyperlab.rasi -dump-theme' in GATE

    assert 'step "Resolve the expected managed-create refusal"' in GATE
    assert 'run_sudo test -f /etc/privatestack/bricks/image_factory' in GATE
    assert "refusal_reason=unsealed-image" in GATE
    assert "refusal_reason=missing-image-factory-prerequisite" in GATE
    assert "refusal_pattern='image debian is not sealed'" in GATE
    assert "refusal_pattern='guest needs image_factory on this host first'" in GATE
    assert 'vm-create-expected-refusal.txt' in GATE
    assert 'grep -Fq "${refusal_pattern}"' in GATE
    assert 'install -m 0644 /dev/null /etc/privatestack/bricks/image_factory' not in GATE

    direct_sudo_calls = ("virsh", "cat", "find", "test")
    for command in direct_sudo_calls:
        assert f"run_sudo {command}" in GATE
    assert "\n  sudo virsh" not in GATE
    assert "\n  sudo cat" not in GATE
    assert "\n  sudo find" not in GATE

    assert 'PRIVATESTACK_BECOME_PASSWORD_FILE:-' in VERIFY
    assert 'become_args=(--become-password-file "${PRIVATESTACK_BECOME_PASSWORD_FILE}")' in VERIFY
    assert "sudo -n true" in VERIFY
    assert "become_args=(-K)" in VERIFY
    assert 'ansible-playbook "${become_args[@]}"' in VERIFY

    print("Nitro gate contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
