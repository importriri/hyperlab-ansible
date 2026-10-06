#!/usr/bin/env python3
"""The rendered isolation ruleset is exactly the frozen flow matrix.

docs/network-flows.md freezes which flows exist between the five network
domains, the host and the internet. This contract renders
roles/lab_isolation/templates/lab-isolation.nft.j2 with the declared
network domains and checks, rule by rule, that:

  1. every ordered pair of different domains is dropped in forward;
  2. the isolated domain forwards nothing in either direction, and it is the
     only domain without libvirt NAT;
  3. from each guest bridge the input chain accepts only replies, DHCP and
     DNS to that bridge's own gateway, then drops, and no rule accepts DNS
     on another domain's gateway; both chains end by dropping every other
     guest bridge (fail closed);
  4. the matrix page lists the same domains.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def chain(ruleset: str, name: str) -> list[str]:
    body = ruleset.split(f"chain {name} {{", 1)[1].split("\n    }", 1)[0]
    return [line.strip() for line in body.splitlines()
            if line.strip() and not line.strip().startswith(("#", "type "))]


def main() -> int:
    networks = yaml.safe_load((ROOT / "group_vars/all/networks.yml").read_text())
    domains = networks["network_domains"]
    lab_nets = networks["lab_host_networks"]
    guests = domains + lab_nets
    # The nested lab host's network (ADR 0046) is declared like a domain but
    # is no product network.
    require([n["name"] for n in lab_nets] == ["hl-lab-testbed"] and lab_nets[0]["forward"] == "nat",
            "the nested lab host has exactly one NAT network")
    require(all(n["name"].startswith("hl-lab-") for n in lab_nets),
            "a lab network lacks the hl-lab- prefix")
    require(not {n["name"] for n in lab_nets} & {d["name"] for d in domains}
            and not {n["bridge"] for n in lab_nets} & {d["bridge"] for d in domains},
            "the lab network shares a name or bridge with a product domain")
    require(not {n["name"] for n in lab_nets} & set(networks["gpu_trust_levels"]),
            "the lab network has a GPU class")
    for path in sorted((ROOT / "templates").glob("*.yml")):
        offered = yaml.safe_load(path.read_text()).get("network_allowlist", [])
        require(not {n["name"] for n in lab_nets} & set(offered), f"{path.name} offers the lab network")
    isolated = [d for d in domains if d["forward"] == "isolated"]
    require(len(isolated) == 1 and isolated[0]["name"] == "lab", "lab must be the one isolated domain")
    require(all(d["forward"] == "nat" for d in domains if d["name"] != "lab"),
            "every other domain reaches the internet through NAT")
    lab = isolated[0]["bridge"]
    template = jinja2.Template((ROOT / "roles/lab_isolation/templates/lab-isolation.nft.j2").read_text())
    ruleset = template.render(lab_isolation_guest_networks=guests, lab_isolation_table="inet lab_isolation",
                              lab_isolation_lab_bridge=lab)

    forward = chain(ruleset, "forward")
    expected_forward = [f'iifname "{lab}" counter drop', f'oifname "{lab}" counter drop']
    expected_forward += [f'iifname "{a["bridge"]}" oifname "{b["bridge"]}" counter drop'
                         for a in guests for b in guests if a["name"] != b["name"]]
    # Fail closed: any other bridge-to-bridge route, an undeclared bridge
    # included (problems/guest-isolation-skipped-unknown-bridges.md).
    expected_forward.append('iifname "virbr*" oifname "virbr*" counter drop')
    require(forward == expected_forward, "the forward chain differs from the frozen matrix")

    expected_input = []
    for d in guests:
        bridge, gateway = d["bridge"], d["gateway"]
        expected_input += [
            f'iifname "{bridge}" ct state established,related accept',
            f'iifname "{bridge}" udp sport 68 udp dport 67 accept',
            f'iifname "{bridge}" ip daddr {gateway} udp dport 53 accept',
            f'iifname "{bridge}" ip daddr {gateway} tcp dport 53 accept',
            f'iifname "{bridge}" counter drop',
        ]
    expected_input.append('iifname "virbr*" counter drop')
    require(chain(ruleset, "input") == expected_input, "the guest-to-host chain differs from the frozen matrix")
    require("hook input priority -10; policy accept;" in ruleset,
            "the input chain must only add restrictions to the host's own policy")
    for d in guests:
        for line in chain(ruleset, "input"):
            if f'iifname "{d["bridge"]}"' in line and "dport 53" in line:
                require(f'ip daddr {d["gateway"]} ' in line, f"{d['name']} may query another resolver")

    page = (ROOT / "docs/network-flows.md").read_text()
    header = next(line for line in page.splitlines() if line.startswith("| From"))
    names = {d["name"] for d in guests}
    rows = {line.split("|")[1].strip() for line in page.splitlines()
            if line.startswith("| ") and line.split("|")[1].strip() in names | {"From \\ To"}} - {"From \\ To"}
    require({cell.strip() for cell in header.split("|")[2:-2]} == names and rows == names,
            "the matrix page lists different domains")
    require(re.search(r"^\| lab \|.*\| \*\*no\*\* \|$", page, re.M) is not None,
            "the matrix page no longer says lab has no internet")
    print("Network flow matrix contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
