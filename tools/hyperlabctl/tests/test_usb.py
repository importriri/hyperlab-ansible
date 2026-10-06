"""hyperlabctl usb list reads sysfs without privilege and names what each device presents."""

import io
import json
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

import world
from harness import check, equals
from hyperlabctl.cli import main
from hyperlabctl.commands import usb


def _descriptors(device_class, *interface_classes):
    """A device descriptor followed by one configuration with these interfaces."""
    data = bytes([18, 1, 0, 2, device_class]) + bytes(13)
    data += bytes([9, 2, 9 + 9 * len(interface_classes), 0, len(interface_classes), 1, 0, 0x80, 50])
    for number, klass in enumerate(interface_classes):
        data += bytes([9, 4, number, 0, 1, klass, 1, 1, 0])
    return data


def _device(root, port, vendor, product_id, authorized, descriptors=None, interfaces=(), **strings):
    entry = root / port
    entry.mkdir()
    (entry / "idVendor").write_text(vendor + "\n")
    (entry / "idProduct").write_text(product_id + "\n")
    (entry / "authorized").write_text("%d\n" % authorized)
    if descriptors is not None:
        (entry / "descriptors").write_bytes(descriptors)
    for key, value in strings.items():
        (entry / key).write_text(value + "\n")
    for number, klass in enumerate(interfaces):
        interface = root / ("%s:1.%d" % (port, number))
        interface.mkdir()
        (interface / "bInterfaceClass").write_text(klass + "\n")


def _tree(base):
    root = Path(base) / "devices"
    root.mkdir()
    # Root hubs and an interface of one are never devices to allow.
    hub = root / "usb1"
    hub.mkdir()
    (hub / "idVendor").write_text("1d6b\n")
    (root / "1-0:1.0").mkdir()
    _device(root, "1-5", "0408", "a061", 1, interfaces=("0e", "0e"),
            manufacturer="SunplusIT Inc", product="HD User Facing")
    _device(root, "1-2", "0781", "5581", 0, descriptors=_descriptors(0, 0x08),
            manufacturer="SanDisk", product="Ultra", serial="4C53\x07000")
    _device(root, "1-3.4", "1234", "abcd", 0, descriptors=_descriptors(0, 0x08, 0x03),
            product="Stick with a keyboard")
    _device(root, "1-10", "dead", "beef", 0)
    _device(root, "2-1", "zzzz", "0001", 0)
    return root


def test_usb_list_reads_ports_ids_strings_and_authorization():
    with tempfile.TemporaryDirectory() as temporary:
        devices = usb.read_usb_devices(_tree(temporary))
    ports = [device["port"] for device in devices]
    equals("usb_ports_blocked_first", ports, ["1-2", "1-3.4", "1-10", "1-5"])
    check("usb_root_hub_skipped", "usb1" not in ports and "1-0:1.0" not in ports)
    check("usb_invalid_vendor_skipped", "2-1" not in ports)
    stick = devices[0]
    equals("usb_vendor", stick["vendor_id"], "0781")
    equals("usb_product_id", stick["product_id"], "5581")
    equals("usb_strings", (stick["manufacturer"], stick["product"]), ("SanDisk", "Ultra"))
    equals("usb_serial_control_stripped", stick["serial"], "4C53000")
    equals("usb_blocked", stick["authorized"], 0)
    equals("usb_blocked_interfaces_from_descriptors", stick["interfaces"], ["08"])
    equals("usb_storage_is_not_hid", stick["hid"], False)
    camera = devices[-1]
    equals("usb_allowed", camera["authorized"], 1)
    equals("usb_allowed_interfaces_from_sysfs", camera["interfaces"], ["0e"])
    equals("usb_missing_serial", camera["serial"], None)


def test_usb_list_marks_a_device_that_presents_a_keyboard():
    with tempfile.TemporaryDirectory() as temporary:
        devices = {device["port"]: device for device in usb.read_usb_devices(_tree(temporary))}
    equals("usb_hid_interfaces", devices["1-3.4"]["interfaces"], ["03", "08"])
    equals("usb_hid_flag", devices["1-3.4"]["hid"], True)


def test_usb_list_reports_unknown_interfaces_as_none_not_harmless():
    with tempfile.TemporaryDirectory() as temporary:
        devices = {device["port"]: device for device in usb.read_usb_devices(_tree(temporary))}
    equals("usb_unknown_interfaces", devices["1-10"]["interfaces"], [])
    equals("usb_unknown_not_hid_claim", devices["1-10"]["hid"], False)


def test_usb_list_hid_device_class_counts():
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        _device(root, "3-1", "aaaa", "bbbb", 0, descriptors=_descriptors(0x03))
        devices = usb.read_usb_devices(root)
    equals("usb_device_class_hid", devices[0]["hid"], True)


def test_usb_list_absent_sysfs_is_empty():
    with tempfile.TemporaryDirectory() as temporary:
        equals("usb_absent", usb.read_usb_devices(Path(temporary) / "missing"), [])


def test_usb_list_json_output_shape():
    with tempfile.TemporaryDirectory() as temporary:
        original = usb.SYSFS_USB
        usb.SYSFS_USB = _tree(temporary)
        buffer = io.StringIO()
        try:
            with redirect_stdout(buffer):
                code = main(["--json", "usb", "list"], ctx=world.build(trust=None))
        finally:
            usb.SYSFS_USB = original
    payload = json.loads(buffer.getvalue())
    equals("usb_json_exit", code, 0)
    equals("usb_json_keys", sorted(payload), ["devices"])
    equals("usb_json_count", len(payload["devices"]), 4)
