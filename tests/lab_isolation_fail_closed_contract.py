#!/usr/bin/env python3
"""A guest bridge nobody declared reaches nothing (fail closed).

problems/guest-isolation-skipped-unknown-bridges.md: the input chain of
`inet lab_isolation` accepts by policy and dropped only what came from the
five declared bridges, so a guest on any other virbr* bridge reached every
host service listening on all addresses (LLMNR, mDNS) and every network's
resolver. This contract renders the shipped template and evaluates packets
against it with first-match semantics:

  1. from an undeclared virbr* bridge nothing reaches the host, not even
     DHCP, and nothing is routed to another guest bridge;
  2. declared networks keep exactly their reviewed flows, and the host's own
     traffic (not a guest bridge) is untouched.

`--template PATH` evaluates another template, to show the reproduction on
the previous one.
"""

from __future__ import annotations

import argparse
import fnmatch
import shlex
import sys
from pathlib import Path

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "roles/lab_isolation/templates/lab-isolation.nft.j2"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def chain(ruleset: str, name: str) -> list[list[str]]:
    body = ruleset.split(f"chain {name} {{", 1)[1].split("\n    }", 1)[0]
    rules = []
    for line in body.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "type ")):
            continue
        rules.append(shlex.split(line))
    return rules


def matches(rule: list[str], packet: dict) -> str | None:
    """The rule's verdict if the packet matches every expression, else None."""
    words = list(rule)
    verdict = words.pop()
    i = 0
    while i < len(words):
        word = words[i]
        if word in ("iifname", "oifname"):
            if not fnmatch.fnmatchcase(packet.get(word[0] + "if", ""), words[i + 1]):
                return None
            i += 2
        elif word == "ct":
            if packet.get("ct") not in words[i + 2].split(","):
                return None
            i += 3
        elif word == "ip" and words[i + 1] == "daddr":
            if packet.get("daddr") != words[i + 2]:
                return None
            i += 3
        elif word in ("udp", "tcp"):
            if packet.get("proto") != word or packet.get(words[i + 1]) != int(words[i + 2]):
                return None
            i += 3
        elif word == "counter":
            i += 1
        else:
            raise AssertionError(f"the evaluator does not know {word!r} in {rule}")
    return verdict


def verdict(rules: list[list[str]], packet: dict) -> str:
    for rule in rules:
        result = matches(rule, packet)
        if result is not None:
            return result
    return "accept"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, default=TEMPLATE)
    args = parser.parse_args()

    domains = yaml.safe_load((ROOT / "group_vars/all/networks.yml").read_text())["network_domains"]
    lab = next(d for d in domains if d["forward"] == "isolated")["bridge"]
    ruleset = jinja2.Template(args.template.read_text()).render(
        network_domains=domains, lab_isolation_table="inet lab_isolation", lab_isolation_lab_bridge=lab)
    rules_in, rules_fwd = chain(ruleset, "input"), chain(ruleset, "forward")

    def host(iif: str, **packet) -> str:
        return verdict(rules_in, dict(packet, iif=iif))

    def routed(iif: str, oif: str) -> str:
        return verdict(rules_fwd, {"iif": iif, "oif": oif, "ct": "new"})

    rogue = "virbr-rogue"
    for label, packet in (
        ("LLMNR on every address", {"proto": "udp", "daddr": "10.10.66.1", "sport": 5355, "dport": 5355, "ct": "new"}),
        ("LLMNR over TCP", {"proto": "tcp", "daddr": "10.10.66.1", "sport": 40000, "dport": 5355, "ct": "new"}),
        ("mDNS", {"proto": "udp", "daddr": "224.0.0.251", "sport": 5353, "dport": 5353, "ct": "new"}),
        ("the dev network's resolver", {"proto": "udp", "daddr": "10.10.3.1", "sport": 40000, "dport": 53, "ct": "new"}),
        ("DHCP", {"proto": "udp", "daddr": "255.255.255.255", "sport": 68, "dport": 67, "ct": "new"}),
    ):
        require(host(rogue, **packet) == "drop",
                f"a guest on an undeclared bridge reached the host: {label}")
    for target in ("virbr-dev", "virbr-services", "virbr-other"):
        require(routed(rogue, target) == "drop", f"an undeclared bridge was routed to {target}")

    require(host("virbr-dev", proto="udp", daddr="10.10.3.1", sport=40000, dport=53, ct="new") == "accept",
            "dev lost DNS on its own gateway")
    require(host("virbr-dev", proto="udp", daddr="10.10.5.1", sport=40000, dport=53, ct="new") == "drop",
            "dev reached the services resolver")
    require(routed("virbr-dev", "wlan0") == "accept", "dev lost its NAT route to the internet")
    require(routed("virbr-lab", "wlan0") == "drop", "lab reached the internet")
    require(host("wlan0", proto="udp", daddr="192.168.1.9", sport=5355, dport=5355, ct="new") == "accept",
            "the host's own network was filtered")
    require(host("lo", proto="tcp", daddr="127.0.0.1", sport=40000, dport=8765, ct="new") == "accept",
            "the host's loopback was filtered")
    require(rules_in[-1] == ["iifname", "virbr*", "counter", "drop"],
            "the input chain does not end by dropping every other guest bridge")
    require(rules_fwd[-1] == ["iifname", "virbr*", "oifname", "virbr*", "counter", "drop"],
            "the forward chain does not end by dropping every other bridge-to-bridge route")
    print("Guest isolation fail-closed contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
