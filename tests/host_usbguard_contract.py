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
    allow_contract()
    print("Host USBGuard contract: OK")
    return 0


def allow_contract() -> None:
    """Allowing one blocked device from the shell (ADR 0038).

    4. every refusal -- a malformed port or scope, a device that is not
       blocked, a configured keyboard or mouse interface, anything but exactly
       one blocked USBGuard device at that port, or one whose interfaces
       include class 03 -- comes before the single allow-device call;
    5. only permanent adds -p, and sysfs is read back afterwards;
    6. it runs from its own playbook, as root, and the registry resolves to it.
    """
    playbook = yaml.safe_load((ROOT / "playbooks/host-usb-allow.yml").read_text())
    play = playbook[0]
    include = play["tasks"][0]["ansible.builtin.include_role"]
    require(play["hosts"] == "hypervisor" and play["become"] is True
            and include == {"name": "host_usbguard", "tasks_from": "allow.yml"},
            "allowing a device does not run the role's allow tasks as root")

    tasks = yaml.safe_load((ROLE / "tasks/allow.yml").read_text())
    names = [task["name"] for task in tasks]
    for task in tasks:
        for condition in task.get("ansible.builtin.assert", {}).get("that", []):
            # An unquoted "a: b" in a condition parses as a mapping, which
            # would never be evaluated as the check it reads as.
            require(isinstance(condition, str), f"{task['name']}: a condition is not a string")
    allows = [index for index, task in enumerate(tasks)
              if "ansible.builtin.command" in task
              and "allow-device" in str(task["ansible.builtin.command"]["argv"])]
    require(len(allows) == 1, "allow-device must be called exactly once")
    allow = allows[0]
    refusals = [index for index, name in enumerate(names) if name.startswith("Refuse")]
    require(len(refusals) == 4 and max(refusals) < allow,
            "a refusal comes after allow-device, or one is missing")

    def that(prefix: str) -> list[str]:
        return next(task for task in tasks if task["name"].startswith(prefix))["ansible.builtin.assert"]["that"]

    shape = that("Refuse a malformed port or scope")
    require("host_usb_allow_port is match('^[0-9]+-[0-9]+([.][0-9]+)*$')" in shape
            and "host_usb_allow_scope in ['once', 'permanent']" in shape,
            "the port or scope is not validated")
    require(names.index("Refuse a malformed port or scope") == 0, "a task runs before the inputs are checked")
    require(that("Refuse a device that is not blocked") == [
        "host_usbguard_allow_before.content | b64decode | trim == '0'"], "an allowed device is not refused")
    sysfs_hid = next(task for task in tasks if task["name"].startswith(
        "Refuse a device whose configured interfaces include a keyboard or mouse"))
    require("select('equalto', '03')" in sysfs_hid["vars"]["host_usbguard_allow_hid_interfaces"],
            "a configured keyboard or mouse interface is not refused")
    exact = that("Refuse unless exactly one blocked device")
    require("host_usbguard_allow_matches | length == 1" in exact,
            "more than one USBGuard device at the port can be allowed")
    require("host_usbguard_allow_matches[0] is match('^[0-9]+: block ')" in exact,
            "a device USBGuard does not block can be allowed")
    require("host_usbguard_allow_matches[0] is search('with-interface ')" in exact
            and "host_usbguard_allow_interfaces is not search('(^|[ {])03:')" in exact,
            "a blocked keyboard or mouse can be allowed")
    listing = names.index("Ask USBGuard which device is at that port")
    require(listing < names.index("Refuse unless exactly one blocked device that is not a keyboard "
                                  "or mouse is at that port") < allow,
            "the USBGuard device is not checked before it is allowed")

    argv = tasks[allow]["ansible.builtin.command"]["argv"]
    require("['-p'] if host_usb_allow_scope == 'permanent' else []" in argv,
            "only a permanent allow may add a rule")
    require('via-port "' in tasks[allow]["vars"]["host_usbguard_allow_id"],
            "the device id is not taken from the line at that port")
    after = names.index("Read the kernel's authorization back")
    require(after > allow and tasks[after]["until"]
            == "host_usbguard_allow_after.content | b64decode | trim == '1'",
            "the allow is not verified in sysfs")

    sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))
    from hyperlabctl.registry import by_id
    action = by_id("usb.allow")
    require(action["command"][:3] == ["ansible-playbook", "playbooks/host-usb-allow.yml", "-K"]
            and action["privileged"] is True,
            "the registry does not resolve usb.allow to this playbook")


if __name__ == "__main__":
    sys.exit(main())
