#!/usr/bin/env python3

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

configure = (
    ROOT / "roles/nitro_sense/tasks/configure.yml"
).read_text(encoding="utf-8")

outtree = (
    ROOT / "roles/nitro_sense/tasks/out-of-tree.yml"
).read_text(encoding="utf-8")

helper = (
    ROOT / "roles/nitro_sense/templates/nitro-sense-apply.sh.j2"
).read_text(encoding="utf-8")

docs = (
    ROOT / "docs/nitro-sense.md"
).read_text(encoding="utf-8")

procedure = (
    ROOT / "docs/nitro-sense-procedure.md"
).read_text(encoding="utf-8")


assert configure.count(
    "- name: Reconcile the effective Nitro policy before validation"
) == 1

reconcile = configure.split(
    "- name: Reconcile the effective Nitro policy before validation",
    1,
)[1].split("\n- name:", 1)[0]

assert "/usr/bin/bash" in reconcile
assert '"{{ nitro_sense_apply_script }}"' in reconcile
assert "changed_when: false" in reconcile
assert "not ansible_check_mode" in reconcile
assert "nitro_sense_use_out_of_tree | bool" in reconcile

assert "- name: Read the applied battery limiter" not in configure
assert "- name: Require the configured battery limiter" not in configure

assert configure.count(
    "- name: Read the reconciled battery limiter"
) == 1

assert configure.count(
    "- name: Require battery hardware and broker observation to agree"
) == 1

assert (
    "nitro_sense_control_status_data.status.runtime.battery_limiter"
    in configure
)

assert "- name: Require the configured fan setting" not in outtree

assert outtree.count(
    "- name: Require fan hardware and broker observation to agree"
) == 1

assert "nitro_sense_control_status_data.status.runtime.fan" in outtree

assert "persistent_state_path=" in helper
assert 'fan_value=${item#fan=}' in helper
assert 'battery_limiter_value=${item#battery=}' in helper
assert 'led_per_zone_value=${item#rgb=}' in helper
assert 'write_and_verify "$fan_path" "$fan_value"' in helper
assert (
    'write_and_verify "$battery_limiter_path" '
    '"$battery_limiter_value"'
    in helper
)

assert "A `Runtime` change is intentionally temporary" in docs
assert "single authority" in docs
assert "broker's observation" in docs

assert "Runtime-only drift" in procedure
assert "`changed=0` idempotence gate" in procedure

print("Nitro effective-policy reconciliation contract: OK")
