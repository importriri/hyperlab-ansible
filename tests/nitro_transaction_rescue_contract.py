#!/usr/bin/env python3

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

OUTTREE = (
    ROOT / "roles/nitro_sense/tasks/out-of-tree.yml"
).read_text(encoding="utf-8")

FAN_ASSERTION = (
    "    - name: Require fan hardware and broker observation to agree"
)

RESCUE = (
    "\n  rescue:\n"
    "    - name: Roll back the failed platform-driver transaction\n"
    "      ansible.builtin.include_tasks: rollback.yml\n"
)

REPORT = (
    "    - name: Report the restored driver after a failed transaction"
)

SUCCESS = (
    "- name: Remove the superseded managed DKMS version "
    "after successful transition"
)


assert OUTTREE.count(FAN_ASSERTION) == 1
assert OUTTREE.count(RESCUE) == 1
assert OUTTREE.count(REPORT) == 1
assert OUTTREE.count(SUCCESS) == 1

fan_pos = OUTTREE.index(FAN_ASSERTION)
rescue_pos = OUTTREE.index(RESCUE)
report_pos = OUTTREE.index(REPORT)
success_pos = OUTTREE.index(SUCCESS)

assert fan_pos < rescue_pos < report_pos < success_pos

normal_tail = OUTTREE[
    fan_pos + len(FAN_ASSERTION):
    rescue_pos
]

assert "Roll back the failed platform-driver transaction" not in normal_tail

rescue_body = OUTTREE[
    rescue_pos:
    success_pos
]

assert "include_tasks: rollback.yml" in rescue_body
assert "ansible.builtin.fail:" in rescue_body

print("Nitro transaction rescue contract: OK")
