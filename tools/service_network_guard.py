#!/usr/bin/env python3
"""Verify that persistent libvirt XML owns exactly one reviewed service lease."""
from __future__ import annotations

import argparse
import json
import sys
import xml.etree.ElementTree as ET


class NetworkGuardError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise NetworkGuardError(message)


def verify(xml: str, name: str, mac: str, ip: str) -> dict[str, str]:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as exc:
        raise NetworkGuardError(f"persistent services network XML cannot be parsed: {exc}") from exc
    require((root.findtext("name") or "").strip() == "services", "persistent XML is not the services network")
    hosts = [dict(node.attrib) for node in root.findall("./ip/dhcp/host")]
    exact = [host for host in hosts if host.get("name") == name and host.get("mac") == mac and host.get("ip") == ip]
    require(len(exact) == 1, "reviewed service lease is absent or duplicated in persistent network XML")
    for host in hosts:
        if host in exact:
            continue
        require(host.get("name") != name, f"service name {name} is assigned to another lease")
        require(host.get("mac") != mac, f"service MAC {mac} is assigned to another lease")
        require(host.get("ip") != ip, f"service IP {ip} is assigned to another lease")
    return {"name": name, "mac": mac, "ip": ip, "network": "services"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--mac", required=True)
    parser.add_argument("--ip", required=True)
    args = parser.parse_args()
    try:
        result = verify(sys.stdin.read(), args.name, args.mac, args.ip)
    except NetworkGuardError as exc:
        print(f"service network refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
