#!/usr/bin/env python3
"""Resolve one managed guest IPv4 address from QEMU Guest Agent evidence."""
from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
import re
import subprocess
import sys


DOMAIN_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$")
MAC_PATTERN = re.compile(r"^(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}$")
LIBVIRT_URI = "qemu:///system"


def domifaddr_argv(virsh_bin: Path, domain: str) -> list[str]:
    """Build the deterministic system-libvirt QGA address query."""
    return [
        str(virsh_bin),
        "-c",
        LIBVIRT_URI,
        "domifaddr",
        domain,
        "--source",
        "agent",
        "--full",
    ]


def resolve_address(output: str, mac: str, network: str) -> str:
    """Return the unique IPv4 address matching both MAC and managed subnet."""
    if not MAC_PATTERN.fullmatch(mac):
        raise ValueError("managed MAC address is malformed")

    try:
        expected_network = ipaddress.ip_network(network, strict=True)
    except ValueError as exc:
        raise ValueError("managed network is not a canonical CIDR") from exc
    if expected_network.version != 4:
        raise ValueError("managed network must be IPv4")

    matches: list[str] = []
    for line in output.splitlines():
        fields = line.split()
        if len(fields) != 4:
            continue
        _interface, observed_mac, protocol, address = fields
        if protocol.lower() != "ipv4" or observed_mac.lower() != mac.lower():
            continue
        try:
            observed = ipaddress.ip_interface(address)
        except ValueError:
            continue
        if observed.version == 4 and observed.ip in expected_network:
            matches.append(str(observed.ip))

    unique = sorted(set(matches))
    if len(unique) != 1:
        raise ValueError(
            "QEMU Guest Agent must report exactly one managed IPv4 address "
            f"for {mac} inside {expected_network}; observed {unique}"
        )
    return unique[0]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--virsh-bin", type=Path, default=Path("/usr/bin/virsh"))
    parser.add_argument("--domain", required=True)
    parser.add_argument("--mac", required=True)
    parser.add_argument("--network", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not DOMAIN_PATTERN.fullmatch(args.domain):
        print("managed domain name is malformed", file=sys.stderr)
        return 2
    if not args.virsh_bin.is_absolute():
        print("virsh path must be absolute", file=sys.stderr)
        return 2

    environment = os.environ.copy()
    environment["LC_ALL"] = "C"
    try:
        result = subprocess.run(
            domifaddr_argv(args.virsh_bin, args.domain),
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
            env=environment,
        )
        address = resolve_address(result.stdout, args.mac, args.network)
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(address)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
