#!/usr/bin/env python3
"""QEMU confinement is either real or recorded as a gap, never assumed.

On Nitro libvirt runs with the DAC model only and every QEMU process is the
same user (problems/qemu-processes-share-one-identity.md); ADR 0037 is the
pending decision. This contract keeps the repository honest about it:

  1. while the roadmap item is open, the gap is documented and the ADR is
     still proposed;
  2. the moment the item is checked, the repository must actually configure
     a MAC security driver for libvirt and enable it in the kernel command
     line it manages, and the domain template must not opt out of it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def repository_text(*globs: str) -> str:
    return "\n".join(path.read_text(errors="replace") for pattern in globs
                     for path in sorted(ROOT.glob(pattern)) if path.is_file())


def main() -> int:
    roadmap = (ROOT / "docs/roadmap.md").read_text()
    item = re.search(r"^- \[( |x)\] sVirt/AppArmor confinement of every QEMU process", roadmap, re.M)
    require(item is not None, "the confinement item left the roadmap")
    adr = (ROOT / "docs/adr/0037-qemu-process-confinement.md").read_text()
    roles = repository_text("roles/**/*.yml", "roles/**/*.j2", "roles/**/files/*")
    template = (ROOT / "roles/guest/templates/domain.xml.j2").read_text()
    require('model="none"' not in template and "model='none'" not in template,
            "the domain template opts out of the security driver")
    if item.group(1) == " ":
        require((ROOT / "problems/qemu-processes-share-one-identity.md").is_file(),
                "the confinement gap is open but not documented")
        require("Status: proposed" in adr, "the confinement gap is open but ADR 0037 is not proposed")
    else:
        require(re.search(r'security_driver\s*=\s*"?(apparmor|selinux)', roles) is not None,
                "confinement is claimed but libvirt has no MAC security driver")
        require("apparmor" in roles and re.search(r"lsm=[^ \"']*apparmor", roles) is not None,
                "confinement is claimed but the kernel command line does not enable AppArmor")
    print("QEMU confinement contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
