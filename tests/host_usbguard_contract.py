#!/usr/bin/env python3
"""The host blocks new USB devices only after it allows the attached ones.

ADR 0038 (accepted 2026-10-05): generate the policy from the devices
attached now, then turn on the implicit block. This contract holds the
order and the safeguards of roles/host_usbguard:

  1. the policy is generated only when none exists, so a reviewed policy is
     never overwritten, and it must allow exactly as many devices as the
     kernel reports before it is installed, root-only;
  2. only then does the daemon get the implicit block, apply the policy to
     present and inserted devices, keep the controllers, and listen to root
     alone over IPC;
  3. the daemon starts after both, and the role runs from its own playbook.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/host_usbguard"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text())
    names = [task["name"] for task in tasks]
    generate = tasks[names.index("Generate the policy from the devices attached now")]
    block = names.index("Block every device the policy does not allow")
    start = names.index("Start USBGuard now and at every boot")
    require(names.index("Generate the policy from the devices attached now") < block < start,
            "the implicit block or the daemon comes before the policy")
    require("not host_usbguard_existing.stat.exists" in generate["when"],
            "an existing policy can be overwritten")
    inner = {task["name"]: task for task in generate["block"]}
    guard = inner["Refuse a generated policy that would block an attached device"]["ansible.builtin.assert"]["that"]
    require("host_usbguard_allows | length == host_usbguard_devices | length" in guard,
            "a generated policy missing a device can be installed")
    install = inner["Install the generated policy"]["ansible.builtin.copy"]
    require(install["mode"] == "0600" and install["owner"] == "root", "the policy is not root-only")
    order = [task["name"] for task in generate["block"]]
    require(order.index("Refuse a generated policy that would block an attached device")
            < order.index("Install the generated policy"), "the policy is installed before it is checked")

    settings = yaml.safe_load((ROLE / "defaults/main.yml").read_text())["host_usbguard_settings"]
    require(settings == {
        "RuleFile": "/etc/usbguard/rules.conf",
        "ImplicitPolicyTarget": "block",
        "PresentDevicePolicy": "apply-policy",
        "PresentControllerPolicy": "keep",
        "InsertedDevicePolicy": "apply-policy",
        "IPCAllowedUsers": "root",
        "IPCAllowedGroups": "",
    }, f"the daemon settings changed: {settings}")

    playbook = yaml.safe_load((ROOT / "playbooks/host-usbguard.yml").read_text())
    require(playbook[0]["become"] is True and playbook[0]["roles"][-1] == "host_usbguard",
            "the policy does not run from its own playbook")
    print("Host USBGuard contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
