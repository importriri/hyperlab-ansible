#!/usr/bin/env python3
"""Compare only the managed semantic fields of two libvirt network XML files."""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def spec(text: str) -> dict[str, object]:
    root = ET.fromstring(text)
    bridge = root.find("bridge")
    forward = root.find("forward")
    ip = root.find("ip")
    dhcp_range = root.find("./ip/dhcp/range")
    dhcp_hosts = [
        dict(sorted(host.attrib.items()))
        for host in root.findall("./ip/dhcp/host")
    ]
    dhcp_hosts.sort(key=lambda host: (host.get("ip", ""), host.get("mac", ""), host.get("name", "")))
    return {
        "name": (root.findtext("name") or "").strip(),
        "bridge": dict(sorted((bridge.attrib if bridge is not None else {}).items())),
        "forward": forward.get("mode") if forward is not None else "isolated",
        "ip": dict(sorted((ip.attrib if ip is not None else {}).items())),
        "dhcp_range": dict(sorted((dhcp_range.attrib if dhcp_range is not None else {}).items())),
        "dhcp_hosts": dhcp_hosts,
    }


def read_arg(value: str) -> str:
    return sys.stdin.read() if value == "-" else Path(value).read_text(encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} DESIRED CURRENT|-", file=sys.stderr)
        return 2
    try:
        desired = spec(read_arg(sys.argv[1]))
        current = spec(read_arg(sys.argv[2]))
    except (OSError, ET.ParseError) as exc:
        print(exc, file=sys.stderr)
        return 2
    if desired == current:
        return 0
    print(json.dumps({"desired": desired, "current": current}, indent=2, sort_keys=True))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
