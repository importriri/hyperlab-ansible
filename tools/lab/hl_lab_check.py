#!/usr/bin/env python3
"""Refuse a nested lab host definition that reaches real hardware (ADR 0046).

The lab host is where host-level changes are tried with root, so it must be
a VM and nothing more: no passed-through or redirected device, no shared
folder or memory, no SPICE agent channel, disks only as volumes of its own
pool, an emulated TPM 2.0, Secure Boot capable firmware, its own network
only, a CPU that can run nested Machines, and a display that listens on
loopback or a socket (the rule every Machine follows,
tools/guest_xml_contract.py).

Usage: hl_lab_check.py DOMAIN.xml   (exit 0 when it passes, 1 otherwise)
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from guest_xml_contract import graphics_exposure  # noqa: E402

NAME = "hl-lab-host"
NETWORK = "hl-lab-testbed"
POOL = "hl-lab-pool"
POOL_DIR = "/var/lib/libvirt/images/hl-lab/"


def secure_boot_firmware(root: ET.Element) -> bool:
    os_node = root.find("./os")
    if os_node is None:
        return False
    loader = os_node.find("./loader")
    if loader is not None and loader.get("secure") == "yes":
        return True
    feature = os_node.find("./firmware/feature[@name='secure-boot']")
    return os_node.get("firmware") == "efi" and feature is not None and feature.get("enabled") == "yes"


def problems(root: ET.Element) -> list[str]:
    found = []
    if root.findtext("./name") != NAME:
        found.append(f"the domain is not named {NAME}")
    devices = root.find("./devices")
    if devices is None:
        return found + ["the domain has no devices section"]
    for tag, why in (("hostdev", "a host device is passed through"),
                     ("redirdev", "USB is redirected"),
                     ("filesystem", "a host folder is shared"),
                     ("smartcard", "a smartcard is passed"),
                     ("shmem", "host memory is shared")):
        if devices.find(tag) is not None:
            found.append(why)
    for channel in devices.findall("./channel"):
        if channel.get("type") == "spicevmc":
            found.append("a SPICE agent channel is present")
    for disk in devices.findall("./disk"):
        source = disk.find("./source")
        if disk.get("type") == "volume":
            if source is None or source.get("pool") != POOL or not str(source.get("volume", "")).startswith("hl-lab-"):
                found.append(f"a disk is not a volume of {POOL}")
        elif disk.get("type") == "file":
            # libvirt may resolve a volume to its file in the live definition.
            if source is None or not str(source.get("file", "")).startswith(POOL_DIR):
                found.append(f"a disk file lies outside {POOL_DIR}")
        else:
            found.append("a disk is neither a lab volume nor a file in the lab pool (a real block device?)")
    for controller in devices.findall("./controller[@type='usb']"):
        if controller.get("model") not in (None, "qemu-xhci", "none"):
            found.append("an unexpected USB controller model")
    interfaces = devices.findall("./interface")
    if len(interfaces) != 1 or interfaces[0].get("type") != "network" \
            or interfaces[0].find("./source") is None \
            or interfaces[0].find("./source").get("network") != NETWORK:
        found.append(f"the only network must be {NETWORK}")
    tpms = devices.findall("./tpm")
    if len(tpms) != 1 or tpms[0].find("./backend") is None \
            or tpms[0].find("./backend").get("type") != "emulator" \
            or tpms[0].find("./backend").get("version") != "2.0":
        found.append("the TPM must be one emulated TPM 2.0")
    if not secure_boot_firmware(root):
        found.append("the firmware is not Secure Boot capable")
    cpu = root.find("./cpu")
    if cpu is None or cpu.get("mode") != "host-passthrough":
        found.append("the CPU is not host-passthrough, so nested KVM would not work")
    found += graphics_exposure(root)
    return found


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[-1], file=sys.stderr)
        return 2
    try:
        root = ET.parse(argv[1]).getroot()
    except (OSError, ET.ParseError) as exc:
        print(f"lab host definition cannot be read: {exc}", file=sys.stderr)
        return 2
    found = problems(root)
    if found:
        print("lab host definition refused:", file=sys.stderr)
        for problem in found:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print("lab host definition: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
