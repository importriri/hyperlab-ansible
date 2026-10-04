#!/usr/bin/env python3
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
GATE = (ROOT / "run-nitro-m9-cockpit-gate.sh").read_text()
VERIFY = (ROOT / "verify.sh").read_text()


def unsealed_example(spec_path: str, pattern: str) -> None:
    """An expected unsealed-image refusal must name an image that is really unsealed."""
    spec = yaml.safe_load((ROOT / spec_path).read_text())
    image = spec["image"]
    manifest = yaml.safe_load((ROOT / "images" / f"{image}.yml").read_text())
    assert manifest["status"] != "sealed", (
        f"{spec_path} uses image {image}, which is sealed now; pick an image that is not built")
    assert pattern == f"image {image} is not sealed", (spec_path, pattern)


def check_unsealed_examples() -> None:
    gate_spec = re.search(r"^SPEC=(\S+)$", GATE, re.MULTILINE).group(1)
    gate_pattern = re.search(r"refusal_pattern='(image \S+ is not sealed)'", GATE).group(1)
    unsealed_example(gate_spec, gate_pattern)

    suite = yaml.safe_load((ROOT / "tests/guest-refusals.yml").read_text())
    for task in suite[0]["tasks"]:
        argv = task.get("ansible.builtin.command", {}).get("argv", [])
        if "--spec" in argv:
            spec_path = argv[argv.index("--spec") + 1]
    checks = [task for task in suite[0]["tasks"] if "ansible.builtin.assert" in task]
    patterns = [re.search(r"'(image \S+ is not sealed)'", line).group(1)
                for task in checks for line in task["ansible.builtin.assert"]["that"]
                if "is not sealed" in line]
    assert len(patterns) == 1, patterns
    unsealed_example(spec_path, patterns[0])


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
    assert 'rofi -config roles/host_desktop_sway/files/rofi-config.rasi -dump-config' in GATE
    assert 'rofi -no-config -theme roles/host_desktop_sway/files/rofi-launcher.rasi -dump-theme' in GATE
    assert 'rofi -no-config -theme roles/host_desktop_sway/files/rofi-hyperlab.rasi -dump-theme' in GATE

    assert 'step "Resolve the expected managed-create refusal"' in GATE
    assert 'run_sudo test -f /etc/privatestack/bricks/image_factory' in GATE
    assert "refusal_reason=unsealed-image" in GATE
    assert "refusal_reason=missing-image-factory-prerequisite" in GATE
    assert "refusal_pattern='image parrot is not sealed'" in GATE
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
    assert 'mktemp "${runtime_dir}/privatestack-verify-become.XXXXXX"' in VERIFY
    assert 'chmod 0600 "${render_password_file}"' in VERIFY
    assert "IFS= read -r -s become_password" in VERIFY
    assert "unset become_password" in VERIFY
    assert "sudo -S -k -p '' -v" in VERIFY
    assert 'become_args=(--become-password-file "${render_password_file}")' in VERIFY
    assert "trap cleanup_render_password_file EXIT" in VERIFY
    assert "if sudo -v; then" not in VERIFY
    assert "become_args=(-K)" not in VERIFY
    assert 'ansible-playbook "${become_args[@]}"' in VERIFY

    check_unsealed_examples()

    print("Nitro gate contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
