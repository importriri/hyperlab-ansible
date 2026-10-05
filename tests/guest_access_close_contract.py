#!/usr/bin/env python3
"""A Machine's first provisioning ends by closing its access (milestone 10).

The last provisioning step, playbooks/guest-close-access.yml, must:

  1. allow the QEMU Guest Agent exactly the calls HyperLab and libvirt use
     (decided 2026-10-04) and never guest-exec or a file write, in the
     comma-separated allow-rpcs form qemu-ga reads, and restart the agent
     while become still needs no password;
  2. remove cloud-init's NOPASSWD rule only when the account has a usable
     password, after a visudo-validated rule lets the administrator group
     sudo with that password, as the last task that uses become, and then
     prove sudo asks for the password;
  3. prove from the host that guest-exec is disabled and that the SSH host
     key read through the agent still matches the pinned one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/guest_access_close"
EXPECTED_RPCS = [
    "guest-sync-delimited", "guest-sync", "guest-ping", "guest-info", "guest-get-host-name",
    "guest-network-get-interfaces", "guest-shutdown", "guest-file-open", "guest-file-read",
    "guest-file-close",
]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    rpcs = defaults["guest_access_close_agent_rpcs"]
    require(rpcs == EXPECTED_RPCS, f"the agent allowlist changed: {rpcs}")
    for forbidden in ("guest-exec", "guest-exec-status", "guest-file-write", "guest-set-user-password",
                      "guest-ssh-add-authorized-keys"):
        require(forbidden not in rpcs, f"{forbidden} is allowed")
    # Every call HyperLab makes through the agent is on the list.
    host_key = (ROOT / "tools/guest_host_key.py").read_text()
    for call in ("guest-file-open", "guest-file-read", "guest-file-close"):
        require(call in host_key and call in rpcs, f"{call} is used but not allowed")
    address = (ROOT / "tools/guest_agent_address.py").read_text()
    require('"--source",\n        "agent"' in address and "guest-network-get-interfaces" in rpcs,
            "the agent address lookup would be refused")

    tasks_text = (ROLE / "tasks/main.yml").read_text()
    require("allow-rpcs={{ guest_access_close_agent_rpcs | join(',') }}" in tasks_text
            and "[general]" in tasks_text, "the agent configuration is not in the form qemu-ga reads")
    tasks = yaml.safe_load(tasks_text)
    names = [task["name"] for task in tasks]
    restart = names.index("Restart the agent on its restricted configuration")
    require(tasks[restart].get("ansible.builtin.meta") == "flush_handlers",
            "the agent restart waits for the end of the play, after sudo needs a password")
    block_task = next(task for task in tasks if task["name"] == "End passwordless sudo once the account has a password")
    require(names.index(block_task["name"]) > restart, "sudo closes before the agent restarts")
    require(block_task["when"] == "guest_access_close_has_password",
            "NOPASSWD is removed even when the account has no password")
    block = block_task["block"]
    admin = next(i for i, task in enumerate(block) if task["name"] == "Let the administrator group sudo with its password")
    remove = next(i for i, task in enumerate(block) if task["name"] == "Remove cloud-init's passwordless sudo rule")
    require(block[admin]["ansible.builtin.copy"].get("validate") == "visudo -cf %s" and admin < remove,
            "the password rule is not validated before NOPASSWD goes")
    require(all(task.get("become") is False for task in block[remove + 1:])
            and all(task.get("become") is False for task in tasks[names.index(block_task["name"]) + 1:]),
            "a task after the NOPASSWD removal still needs passwordless become")
    proof = block[remove + 1]
    require(proof["ansible.builtin.command"]["argv"] == ["sudo", "-n", "true"]
            and proof["failed_when"] == "guest_access_close_sudo.rc == 0",
            "nothing proves sudo now asks for the password")

    playbook = yaml.safe_load((ROOT / "playbooks/guest-close-access.yml").read_text())
    host_tasks = playbook[1]["tasks"]
    exec_task = next(task for task in host_tasks if task["name"] == "Refuse unless guest-exec is disabled")
    require("guest-exec" in " ".join(exec_task["ansible.builtin.command"]["argv"])
            and "guest_close_exec.rc == 0" in exec_task["failed_when"], "guest-exec is not proven disabled")
    require(any("guest_host_key.py" in " ".join(task.get("ansible.builtin.command", {}).get("argv", []))
                for task in host_tasks), "the host key is not read again after the restriction")
    require(any("ssh-keygen" in task.get("ansible.builtin.command", {}).get("argv", [""])[0]
                for task in host_tasks), "the re-read key is not compared with the pinned one")
    print("Guest access close contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
