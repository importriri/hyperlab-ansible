#!/usr/bin/env python3
"""The host does not suspend while a Machine holds a passed-through device.

  1. the libvirt hook starts the inhibitor unit for a domain with a PCI
     hostdev once it has started, starts nothing for any other domain, stops
     the unit when libvirt releases the domain, ignores other phases and
     names it does not accept, and reports unreadable XML at start;
  2. the unit holds a block inhibitor for sleep, idle, the suspend and
     hibernate keys and the lid (logind ignores sleep inhibitors for the lid
     by default), naming the domain;
  3. libvirt is restarted for the hook only with no domain running.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/host_sleep_guard"
HOOK = ROLE / "files/hyperlab-vfio-sleep-guard.py"
VFIO = ("<domain><name>dev-01</name><devices><hostdev mode='subsystem' type='pci' managed='yes'>"
        "<source><address domain='0x0000' bus='0x01' slot='0x00' function='0x0'/></source></hostdev>"
        "</devices></domain>")
PLAIN = "<domain><name>srv-01</name><devices><disk type='file' device='disk'/></devices></domain>"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def hook(domain: str, phase: str, xml: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, HYPERLAB_SLEEP_GUARD_DRY_RUN="1")
    return subprocess.run([sys.executable, str(HOOK), domain, phase], input=xml, capture_output=True,
                          text=True, env=env, check=False)


def main() -> int:
    started = hook("dev-01", "started", VFIO)
    require(started.returncode == 0 and started.stdout.strip()
            == "ACTION /usr/bin/systemctl start --no-block hyperlab-vfio-inhibit@dev-01.service",
            f"a VFIO Machine did not take the inhibitor: {started.stdout!r} {started.stderr!r}")
    plain = hook("srv-01", "started", PLAIN)
    require(plain.returncode == 0 and plain.stdout == "", "a Machine without a passed-through device inhibited sleep")
    released = hook("dev-01", "release", VFIO)
    require(released.stdout.strip() == "ACTION /usr/bin/systemctl stop --no-block hyperlab-vfio-inhibit@dev-01.service",
            "the inhibitor outlives the Machine")
    for domain, phase in (("dev-01", "prepare"), ("dev-01", "stopped"), ("../x", "started"), ("Dev_01", "started")):
        result = hook(domain, phase, VFIO)
        require(result.returncode == 0 and result.stdout == "", f"the hook acted on {domain} {phase}")
    require(hook("dev-01", "started", "not xml").returncode == 1, "unreadable XML at start was not reported")

    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    unit = jinja2.Template((ROLE / "templates/hyperlab-vfio-inhibit@.service.j2").read_text()).render(**defaults)
    require("--mode=block" in unit and "systemd-inhibit" in unit and "%i" in unit, "the unit does not block sleep")
    what = defaults["host_sleep_guard_what"].split(":")
    for needed in ("sleep", "idle", "handle-suspend-key", "handle-hibernate-key", "handle-lid-switch"):
        require(needed in what, f"the inhibitor does not cover {needed}")

    handlers = (ROLE / "handlers/main.yml").read_text()
    require(handlers.index("Refuse a libvirt restart while any domain is active")
            < handlers.index("- name: Restart libvirt for the sleep guard hook\n  listen"),
            "libvirt could restart with Machines running")
    bricks = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text())
    require(bricks["brick_requires"]["host_sleep_guard"] == ["kvm_host"]
            and bricks["brick_playbooks"]["host_sleep_guard"] == "playbooks/host-sleep-guard.yml",
            "the sleep guard brick is not in the graph")
    print("Host sleep guard contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
