#!/usr/bin/env python3
"""Refuse PCI, Looking Glass and fixed-SPICE collisions across libvirt domain XML.

The GPU is a boot-scoped lease (ADR 0016): several HyperLab-managed VFIO
domains may name the same PCI functions in their definitions, but only one of
them may run at a time. A domain HyperLab does not manage never shares them.
"""
from __future__ import annotations

import json
import sys
import xml.etree.ElementTree as ET
from typing import Any


class RegistryError(ValueError):
    """The libvirt registry cannot safely accept or start a VFIO domain."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RegistryError(message)


def address_bdf(address: ET.Element) -> str:
    try:
        domain = int(address.get("domain", "0"), 0)
        bus = int(address.get("bus", "0"), 0)
        slot = int(address.get("slot", "0"), 0)
        function = int(address.get("function", "0"), 0)
    except ValueError as exc:
        raise RegistryError("libvirt domain contains an invalid PCI source address") from exc
    return f"{domain:04x}:{bus:02x}:{slot:02x}.{function:x}"


HYPERLAB_NAMESPACES = (
    "https://github.com/importriri/hyperlab-ansible/hyperlab/1",
    "https://github.com/importriri/privatestack-ansible/hyperlab/1",
)
QEMU_NAMESPACE = "http://libvirt.org/schemas/domain/qemu/1.0"


def managed_vfio(root: ET.Element) -> bool:
    for namespace in HYPERLAB_NAMESPACES:
        instance = root.find(f"./metadata/{{{namespace}}}instance")
        if instance is not None:
            return instance.get("device-profile") == "vfio"
    return False


def looking_glass_devices(root: ET.Element) -> list[str]:
    devices = []
    for arg in root.findall(f"./{{{QEMU_NAMESPACE}}}commandline/{{{QEMU_NAMESPACE}}}arg"):
        value = arg.get("value", "")
        if "memory-backend-file" in value and "/dev/kvmfr" in value:
            start = value.index("/dev/kvmfr")
            devices.append(value[start:].split("'", 1)[0])
    return sorted(set(devices))


def domain_contract(xml_text: str, name: str) -> dict[str, Any]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise RegistryError(f"cannot parse inactive XML for {name}: {exc}") from exc
    bdfs = []
    for node in root.findall("./devices/hostdev[@type='pci']/source/address"):
        bdfs.append(address_bdf(node))
    graphics = root.find("./devices/graphics[@type='spice']")
    port = None if graphics is None else graphics.get("port")
    return {
        "bdfs": sorted(bdfs),
        "spice_port": port,
        "managed_vfio": managed_vfio(root),
        "looking_glass": looking_glass_devices(root),
    }


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise RegistryError("registry payload root must be a mapping")
        planned_name = payload.get("planned_name")
        mode = payload.get("mode")
        planned_bdfs = payload.get("planned_bdfs")
        domains = payload.get("domains")
        active_names = payload.get("active_names", [])
        spice_port = str(payload.get("spice_port", "5900"))
        require(isinstance(planned_name, str) and planned_name, "planned_name is required")
        require(mode in {"define", "start"}, "mode must be define or start")
        require(isinstance(planned_bdfs, list) and len(planned_bdfs) == 2
                and all(isinstance(item, str) for item in planned_bdfs),
                "planned_bdfs must contain GPU and audio")
        require(isinstance(domains, list), "domains must be a list")
        require(isinstance(active_names, list) and all(isinstance(item, str) for item in active_names),
                "active_names must be a string list")

        planned_set = set(planned_bdfs)
        planned_looking_glass: list[str] = []
        for item in domains:
            if isinstance(item, dict) and item.get("name") == planned_name and isinstance(item.get("xml"), str):
                planned_looking_glass = domain_contract(item["xml"], planned_name)["looking_glass"]
        seen_names: set[str] = set()
        for item in domains:
            require(isinstance(item, dict), "domain registry entries must be mappings")
            name = item.get("name")
            xml_text = item.get("xml")
            require(isinstance(name, str) and name, "domain registry entry needs a name")
            require(name not in seen_names, f"duplicate libvirt domain entry: {name}")
            require(isinstance(xml_text, str) and xml_text, f"domain {name} has no inactive XML")
            seen_names.add(name)
            contract = domain_contract(xml_text, name)
            owned = set(contract["bdfs"])
            overlap = sorted(planned_set & owned)
            if name == planned_name:
                if owned:
                    require(owned == planned_set,
                            f"existing domain {name} owns VFIO devices {sorted(owned)}, expected {sorted(planned_set)}")
                continue
            # Another managed VFIO domain may name the same GPU: owning it is a
            # lease taken at start. An unmanaged domain never shares it.
            require(not overlap or contract["managed_vfio"],
                    f"VFIO devices {overlap} are already assigned to libvirt domain {name}, "
                    "which HyperLab does not manage")
            if mode == "start" and name in active_names:
                require(not overlap,
                        f"VFIO devices {overlap} are in use by running domain {name}")
                shared = sorted(set(planned_looking_glass) & set(contract["looking_glass"]))
                require(not shared,
                        f"Looking Glass device {', '.join(shared)} is in use by running domain {name}")
                require(contract["spice_port"] != spice_port,
                        f"active domain {name} already owns fixed SPICE port {spice_port}")

        if mode == "start":
            require(planned_name in seen_names,
                    f"planned VFIO domain {planned_name} is not defined")
    except (OSError, json.JSONDecodeError, RegistryError) as exc:
        print(f"VFIO registry refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"domains": len(domains), "status": "safe"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
