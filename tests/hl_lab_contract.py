#!/usr/bin/env python3
"""The nested lab host tool touches only hl-lab-* resources (ADR 0046).

  1. the domain template, with and without the install media, passes
     tools/lab/hl_lab_check.py; each way a definition could reach real
     hardware or another network is refused;
  2. every mutating virsh call goes through one guard that refuses a name
     without the hl-lab- prefix before virsh runs; create and destroy, run
     against a fake libvirt, only ever name hl-lab-* objects;
  3. start refuses, without calling virsh at all, unless the operator says
     they saw the host's loaded ruleset isolate the lab bridge;
  4. the lab network is the declared one, NAT, and the cloud-init seed
     carries only the lab's public key;
  5. nothing under tools/lab/ calls sudo.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/lab"))

import hl_lab  # noqa: E402
from hl_lab_check import problems  # noqa: E402


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def mutate(xml: str, old: str, new: str) -> str:
    require(xml.count(old) == 1, f"fixture text not found once: {old!r}")
    return xml.replace(old, new)


def check_definition() -> None:
    for with_iso in (False, True):
        xml = hl_lab.domain_xml(with_iso)
        require(problems(ET.fromstring(xml)) == [],
                f"the reviewed definition was refused ({with_iso=}): {problems(ET.fromstring(xml))}")
    require("cdrom" not in hl_lab.domain_xml(False), "install media attached without an ISO")
    xml = hl_lab.domain_xml(False)
    end = "  </devices>"
    refused = {
        "a passed-through PCI device": mutate(xml, end, '    <hostdev mode="subsystem" type="pci" managed="yes"><source><address domain="0" bus="1" slot="0" function="0"/></source></hostdev>\n' + end),
        "a passed-through USB device": mutate(xml, end, '    <hostdev mode="subsystem" type="usb"><source><vendor id="0x0408"/><product id="0xa061"/></source></hostdev>\n' + end),
        "USB redirection": mutate(xml, end, '    <redirdev bus="usb" type="spicevmc"/>\n' + end),
        "a shared folder": mutate(xml, end, '    <filesystem type="mount"><source dir="/home"/><target dir="home"/></filesystem>\n' + end),
        "shared host memory": mutate(xml, end, '    <shmem name="ivshmem"><model type="ivshmem-plain"/></shmem>\n' + end),
        "a SPICE agent channel": mutate(xml, end, '    <channel type="spicevmc"><target type="virtio" name="com.redhat.spice.0"/></channel>\n' + end),
        "a real block device": mutate(xml, end, '    <disk type="block" device="disk"><source dev="/dev/nvme0n1"/><target dev="vdb" bus="virtio"/></disk>\n' + end),
        "a volume of another pool": mutate(xml, 'pool="hl-lab-pool"', 'pool="default"'),
        "a file outside the lab pool": mutate(xml, end, '    <disk type="file" device="disk"><source file="/var/lib/libvirt/images/dev-01.qcow2"/><target dev="vdb" bus="virtio"/></disk>\n' + end),
        "a second network": mutate(xml, end, '    <interface type="network"><source network="dev"/></interface>\n' + end),
        "a product network": mutate(xml, 'network="hl-lab-testbed"', 'network="dev"'),
        "the host's TPM": mutate(xml, '<backend type="emulator" version="2.0"/>', '<backend type="passthrough"><device path="/dev/tpm0"/></backend>'),
        "firmware without Secure Boot": mutate(xml, '<feature enabled="yes" name="secure-boot"/>', '<feature enabled="no" name="secure-boot"/>'),
        "a CPU without VMX": mutate(xml, 'mode="host-passthrough"', 'mode="host-model"'),
        "a display on every address": mutate(xml, 'address="127.0.0.1"', 'address="0.0.0.0"'),
        "another name": mutate(xml, "<name>hl-lab-host</name>", "<name>dev-01</name>"),
    }
    for label, candidate in refused.items():
        require(problems(ET.fromstring(candidate)) != [], f"the checker accepted {label}")


class FakeLibvirt:
    """Answers virsh like an empty host, then like one with the lab defined."""

    def __init__(self, defined: bool):
        self.calls: list[list[str]] = []
        self.defined = defined

    def __call__(self, argv, **_):
        require(argv[:3] == ["virsh", "--connect", "qemu:///system"], f"virsh outside qemu:///system: {argv}")
        args = argv[3:]
        self.calls.append(args)
        out = ""
        if args[0] == "net-list":
            out = "default\ndev\nhl-lab-testbed\n" if self.defined else "default\ndev\n"
        elif args[0] == "pool-list":
            out = "default\nhl-lab-pool\n" if self.defined else "default\n"
        elif args[0] == "list":
            out = "dev-01\nhl-lab-host\n" if self.defined else "dev-01\n"
        elif args[0] == "vol-list":
            # The installed virsh has no --name for vol-list; it prints a
            # Name/Path table (problems/hl-lab-vol-list-name-option.md).
            if "--name" in args:
                return SimpleNamespace(returncode=1, stdout="",
                                       stderr="error: command 'vol-list' doesn't support option --name")
            out = " Name   Path\n--------------\n"
            if self.defined:
                out += (" hl-lab-host.qcow2    /var/lib/libvirt/images/hl-lab/hl-lab-host.qcow2\n"
                        " hl-lab-install.iso   /var/lib/libvirt/images/hl-lab/hl-lab-install.iso\n")
        elif args[0] == "dumpxml":
            out = hl_lab.domain_xml(True)
        return SimpleNamespace(returncode=0, stdout=out, stderr="")


def check_guard() -> None:
    for name in ("dev-01", "default", "hl-labx", "../hl-lab-x", "dev"):
        for args in (("destroy", name), ("net-destroy", name), ("vol-delete", "hl-lab-x", "--pool", name),
                     ("undefine", name, "--nvram")):
            recorded = []
            try:
                hl_lab.virsh(*args, run=lambda argv, _seen=recorded, **_: _seen.append(argv))
                require(False, f"virsh {args} was allowed")
            except hl_lab.Refused:
                require(recorded == [], f"virsh ran before the guard refused {args}")

    saved = (hl_lab.virsh, hl_lab.check_host, hl_lab.ensure_key, hl_lab.upload, hl_lab.seed_image)
    try:
        for defined, action in ((False, "create"), (True, "destroy")):
            fake = FakeLibvirt(defined)
            hl_lab.virsh = lambda *a, check=True, _fake=fake: saved[0](*a, check=check, run=_fake)
            hl_lab.check_host = lambda iso: []
            hl_lab.ensure_key = lambda: "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFixture hyperlab-lab-agent"
            hl_lab.upload = lambda path, volume, fmt="raw": hl_lab.virsh("vol-create-as", hl_lab.POOL, volume, "1")
            hl_lab.seed_image = lambda key, directory: Path(directory) / hl_lab.SEED_VOLUME
            if action == "create":
                with tempfile.NamedTemporaryFile(suffix=".iso") as iso:
                    hl_lab.create(Path(iso.name))
            else:
                hl_lab.destroy()
            mutating = [c for c in fake.calls if c[0] in hl_lab.MUTATING]
            require(mutating, f"{action} changed nothing")
            for call in mutating:
                named = [a for a in call[1:] if not a.startswith("-") and not a.startswith("/")
                         and a not in ("dir", "qcow2", "raw") and not re.fullmatch(r"\d+G?", a)]
                require(all(a.startswith("hl-lab-") for a in named),
                        f"{action} named a non-lab object: {call}")
            if action == "create":
                require(not any(c[0] == "start" or c[0] == "net-start" for c in fake.calls),
                        "create started something")
            else:
                deleted = [c[1] for c in fake.calls if c[0] == "vol-delete"]
                require(deleted == ["hl-lab-host.qcow2", "hl-lab-install.iso"],
                        f"destroy did not read the volume table: {deleted}")
    finally:
        (hl_lab.virsh, hl_lab.check_host, hl_lab.ensure_key, hl_lab.upload, hl_lab.seed_image) = saved


def check_start_needs_isolation() -> None:
    calls = []
    saved = hl_lab.virsh
    hl_lab.virsh = lambda *a, **k: calls.append(a)
    try:
        hl_lab.start(isolation_checked=False)
        require(False, "start ran without the isolation confirmation")
    except hl_lab.Refused as exc:
        require("virbr-hl-lab" in str(exc) and "nft list chain inet lab_isolation input" in str(exc),
                "the refusal does not say how to check the isolation")
    finally:
        hl_lab.virsh = saved
    require(calls == [], "start called virsh before refusing")


def check_network_and_seed() -> None:
    net = hl_lab.lab_network()
    xml = ET.fromstring(hl_lab.network_xml(net))
    require(xml.findtext("./name") == "hl-lab-testbed" and xml.find("./bridge").get("name") == "virbr-hl-lab",
            "the lab network is not the declared one")
    require(xml.find("./forward").get("mode") == "nat", "the lab network has no NAT")
    if subprocess.run(["sh", "-c", "command -v cloud-localds"], capture_output=True, check=False).returncode == 0:
        with tempfile.TemporaryDirectory() as temp:
            key = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIFixture hyperlab-lab-agent"
            hl_lab.seed_image(key, Path(temp))
            user_data = (Path(temp) / "user-data").read_text()
            require(key in user_data and "PRIVATE" not in user_data and "id_ed25519\"" not in user_data,
                    "the seed carries more than the public key")


def check_no_sudo() -> None:
    # sudo may appear in text shown to the operator, never as a command this
    # tool runs: not as an argv element, not at the start of a shell line.
    for path in (ROOT / "tools/lab").iterdir():
        if not path.is_file():
            continue
        text = path.read_text()
        require(re.search(r"""[\[(,]\s*["']sudo["']""", text) is None, f"{path.name} runs sudo")
        require(re.search(r"^\s*(exec\s+)?sudo\s", text, re.M) is None, f"{path.name} runs sudo")


def main() -> int:
    check_definition()
    check_guard()
    check_start_needs_isolation()
    check_network_and_seed()
    check_no_sudo()
    print("Nested lab host tool contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
