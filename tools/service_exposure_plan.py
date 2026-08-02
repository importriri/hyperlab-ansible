#!/usr/bin/env python3
"""Bind reviewed service exposures to one observed physical default route."""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from typing import Any

IFACE_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,15}$")
BRIDGE_RE = re.compile(r"^virbr-[a-z0-9-]+$")
EXPOSURE_RE = re.compile(r"^(tcp|udp)/([1-9][0-9]{0,4})$")
VIRTUAL_PREFIXES = ("virbr", "vnet", "tap", "tun", "docker", "br-")


class ExposurePlanError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ExposurePlanError(message)


def select_interface(routes: Any, override: str) -> str:
    require(isinstance(routes, list), "default-route evidence must be a list")
    candidates: list[str] = []
    for route in routes:
        if not isinstance(route, dict) or route.get("dst") != "default":
            continue
        dev = route.get("dev")
        if isinstance(dev, str) and dev not in candidates:
            candidates.append(dev)
    if override:
        require(override in candidates, "LAN interface override is not an observed default-route device")
        selected = override
    else:
        require(len(candidates) == 1,
                f"exactly one default-route interface is required; observed {candidates!r}")
        selected = candidates[0]
    require(IFACE_RE.fullmatch(selected) is not None, "LAN interface name is invalid")
    require(selected != "lo" and not selected.startswith(VIRTUAL_PREFIXES),
            "LAN interface must be a physical/default-route interface, not a virtual bridge")
    return selected


def build(service_plan: dict[str, Any], routes: Any, bridge: str, override: str) -> dict[str, Any]:
    require(service_plan.get("schema_version") == 1, "service plan schema_version must be 1")
    domain = service_plan.get("vm")
    require(isinstance(domain, str) and domain == service_plan.get("id") and domain.startswith("svc-"),
            "service exposure domain identity is invalid")
    require(service_plan.get("network_profile") == "services",
            "LAN exposure is limited to the reviewed services network")
    require(BRIDGE_RE.fullmatch(bridge) is not None and bridge == "virbr-services",
            "service exposure bridge must remain virbr-services")
    dhcp = service_plan.get("dhcp")
    require(isinstance(dhcp, dict), "service exposure requires reviewed DHCP identity")
    guest_ip = str(dhcp.get("ip", ""))
    address = ipaddress.ip_address(guest_ip)
    require(address in ipaddress.ip_network("10.10.5.0/24"),
            "service exposure target is outside the services subnet")
    interface = select_interface(routes, override)
    requested = service_plan.get("exposures")
    require(isinstance(requested, list) and requested, "M8 requires at least one reviewed service exposure")
    exposures: list[dict[str, Any]] = []
    seen: set[tuple[str, int]] = set()
    for item in requested:
        require(isinstance(item, str), "service exposure entries must be strings")
        match = EXPOSURE_RE.fullmatch(item)
        require(match is not None, f"invalid service exposure {item!r}")
        protocol = match.group(1)
        port = int(match.group(2))
        require(port <= 65535, f"service exposure port exceeds 65535: {item}")
        key = (protocol, port)
        require(key not in seen, "service exposure contains a protocol/port collision")
        seen.add(key)
        exposures.append({
            "domain": domain,
            "protocol": protocol,
            "host_port": port,
            "guest_ip": guest_ip,
            "guest_port": port,
            "lan_interface": interface,
            "guest_bridge": bridge,
            "comment": f"privatestack-service-exposure:{domain}:{protocol}:{port}",
        })
    return {
        "schema_version": 1,
        "state_dir": "/run/privatestack-service-exposure",
        "nft_table_family": "ip",
        "nft_table_name": "privatestack_services",
        "libvirt_table_family": "ip",
        "libvirt_table_name": "libvirt_network",
        "libvirt_input_chain": "guest_input",
        "domains": {domain: exposures},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bridge", default="virbr-services")
    parser.add_argument("--interface-override", default="")
    args = parser.parse_args()
    try:
        payload = json.load(sys.stdin)
        require(isinstance(payload, dict), "exposure-plan JSON root must be a mapping")
        service_plan = payload.get("service_plan")
        require(isinstance(service_plan, dict), "service_plan must be a mapping")
        result = build(service_plan, payload.get("routes"), args.bridge, args.interface_override)
    except (OSError, ValueError, json.JSONDecodeError, ExposurePlanError) as exc:
        print(f"service exposure plan refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
