#!/usr/bin/env python3
"""A check mode run of kvm_host is honest on a host that never had libvirt.

problems/kvm-host-check-mode-failed-without-libvirt.md: in the nested lab
host, `foundation.yml --check` stopped at "Enable socket activation":
libvirt was only "would be installed", so libvirtd.socket and
virtlogd.socket did not exist, and every later role went unpreviewed. The
admin's libvirt group, created by the same package, would have failed next.

This contract holds roles/kvm_host to the pattern of host_usbguard:

  1. the role looks for libvirtd.socket's unit after the package step and
     before its use;
  2. describe-only holds only in check mode without that unit, and then
     the run says what it could not preview and what an apply does;
  3. only the steps that need the packages (the sockets and the libvirt
     group) skip, and only then; KVM, the packages and the brick stamp do
     not.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "roles/kvm_host/tasks/main.yml"
UNIT = "/usr/lib/systemd/system/libvirtd.socket"
NEEDS_PACKAGES = ("Enable socket activation", "Let the admin drive virsh")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def when(task: dict) -> list[str]:
    value = task.get("when", [])
    return [value] if isinstance(value, str) else list(value)


def main() -> int:
    tasks = yaml.safe_load(TASKS.read_text())
    names = [task["name"] for task in tasks]
    for name in NEEDS_PACKAGES:
        require(name in names, f"kvm_host lost {name!r}")
        require("not kvm_host_describe_only | bool" in when(tasks[names.index(name)]),
                f"{name!r} runs in a check mode that has no libvirt to run against")

    require("Look for the libvirt socket unit" in names, "the role does not look for libvirt's socket unit")
    look = tasks[names.index("Look for the libvirt socket unit")]["ansible.builtin.stat"]
    require(look["path"] == UNIT, f"the role looks for {look['path']}, not {UNIT}")
    require(names.index("Install the headless KVM stack") < names.index("Look for the libvirt socket unit")
            < names.index("Enable socket activation"),
            "the unit is looked for before the package step or after its use")

    decide = tasks[names.index("Decide whether this run can only describe the libvirt services")]
    expression = decide["ansible.builtin.set_fact"]["kvm_host_describe_only"].replace(" ", "")
    require(expression == "{{ansible_check_modeandnotkvm_host_libvirt_unit.stat.exists}}",
            "describe-only is not limited to check mode without libvirt's unit")
    say = tasks[names.index("Say what a check mode run on a host without libvirt cannot preview")]
    message = say["ansible.builtin.debug"]["msg"]
    require(when(say) == ["kvm_host_describe_only | bool"] and "cannot be" in message
            and "libvirtd.socket" in message and "libvirt group" in message,
            "a check mode run without libvirt does not say what it could not preview")

    for name in ("Refuse to continue without KVM", "Install the headless KVM stack",
                 "Record that the kvm_host brick landed"):
        require(not any("describe_only" in condition for condition in when(tasks[names.index(name)])),
                f"{name!r} is skipped by describe-only")
    print("kvm_host check mode contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
