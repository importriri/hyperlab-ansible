#!/usr/bin/env python3
"""`foundation.yml --check` is honest on a host that never had its packages.

problems/foundation-check-mode-used-what-it-had-not-installed.md: in check
mode a package step only reports "would be installed", so a later task that
runs the package's command, starts its unit or needs the users it creates
fails instead of previewing. kvm_host and host_usbguard already describe
such steps (tests/kvm_host_check_mode_contract.py,
tests/host_usbguard_contract.py). This contract holds every other role of
playbooks/foundation.yml to the same pattern:

  1. hardware_probe: without lspci, a check mode run reads the same numeric
     identities from sysfs, and says so; this machine's sysfs must give the
     same set as lspci -Dn;
  2. network_domains: without virsh or the libvirt Python binding, a check
     mode run renders the definitions, says what it cannot compare, and
     skips every task that asks libvirt;
  3. lab_isolation: without the nftables unit, a check mode run renders the
     ruleset, says so, and skips enabling, asking and reloading nftables,
     the reload handler included;
  4. image_store: when the only missing identities are QEMU's and swtpm's
     and libvirt is not installed, a check mode run says so, previews the
     administrator's directories and skips the rest; any other missing
     identity is still refused.

Each describe-only state holds only in check mode, so a run that changes the
host is unchanged. vfio_boot, gpu_handoff, base and bootstrap_storage run no
command or unit that foundation.yml installs.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def tasks_of(path: str) -> tuple[list[dict], list[str]]:
    tasks = yaml.safe_load((ROOT / path).read_text())
    return tasks, [task["name"] for task in tasks]


def when(task: dict) -> list[str]:
    value = task.get("when", [])
    return [value] if isinstance(value, str) else list(value)


def decided_in_check_mode_only(task: dict, fact: str) -> str:
    expression = " ".join(str(task["ansible.builtin.set_fact"][fact]).split())
    require(expression.startswith("{{ ansible_check_mode and "),
            f"{fact} does not hold only in check mode: {expression}")
    return expression


def check_hardware_probe() -> None:
    tasks, names = tasks_of("roles/hardware_probe/tasks/main.yml")
    require("Read numeric PCI identities from sysfs" in names,
            "hardware_probe runs lspci in a check mode that has no pciutils")
    look = tasks[names.index("Look for lspci")]["ansible.builtin.stat"]
    require(look["path"] == "/usr/bin/lspci", "hardware_probe does not look for lspci")
    decided_in_check_mode_only(tasks[names.index("Decide whether this run reads PCI identities from sysfs")],
                               "hardware_probe_from_sysfs")
    require(names.index("Install PCI discovery tooling") < names.index("Look for lspci")
            < names.index("Read numeric PCI identities"), "lspci is looked for out of order")
    require(when(tasks[names.index("Read numeric PCI identities")]) == ["not hardware_probe_from_sysfs | bool"],
            "lspci is not the reader of a run that changes the host")
    say = tasks[names.index("Say that a check mode run without pciutils reads sysfs")]
    require("sysfs" in say["ansible.builtin.debug"]["msg"] or "/sys/bus/pci" in say["ansible.builtin.debug"]["msg"],
            "a check mode run without pciutils does not say where it read the identities")
    resolve = tasks[names.index("Resolve the PCI address of every reviewed VFIO component")]["ansible.builtin.command"]
    require("grep" in resolve["argv"] and "lspci" in resolve["argv"],
            "the VFIO addresses are not resolved from the same reading")

    # The fallback reads what lspci reads: the same identities, same form.
    script = tasks[names.index("Read numeric PCI identities from sysfs")]["ansible.builtin.shell"]
    require(shutil.which("lspci") is not None, "lspci (pciutils) is needed to compare the sysfs reading")
    fallback = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True).stdout
    tool = subprocess.run(["lspci", "-Dn"], capture_output=True, text=True, check=True).stdout

    def ids(text: str) -> list[str]:
        return sorted({found.lower() for found in re.findall(r"(?i)\b[0-9a-f]{4}:[0-9a-f]{4}\b", text)})

    def addresses(text: str) -> list[str]:
        return sorted(line.split()[0] for line in text.splitlines() if line.strip())

    require(ids(fallback) == ids(tool), f"sysfs and lspci disagree on the PCI identities: {ids(fallback)} {ids(tool)}")
    require(addresses(fallback) == addresses(tool), "sysfs and lspci disagree on the PCI addresses")


def check_network_domains() -> None:
    tasks, names = tasks_of("roles/network_domains/tasks/main.yml")
    require("Decide whether this run can only describe the networks" in names,
            "network_domains asks virsh in a check mode that has no libvirt")
    expression = decided_in_check_mode_only(tasks[names.index("Decide whether this run can only describe the networks")],
                                            "network_domains_describe_only")
    require("network_domains_virsh.stat.exists" in expression and "network_domains_binding.rc == 0" in expression,
            "describe-only does not depend on virsh and the libvirt binding")
    require(tasks[names.index("Look for virsh")]["ansible.builtin.stat"]["path"] == "/usr/bin/virsh",
            "network_domains does not look for virsh")
    say = tasks[names.index("Say what a check mode run on a host without libvirt cannot preview")]
    require(when(say) == ["network_domains_describe_only | bool"], "the network description is not said")
    first = names.index("List all defined libvirt networks")
    last = names.index("Record that the network_domains brick landed")
    for task in tasks[first:last]:
        require("not network_domains_describe_only | bool" in when(task),
                f"{task['name']!r} asks libvirt in a check mode that has none")
    for name in ("Install libvirt network dependencies", "Render the desired persistent network definitions",
                 "Record that the network_domains brick landed"):
        require(not any("describe_only" in c for c in when(tasks[names.index(name)])),
                f"{name!r} is skipped by describe-only")
    require(names.index("Render the desired persistent network definitions") < names.index("Look for virsh") < first,
            "virsh is looked for out of order")


def check_lab_isolation() -> None:
    tasks, names = tasks_of("roles/lab_isolation/tasks/main.yml")
    require("Decide whether this run can only describe the firewall" in names,
            "lab_isolation enables nftables in a check mode that has no nftables")
    expression = decided_in_check_mode_only(tasks[names.index("Decide whether this run can only describe the firewall")],
                                            "lab_isolation_describe_only")
    require("lab_isolation_unit.stat.exists" in expression, "describe-only does not depend on the nftables unit")
    require(tasks[names.index("Look for the nftables unit")]["ansible.builtin.stat"]["path"]
            == "/usr/lib/systemd/system/nftables.service", "lab_isolation does not look for the nftables unit")
    for name in ("Enable nftables at boot", "Ask the kernel - not systemd - whether the isolation table is live",
                 "Load the ruleset only when the kernel is missing it (never restart)"):
        require("not lab_isolation_describe_only | bool" in when(tasks[names.index(name)]),
                f"{name!r} runs in a check mode that has no nftables")
    for name in ("Install nftables", "Install the isolation matrix (validated by nft before landing)",
                 "Record that the lab_isolation brick landed"):
        require(not any("describe_only" in c for c in when(tasks[names.index(name)])),
                f"{name!r} is skipped by describe-only")
    handlers = yaml.safe_load((ROOT / "roles/lab_isolation/handlers/main.yml").read_text())
    reload = next(handler for handler in handlers if handler["name"] == "Reload nftables")
    require(any("lab_isolation_describe_only" in c for c in when(reload)),
            "the reload handler runs in a check mode that has no nftables")


def check_image_store() -> None:
    tasks, names = tasks_of("roles/image_store/tasks/identity.yml")
    require("Decide whether this run can only describe the runtime identities" in names,
            "image_store refuses the QEMU and swtpm identities a check mode run cannot have yet")
    expression = decided_in_check_mode_only(
        tasks[names.index("Decide whether this run can only describe the runtime identities")],
        "image_store_describe_only")
    for part in ("not image_store_libvirt_unit.stat.exists", "image_store_qemu_user", "image_store_swtpm_group",
                 "| difference("):
        require(part in expression, f"describe-only is wider than QEMU and swtpm without libvirt: missing {part}")
    refuse = tasks[names.index("Refuse an identity this host does not have")]
    require(when(refuse) == ["not image_store_describe_only | bool"], "a missing identity is not refused")
    main, main_names = tasks_of("roles/image_store/tasks/main.yml")
    create = main[main_names.index("Create each store directory individually")]
    require(when(create) == ["not image_store_describe_only | bool or item.access == 'admin'"],
            "the store directories of missing groups are created in check mode, or the admin ones are not previewed")
    bases = main[main_names.index("Give sealed bases their own reader group")]
    require("not image_store_describe_only | bool" in when(bases), "the QEMU user is changed in check mode")


def main() -> int:
    check_hardware_probe()
    check_network_domains()
    check_lab_isolation()
    check_image_store()
    print("foundation check mode contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
