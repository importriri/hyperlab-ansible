#!/usr/bin/python3
"""hyperlab-vfio-sleep-guard - libvirt qemu hook. Managed by hyperlab-ansible.

A Machine that holds a passed-through PCI device (the GPU) does not survive
the host suspending: the device loses its state and the guest hangs or
crashes. While such a domain runs, this hook keeps a systemd block
inhibitor through hyperlab-vfio-inhibit@<domain>.service, so logind refuses
suspend, hibernate and the lid and sleep keys. It starts the unit when the
domain has started and stops it when libvirt releases the domain.

libvirt passes the domain XML on stdin.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

DOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
DRY_RUN = os.environ.get("HYPERLAB_SLEEP_GUARD_DRY_RUN") == "1"


def holds_pci_device(xml_text: str) -> bool:
    root = ET.fromstring(xml_text)
    return any(node.get("type") == "pci" for node in root.findall("./devices/hostdev"))


def systemctl(verb: str, domain: str) -> None:
    argv = ["/usr/bin/systemctl", verb, "--no-block", f"hyperlab-vfio-inhibit@{domain}.service"]
    if DRY_RUN:
        print("ACTION " + " ".join(argv))
        return
    subprocess.run(argv, check=True)


def main(argv: list[str]) -> int:
    domain = argv[1] if len(argv) > 1 else ""
    phase = argv[2] if len(argv) > 2 else ""
    if phase not in ("started", "release") or not DOMAIN_RE.fullmatch(domain):
        return 0
    try:
        if phase == "release":
            systemctl("stop", domain)
        elif holds_pci_device(sys.stdin.read()):
            systemctl("start", domain)
        return 0
    except (OSError, ET.ParseError, subprocess.CalledProcessError) as exc:
        # The domain is already running; a failure here is reported, never
        # turned into a stopped Machine.
        print(f"hyperlab-vfio-sleep-guard: {domain}: {exc}", file=sys.stderr)
        return 0 if phase == "release" else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
