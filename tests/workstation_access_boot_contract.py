#!/usr/bin/env python3
# The workstation access role must retire only the reviewed stale Arch cloud gate.

from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "roles/workstation_access/tasks/main.yml"

UNIT = "/etc/systemd/system/pacman-init.service"
ENABLEMENT = "/etc/systemd/system/multi-user.target.wants/pacman-init.service"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def named(tasks: list[dict], name: str) -> dict:
    matches = [
        task
        for task in tasks
        if isinstance(task, dict) and task.get("name") == name
    ]
    require(len(matches) == 1, f"expected exactly one task named {name!r}")
    return matches[0]


def main() -> int:
    source = TASKS.read_text(encoding="utf-8")
    tasks = yaml.safe_load(source)

    unit_probe = named(tasks, "Inspect stale Arch cloud first-boot Pacman unit")
    require(
        unit_probe["ansible.builtin.stat"] == {"path": UNIT, "follow": False},
        "workstation_access must inspect the exact unit without following redirects",
    )

    link_probe = named(tasks, "Inspect stale Arch cloud Pacman enablement")
    require(
        link_probe["ansible.builtin.stat"] == {
            "path": ENABLEMENT,
            "follow": False,
        },
        "workstation_access must inspect the exact enablement without following redirects",
    )

    pre_read = named(tasks, "Refuse an unsafe Pacman first-boot unit before reading it")
    pre_read_text = yaml.safe_dump(pre_read, sort_keys=False, width=4096)
    for marker in ("stat.isreg", "stat.islnk", "stat.pw_name", "stat.gr_name", "0644"):
        require(marker in pre_read_text, f"unit pre-read guard lost: {marker}")

    ownership = named(
        tasks,
        "Check whether the stale Pacman first-boot unit is package-owned",
    )
    require(
        ownership["ansible.builtin.command"]["argv"]
        == ["/usr/bin/pacman", "-Qo", UNIT],
        "package ownership probe drifted",
    )
    require(
        ownership["check_mode"] is False,
        "package ownership must still be inspected in check mode",
    )

    ownership_refusal = named(
        tasks,
        "Refuse to alter a package-owned Pacman first-boot unit",
    )
    require(
        "workstation_access_pacman_init_package_owner.rc == 1"
        in str(ownership_refusal["ansible.builtin.assert"]["that"]),
        "package-owned units are no longer refused",
    )

    link_refusal = named(
        tasks,
        "Refuse an orphaned or redirected Pacman first-boot enablement",
    )
    link_refusal_text = yaml.safe_dump(link_refusal, sort_keys=False, width=4096)
    for marker in ("stat.islnk", "stat.lnk_source", UNIT):
        require(marker in link_refusal_text, f"enablement refusal lost guard: {marker}")

    keyring = named(tasks, "Refuse an incomplete or redirected Pacman keyring")
    keyring_text = yaml.safe_dump(keyring, sort_keys=False, width=4096)
    for marker in ("stat.exists", "stat.isreg", "stat.islnk", "stat.size", "root"):
        require(marker in keyring_text, f"keyring guard lost: {marker}")
    for path in (
        "/etc/pacman.d/gnupg/pubring.gpg",
        "/etc/pacman.d/gnupg/trustdb.gpg",
    ):
        require(path in source, f"missing keyring evidence path: {path}")

    unit_guard = named(tasks, "Refuse an unexpected stale Pacman first-boot unit")
    guard_text = yaml.safe_dump(unit_guard, sort_keys=False, width=4096)
    for marker in (
        "ConditionFirstBoot=yes",
        "After=time-sync[.]target",
        "Before=sshd[.]service",
        "Type=oneshot",
        "RemainAfterExit=yes",
        "ExecStart=/usr/bin/pacman-key --init",
        "ExecStart=/usr/bin/pacman-key --populate",
        "WantedBy=multi-user[.]target",
    ):
        require(marker in guard_text, f"missing reviewed unit marker: {marker}")

    retirement = named(tasks, "Retire stale Arch cloud Pacman first-boot enablement")
    require(
        retirement["ansible.builtin.file"] == {
            "path": ENABLEMENT,
            "state": "absent",
        },
        "retirement must remove only the exact multi-user enablement link",
    )
    require(
        "workstation_access_pacman_init_enablement.stat.exists"
        in str(retirement["when"]),
        "retirement must be conditional on the observed enablement",
    )

    require(
        not any(
            isinstance(task, dict)
            and task.get("ansible.builtin.file", {}).get("path") == UNIT
            and task.get("ansible.builtin.file", {}).get("state") == "absent"
            for task in tasks
        ),
        "workstation_access must preserve the pacman-init unit file",
    )

    reload_task = named(
        tasks,
        "Reload systemd after retiring stale Pacman first-boot enablement",
    )
    require(
        reload_task["ansible.builtin.systemd_service"] == {"daemon_reload": True},
        "systemd manager reload must be scoped to the retirement transaction",
    )

    for forbidden in (
        "systemd-time-wait-sync.service",
        "systemd-timesyncd.service",
        "time-sync.target.wants",
        "systemctl disable systemd",
        "mitigations=off",
    ):
        require(
            forbidden not in source,
            f"workstation_access must not weaken an unrelated boundary: {forbidden}",
        )

    print("workstation access stale pacman-init contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
