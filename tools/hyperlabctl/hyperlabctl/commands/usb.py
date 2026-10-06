"""The host's USB devices as the kernel reports them, read-only (ADR 0038).

USBGuard blocks a new device by leaving it unauthorized in sysfs. This
command reads /sys/bus/usb/devices without privilege, so the shell can show
which devices are blocked and what each one presents. Allowing one is the
privileged usb.allow action; nothing here changes a device.

A blocked device is not configured, so its interface directories do not
exist yet. Its interface classes come from the raw descriptors the kernel
read at enumeration, which are readable either way; the interface
directories of a configured device are read as well. A device whose
interfaces cannot be read reports none, and callers treat that as unknown,
never as harmless.
"""

import json
import re
from pathlib import Path

from .base import Command

SYSFS_USB = Path("/sys/bus/usb/devices")
PORT_RE = re.compile(r"^[0-9]+-[0-9]+(\.[0-9]+)*$")
ID_RE = re.compile(r"^[0-9a-f]{4}$")
HID_CLASS = "03"
MAX_STRING = 128
MAX_DESCRIPTORS = 64 * 1024
DESCRIPTOR_DEVICE = 1
DESCRIPTOR_INTERFACE = 4


def _text(path):
    """A short sysfs string, or None when it is absent or unreadable."""
    try:
        value = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    value = "".join(ch for ch in value if ch.isprintable())[:MAX_STRING]
    return value or None


def _descriptor_classes(path):
    """Device and interface classes from a device's raw descriptors."""
    try:
        with open(path, "rb") as stream:
            data = stream.read(MAX_DESCRIPTORS)
    except OSError:
        return None, set()
    device_class = None
    classes = set()
    offset = 0
    while offset + 2 <= len(data):
        length, kind = data[offset], data[offset + 1]
        if length < 2 or offset + length > len(data):
            break
        if kind == DESCRIPTOR_DEVICE and length >= 18:
            device_class = "%02x" % data[offset + 4]
        elif kind == DESCRIPTOR_INTERFACE and length >= 9:
            classes.add("%02x" % data[offset + 5])
        offset += length
    return device_class, classes


def _interface_classes(root, port):
    classes = set()
    for interface in root.glob("%s:*" % port):
        value = _text(interface / "bInterfaceClass")
        if value and re.fullmatch(r"[0-9a-fA-F]{2}", value):
            classes.add(value.lower())
    return classes


def _authorized(path):
    value = _text(path)
    if value in ("0", "1"):
        return int(value)
    return None


def read_usb_devices(sysfs_root=None):
    """Every USB device below the root hubs, blocked ones first."""
    root = Path(sysfs_root) if sysfs_root else SYSFS_USB
    devices = []
    try:
        entries = sorted(root.iterdir(), key=lambda item: item.name)
    except OSError:
        return devices
    for entry in entries:
        port = entry.name
        if not PORT_RE.fullmatch(port):
            continue
        vendor = _text(entry / "idVendor")
        product = _text(entry / "idProduct")
        if not vendor or not ID_RE.fullmatch(vendor):
            continue
        device_class, classes = _descriptor_classes(entry / "descriptors")
        classes |= _interface_classes(root, port)
        if device_class is None:
            device_class = _text(entry / "bDeviceClass")
        devices.append({
            "port": port,
            "vendor_id": vendor,
            "product_id": product if product and ID_RE.fullmatch(product) else None,
            "manufacturer": _text(entry / "manufacturer"),
            "product": _text(entry / "product"),
            "serial": _text(entry / "serial"),
            "authorized": _authorized(entry / "authorized"),
            "interfaces": sorted(classes),
            "hid": HID_CLASS in classes or device_class == HID_CLASS,
        })
    devices.sort(key=lambda device: (device["authorized"] != 0,
                                     [int(part) for part in re.split(r"[-.]", device["port"])]))
    return devices


class UsbCommand(Command):
    name = "usb"
    help = "USB devices and whether the host allows them (read-only)"
    order = 31

    def configure(self, parser):
        sub = parser.add_subparsers(dest="usb_action", required=True)
        sub.add_parser("list")

    def run(self, args, ctx):
        devices = read_usb_devices()
        if args.json:
            print(json.dumps({"devices": devices}, indent=2))
            return 0
        if not devices:
            print("No USB devices below the root hubs.")
            return 0
        for device in devices:
            state = {0: "blocked", 1: "allowed"}.get(device["authorized"], "unknown")
            name = device["product"] or device["manufacturer"] or "USB device"
            print("  %-10s %-8s %s:%s  %-32s %s%s" % (
                device["port"], state, device["vendor_id"], device["product_id"] or "????",
                name, " ".join(device["interfaces"]) or "interfaces unknown",
                "  (keyboard or mouse)" if device["hid"] else ""))
        return 0
