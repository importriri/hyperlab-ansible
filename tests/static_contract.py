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

client = (root / "roles/looking_glass/templates/client.ini.j2").read_text().splitlines()
check(not any(line.startswith('#') for line in client), "Looking Glass B7 comments must use semicolons")
check(any(line == 'port={{ looking_glass_spice_port }}' for line in client), "SPICE port must remain templated")

if errors:
    print("STATIC CONTRACT FAILED", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    raise SystemExit(1)
print("static contract: OK")
