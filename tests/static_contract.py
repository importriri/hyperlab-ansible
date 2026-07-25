#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
import yaml

root = Path(__file__).resolve().parents[1]
errors: list[str] = []

def check(ok: bool, message: str) -> None:
    if not ok:
        errors.append(message)

hardware = yaml.safe_load((root / "group_vars/all/hardware.yml").read_text())
networks = yaml.safe_load((root / "group_vars/all/networks.yml").read_text())
profiles = hardware["hardware_profiles"]
check(set(profiles) == {"nitro-3060", "predator-3070"}, "both laptop profiles must exist")
for name, profile in profiles.items():
    check(len(profile["vfio_ids"]) == 2, f"{name} must bind GPU and HDMI audio")
    check(all(len(x) == 9 and x[4] == ':' for x in profile["vfio_ids"]), f"bad PCI ID in {name}")

domains = networks["network_domains"]
check([d["name"] for d in domains] == ["clean", "dirty", "dev", "lab", "services"], "domain order/coverage drift")
check([d["name"] for d in domains if d["forward"] == "isolated"] == ["lab"], "lab must be the only isolated domain")
check("services" not in networks["gpu_trust_levels"], "services must never receive the GPU")


lab_roles = [str(x) for x in yaml.safe_load((root / "playbooks/lab.yml").read_text())[0]["roles"]]
check(lab_roles == ["base", "hardware_probe", "kvm_host", "vfio_boot", "network_domains", "lab_isolation", "gpu_handoff"], "lab role order drift")

hardware_tasks = (root / "roles/hardware_probe/tasks/main.yml").read_text()
check("lspci -Dn" in hardware_tasks, "hardware probe must use numeric PCI discovery")
check("difference(hardware_probe_detected_ids)" in hardware_tasks, "hardware profile must validate all required IDs")

network_tasks = (root / "roles/network_domains/tasks/main.yml").read_text()
check("net-dumpxml --inactive" in network_tasks, "network drift must compare persistent XML")
check("network_domains_reconcile" in network_tasks, "network role must reconcile changed definitions")
check("network_domains_restart_changed" in network_tasks, "active network restart must be explicit")

looking_tasks = (root / "roles/looking_glass/tasks/main.yml").read_text()
looking_handlers = (root / "roles/looking_glass/handlers/main.yml").read_text()
check("stat.ischr" in looking_tasks, "kvmfr must be verified as a character device")
check("failed_when: looking_glass_unload.rc != 0" in looking_handlers, "kvmfr resize must fail when unload fails")

client = (root / "roles/looking_glass/templates/client.ini.j2").read_text().splitlines()
check(not any(line.startswith('#') for line in client), "Looking Glass B7 comments must use semicolons")
check(any(line == 'port={{ looking_glass_spice_port }}' for line in client), "SPICE port must remain templated")

if errors:
    print("STATIC CONTRACT FAILED", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    raise SystemExit(1)
print("static contract: OK")
