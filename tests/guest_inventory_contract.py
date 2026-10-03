#!/usr/bin/env python3
"""Host-independent contract for managed guest runtime inventory."""
from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
TOOL_PATH = ROOT / "tools" / "guest_agent_address.py"


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


def ed25519_line(seed: int = 7) -> str:
    blob = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes([seed]) * 32
    return "ssh-ed25519 " + base64.b64encode(blob).decode() + " root@dev-01"


def check_host_key_tool() -> None:
    spec = importlib.util.spec_from_file_location("guest_host_key", ROOT / "tools" / "guest_host_key.py")
    assert spec is not None and spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)

    line = ed25519_line()
    pinned = tool.known_hosts_line("10.10.3.131", line + "\n")
    assert pinned == "10.10.3.131 " + " ".join(line.split()[:2]), pinned
    expect_refusal(tool.known_hosts_line, "dev-01", line)
    expect_refusal(tool.known_hosts_line, "10.10.3.131", line + "\n" + ed25519_line(8))
    expect_refusal(tool.known_hosts_line, "10.10.3.131", "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB root@x")
    short = "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x10" + b"x" * 16).decode()
    expect_refusal(tool.known_hosts_line, "10.10.3.131", short)

    calls = []

    def agent(argv):
        assert argv[:5] == ["/usr/bin/virsh", "-c", "qemu:///system", "qemu-agent-command", "dev-01"]
        command = json.loads(argv[5])
        calls.append(command["execute"])
        if command["execute"] == "guest-file-open":
            assert command["arguments"] == {"path": "/etc/ssh/ssh_host_ed25519_key.pub", "mode": "r"}
            return json.dumps({"return": 5})
        if command["execute"] == "guest-file-read":
            return json.dumps({"return": {"count": len(line), "eof": True,
                                          "buf-b64": base64.b64encode(line.encode()).decode()}})
        return json.dumps({"return": {}})

    content = tool.read_guest_file(agent, Path("/usr/bin/virsh"), "dev-01", tool.HOST_KEY_PATH)
    assert content == line and calls == ["guest-file-open", "guest-file-read", "guest-file-close"]


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

    check_host_key_tool()

    playbook = yaml.safe_load(
        (ROOT / "playbooks" / "vm-guest-inventory.yml").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(playbook, list) and len(playbook) == 1
    play = playbook[0]
    assert play["hosts"] == "hypervisor"
    assert play["become"] is False, (
        "runtime guest inventory must remain unprivileged"
    )
    tasks = play["tasks"]
    names = [task["name"] for task in tasks]
    assert "Resolve the unique managed guest address through QEMU Guest Agent" in names
    assert "Publish the strict runtime workstation inventory" in names
    read = names.index("Read the guest SSH host key through QEMU Guest Agent")
    pin = names.index("Pin the guest SSH host key for strict checking")
    resolve = names.index("Resolve the unique managed guest address through QEMU Guest Agent")
    assert resolve < read < pin < names.index("Build the strict runtime workstation inventory record")
    pin_task = tasks[pin]["ansible.builtin.known_hosts"]
    assert pin_task["state"] == "present" and pin_task["hash_host"] is False
    assert pin_task["name"] == "{{ guest_inventory_address.stdout }}"
    assert "ssh-keyscan" not in (ROOT / "playbooks" / "vm-guest-inventory.yml").read_text(), (
        "a host key is never accepted from the network"
    )

    rendered_source = (ROOT / "playbooks" / "vm-guest-inventory.yml").read_text(
        encoding="utf-8"
    )
    assert "guest_agent_address.py" in rendered_source
    assert "guest_inventory_effective_uid" in rendered_source
    assert "[workstations]" in rendered_source
    assert "StrictHostKeyChecking=yes" in rendered_source
    assert "UserKnownHostsFile=" in rendered_source
    assert "IdentitiesOnly=yes" in rendered_source
    assert "ansible_ssh_use_tty=false" in rendered_source, (
    "runtime guest inventory must disable SSH pseudo-TTY allocation"
)
    assert "mode: '0600'" in rendered_source
    vm_source = (
        ROOT
        / "tools"
        / "hyperlabctl"
        / "hyperlabctl"
        / "commands"
        / "vm.py"
    ).read_text(encoding="utf-8")

    assert 'sub.add_parser(\n            "inventory"' in vm_source
    assert 'target_choices("spec", repo_root)' in vm_source
    assert "playbooks/vm-guest-inventory.yml" in vm_source
    assert '"guest_spec=%s" % args.spec' in vm_source
    assert '"-K"' not in vm_source

    opener_source = (
        ROOT
        / "tools"
        / "hyperlabctl"
        / "hyperlabctl"
        / "commands"
        / "open.py"
    ).read_text(encoding="utf-8")

    assert "def _runtime_inventory(ctx, domain):" in opener_source
    assert (
        "return _publish_runtime_inventory(ctx, domain, inventory)"
        in opener_source
    )
    assert (
        "runtime_inventory = _runtime_inventory(ctx, domain)"
        in opener_source
    )
    assert "stat.S_ISLNK" in opener_source
    assert "stat.S_ISREG" in opener_source
    assert "stat.S_IMODE(info.st_mode) != 0o600" in opener_source

    publish = opener_source.split(
        "def _publish_runtime_inventory(ctx, domain, inventory):",
        1,
    )[1].split(
        "\n\ndef _runtime_inventory(ctx, domain):",
        1,
    )[0]

    assert '_executable("hyperlabctl")' in publish
    assert '"vm",' in publish
    assert '"inventory",' in publish
    assert '"--repo",' in publish
    assert "ansible-playbook" not in publish

    registry_source = (
        ROOT
        / "tools"
        / "hyperlabctl"
        / "hyperlabctl"
        / "registry.py"
    ).read_text(encoding="utf-8")

    inventory_action = registry_source.split(
        '"id": "vm.inventory"',
        1,
    )[1].split(
        "\n    },",
        1,
    )[0]

    assert (
        '["hyperlabctl", "vm", "inventory", "{spec}"]'
        in inventory_action
    )
    assert '"privileged": False' in inventory_action
    assert '"requires": None' in inventory_action

    print("managed guest inventory contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
