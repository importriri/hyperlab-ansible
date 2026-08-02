"""Parsing libvirt XML with the standard library.

virsh is the interface (ADR 0004), but its human output is not. Everything read
here comes from dumpxml or a --name listing: the two surfaces libvirt keeps
stable.
"""

import xml.etree.ElementTree as ET

from .errors import Unavailable

HL = "https://github.com/importriri/privatestack-ansible/hyperlab/1"


def _pci_address(node):
    if node is None:
        return None
    def part(name, width):
        raw = node.get(name)
        if raw is None:
            return None
        return format(int(raw, 16), "0%dx" % width)
    fields = [part("domain", 4), part("bus", 2), part("slot", 2), part("function", 1)]
    if any(field is None for field in fields):
        return None
    return "%s:%s:%s.%s" % tuple(fields)


def parse_domain(xml_text):
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise Unavailable("domain XML did not parse: %s" % exc) from exc

    memory_kib = None
    for tag in ("currentMemory", "memory"):
        node = root.find(tag)
        if node is not None and node.text:
            unit = (node.get("unit") or "KiB").lower()
            value = int(node.text)
            memory_kib = value if unit in ("kib", "k") else value * 1024
            break

    networks = []
    for interface in root.findall("./devices/interface"):
        source = interface.find("source")
        if source is None:
            continue
        name = source.get("network") or source.get("bridge")
        if name:
            networks.append(name)

    hostdevs = []
    for hostdev in root.findall("./devices/hostdev"):
        if hostdev.get("type") != "pci":
            continue
        address = _pci_address(hostdev.find("./source/address"))
        if address:
            hostdevs.append(address)

    name_node = root.find("name")
    metadata = root.find("./metadata/{%s}instance" % HL)
    return {
        "name": name_node.text if name_node is not None else None,
        "memory_mb": None if memory_kib is None else memory_kib // 1024,
        "networks": networks,
        "hostdevs": hostdevs,
        "vfio": bool(hostdevs),
        "managed": metadata is not None,
        "device_profile": None if metadata is None else metadata.get("device-profile"),
        "lifecycle": None if metadata is None else metadata.get("lifecycle"),
    }
