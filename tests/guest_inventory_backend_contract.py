#!/usr/bin/env python3
"""Narrow host-independent contract for runtime guest inventory backend."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "guest_agent_address.py"
PLAYBOOK_PATH = ROOT / "playbooks" / "vm-guest-inventory.yml"


def load_tool():
    spec = importlib.util.spec_from_file_location("guest_agent_address", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_refusal(function, *args: str) -> None:
    try:
        function(*args)
    except ValueError:
        return
    raise AssertionError(f"expected refusal for {args!r}")


def main() -> int:
    tool = load_tool()

    assert tool.LIBVIRT_URI == "qemu:///system"
    assert tool.domifaddr_argv(
        Path("/usr/bin/virsh"),
        "arch-dev-vfio",
    ) == [
        "/usr/bin/virsh",
        "-c",
        "qemu:///system",
        "domifaddr",
        "arch-dev-vfio",
        "--source",
        "agent",
        "--full",
    ]

    evidence = """\
 Name       MAC address          Protocol     Address
-------------------------------------------------------------------------------
 lo         00:00:00:00:00:00    ipv4         127.0.0.1/8
 enp1s0     52:54:00:d4:21:89    ipv4         10.10.3.198/24
 enp1s0     52:54:00:d4:21:89    ipv6         fe80::5054:ff:fed4:2189/64
"""
    assert (
        tool.resolve_address(evidence, "52:54:00:d4:21:89", "10.10.3.0/24")
        == "10.10.3.198"
    )
    expect_refusal(
        tool.resolve_address,
        evidence,
        "52:54:00:d4:21:89",
        "10.10.5.0/24",
    )
    expect_refusal(
        tool.resolve_address,
        evidence + "enp1s0 52:54:00:d4:21:89 ipv4 10.10.3.199/24\n",
        "52:54:00:d4:21:89",
        "10.10.3.0/24",
    )
    expect_refusal(
        tool.resolve_address,
        evidence,
        "not-a-mac",
        "10.10.3.0/24",
    )

    playbook = yaml.safe_load(PLAYBOOK_PATH.read_text(encoding="utf-8"))
    assert isinstance(playbook, list) and len(playbook) == 1
    play = playbook[0]
    assert play["hosts"] == "hypervisor"
    assert play["become"] is False
    assert play["gather_facts"] is False

    tasks = play["tasks"]
    names = [task["name"] for task in tasks]
    for name in (
        "Resolve the effective inventory publisher UID",
        "Require the physical operator to publish runtime inventory",
        "Resolve the unique managed guest address through QEMU Guest Agent",
        "Publish the strict runtime workstation inventory",
    ):
        assert name in names, name

    source = PLAYBOOK_PATH.read_text(encoding="utf-8")
    for token in (
        "guest_agent_address.py",
        "guest_inventory_effective_uid",
        "[workstations]",
        "BatchMode=yes",
        "StrictHostKeyChecking=yes",
        "UserKnownHostsFile=",
        "IdentitiesOnly=yes",
        "ansible_ssh_use_tty=false",
        "mode: '0600'",
    ):
        assert token in source, token

    assert "become: true" not in source.split("tasks:", 1)[0]
    print("runtime guest inventory backend contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
