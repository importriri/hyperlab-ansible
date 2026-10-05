#!/usr/bin/env python3
"""The AppArmor boot entry is the VFIO entry plus AppArmor, and not the default.

ADR 0037 needs AppArmor active in the kernel, which only the kernel command
line can do (CONFIG_LSM on Nitro's linux-hardened leaves it out). The entry
that enables it must be the reviewed VFIO entry with one added lsm= group
that keeps the kernel's own LSM order and inserts apparmor, and the loader
default must stay the plain VFIO entry until Nitro has proved it: a failed
boot is then one reboot away from the old one.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    profiles = {p["file"]: p for p in yaml.safe_load((ROOT / "roles/vfio_boot/defaults/main.yml").read_text())["vfio_boot_profiles"]}
    vfio = profiles["Arch-Linux-Hardened-Vfio.conf"]
    armored = profiles["Arch-Linux-Hardened-Vfio-AppArmor.conf"]
    require(armored.get("bind_vfio_devices") is True, "the AppArmor entry lost the VFIO binding")
    require(armored["option_groups"][:-1] == vfio["option_groups"],
            "the AppArmor entry differs from the VFIO entry in more than AppArmor")
    lsm = armored["option_groups"][-1]
    require(lsm == "lsm=landlock,lockdown,yama,integrity,apparmor,bpf",
            f"the AppArmor entry's LSM list is not the kernel's order with apparmor: {lsm}")
    require(not any("lsm=" in group for group in vfio["option_groups"]), "the fallback entry changed its LSMs")
    tasks = (ROOT / "roles/vfio_boot/tasks/main.yml").read_text()
    require("line: default Arch-Linux-Hardened-Vfio.conf" in tasks,
            "the loader default moved before Nitro proved the AppArmor entry")
    print("AppArmor boot contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
