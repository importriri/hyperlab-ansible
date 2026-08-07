#!/usr/bin/env python3
"""Compare the managed contract fields of two libvirt domain XML files."""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

HL = "https://github.com/importriri/privatestack-ansible/hyperlab/1"
QEMU = "http://libvirt.org/schemas/domain/qemu/1.0"
Q35_VERSIONED = re.compile(r"pc-q35-\d+(?:\.\d+)+")


def text(root: ET.Element, path: str) -> str | None:
    node = root.find(path)
    return None if node is None else node.text


def attr(root: ET.Element, path: str, name: str) -> str | None:
    node = root.find(path)
    return None if node is None else node.get(name)


def memory_mib(root: ET.Element, path: str) -> int | None:
    node = root.find(path)
    if node is None or node.text is None:
        return None
    value = int(node.text)
    unit = (node.get("unit") or "KiB").lower()
    factors = {"b": 1 / (1024 * 1024), "kib": 1 / 1024, "mib": 1, "gib": 1024}
    if unit not in factors:
        raise ValueError(f"unsupported memory unit {unit}")
    return int(value * factors[unit])


def graphics_listen(root: ET.Element) -> str | None:
    graphics = root.find("./devices/graphics")
    if graphics is None:
        return None
    if graphics.get("listen"):
        return graphics.get("listen")
    child = graphics.find("./listen[@type='address']")
    return None if child is None else child.get("address")


def hostdev_bdfs(root: ET.Element) -> list[str]:
    result: list[str] = []
    for hostdev in root.findall("./devices/hostdev[@type='pci']"):
        address = hostdev.find("./source/address")
        if address is None:
            result.append("<missing>")
            continue
        try:
            domain = int(address.get("domain", "0"), 0)
            bus = int(address.get("bus", "0"), 0)
            slot = int(address.get("slot", "0"), 0)
            function = int(address.get("function", "0"), 0)
        except ValueError:
            result.append("<invalid>")
            continue
        result.append(f"{domain:04x}:{bus:02x}:{slot:02x}.{function:x}")
    return sorted(result)


def input_devices(root: ET.Element) -> list[tuple[str | None, str | None]]:
    return sorted((node.get("type"), node.get("bus")) for node in root.findall("./devices/input"))


def qemu_args(root: ET.Element) -> list[str | None]:
    return [node.get("value") for node in root.findall(f"./{{{QEMU}}}commandline/{{{QEMU}}}arg")]


def machine_matches(expected: str | None, actual: str | None) -> bool:
    """Allow libvirt to resolve only an explicitly generic q35 request."""
    if expected == "q35":
        return actual == "q35" or (
            actual is not None and Q35_VERSIONED.fullmatch(actual) is not None
        )
    return expected == actual


def contract_value_matches(
    key: str,
    expected: dict[str, Any],
    actual: dict[str, Any],
    allow_legacy_missing_dac_relabel: bool,
) -> bool:
    if key == "machine":
        return machine_matches(expected[key], actual[key])
    if key in {"secure_boot", "enrolled_keys"}:
        expected_features = (expected["secure_boot"], expected["enrolled_keys"])
        actual_features = (actual["secure_boot"], actual["enrolled_keys"])
        if expected_features == (None, None) and actual_features in {
            (None, None),
            (None, "no"),
            ("no", None),
            ("no", "no"),
            ("yes", "no"),
        }:
            # Firmware auto-selection may publish the selected firmware's
            # capabilities.  Without enrolled keys it still boots unsigned
            # binaries, so it is equivalent to the unconstrained request.
            return True
    if key == "disk_dac_relabel" and allow_legacy_missing_dac_relabel:
        return expected[key] == "no" and actual[key] in {None, "no"}
    if key == "disk_security_labels" and allow_legacy_missing_dac_relabel:
        return expected[key] == [("dac", "no", None)] and (
            actual[key] == [] or actual[key] == expected[key]
        )
    return expected[key] == actual[key]


def signature(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    metadata = root.find(f"./metadata/{{{HL}}}instance")
    metadata_attrs = {} if metadata is None else dict(metadata.attrib)
    disk = root.find("./devices/disk[@device='disk']")
    disk_source = None if disk is None else disk.find("./source")
    disk_dac_seclabel = (
        None
        if disk_source is None
        else disk_source.find("./seclabel[@model='dac']")
    )
    disk_security_labels = sorted(
        (
            node.get("model"),
            node.get("relabel"),
            text(node, "./label"),
        )
        for node in ([] if disk_source is None else disk_source.findall("./seclabel"))
    )
    disk_driver = None if disk is None else disk.find("./driver")
    disk_target = None if disk is None else disk.find("./target")
    seed = root.find("./devices/disk[@device='cdrom']")
    seed_source = None if seed is None else seed.find("./source")
    seed_target = None if seed is None else seed.find("./target")
    interface = root.find("./devices/interface")
    tpm = root.find("./devices/tpm")
    tpm_backend = None if tpm is None else tpm.find("./backend")
    tpm_source = None if tpm_backend is None else tpm_backend.find("./source")
    qga = root.find("./devices/channel/target[@name='org.qemu.guest_agent.0']")
    graphics = root.find("./devices/graphics[@type='spice']")
    clipboard = None if graphics is None else graphics.find("./clipboard")
    filetransfer = None if graphics is None else graphics.find("./filetransfer")
    video = root.find("./devices/video/model")
    balloon = root.find("./devices/memballoon")
    os_type = root.find("./os/type")
    cpu = root.find("./cpu")
    boot = root.find("./os/boot")
    bdfs = hostdev_bdfs(root)
    qemu_commandline = qemu_args(root)
    is_vfio = metadata_attrs.get("device-profile") == "vfio" or bool(bdfs) or bool(qemu_commandline)
    return {
        "name": text(root, "./name"),
        "uuid": text(root, "./uuid"),
        "memory_mb": memory_mib(root, "./memory"),
        "current_memory_mb": memory_mib(root, "./currentMemory"),
        "vcpu": text(root, "./vcpu"),
        "firmware": attr(root, "./os", "firmware"),
        "os_arch": None if os_type is None else os_type.get("arch"),
        "machine": None if os_type is None else os_type.get("machine"),
        "boot": None if boot is None else boot.get("dev"),
        "secure_boot": attr(root, "./os/firmware/feature[@name='secure-boot']", "enabled"),
        "enrolled_keys": attr(root, "./os/firmware/feature[@name='enrolled-keys']", "enabled"),
        "nvram": text(root, "./os/nvram"),
        "cpu_mode": None if cpu is None else cpu.get("mode"),
        "cpu_migratable": None if cpu is None else cpu.get("migratable"),
        "hyperv": root.find("./features/hyperv") is not None,
        "kvm_hidden": attr(root, "./features/kvm/hidden", "state"),
        "ps2": attr(root, "./features/ps2", "state"),
        "disk": None if disk_source is None else disk_source.get("file"),
        "disk_dac_relabel": (
            None if disk_dac_seclabel is None else disk_dac_seclabel.get("relabel")
        ),
        "disk_security_labels": disk_security_labels,
        "disk_format": None if disk_driver is None else disk_driver.get("type"),
        "disk_cache": None if disk_driver is None else disk_driver.get("cache"),
        "disk_discard": None if disk_driver is None else disk_driver.get("discard"),
        "disk_target": None if disk_target is None else disk_target.get("dev"),
        "disk_bus": None if disk_target is None else disk_target.get("bus"),
        "seed": None if seed_source is None else seed_source.get("file"),
        "seed_target": None if seed_target is None else seed_target.get("dev"),
        "seed_bus": None if seed_target is None else seed_target.get("bus"),
        "seed_readonly": seed is not None and seed.find("./readonly") is not None,
        "network": None if interface is None else attr(interface, "./source", "network"),
        "mac": None if interface is None else attr(interface, "./mac", "address"),
        "network_model": None if interface is None else attr(interface, "./model", "type"),
        "qga": qga is not None,
        "tpm_model": None if tpm is None else tpm.get("model"),
        "tpm_backend": None if tpm_backend is None else tpm_backend.get("type"),
        "tpm_version": None if tpm_backend is None else tpm_backend.get("version"),
        "tpm_persistent": None if tpm_backend is None else tpm_backend.get("persistent_state"),
        "tpm_path": None if tpm_source is None else tpm_source.get("path"),
        "graphics": None if graphics is None else graphics.get("type"),
        "graphics_listen": graphics_listen(root),
        "graphics_port": None if graphics is None or not is_vfio else graphics.get("port"),
        "graphics_autoport": None if graphics is None else graphics.get("autoport"),
        "clipboard": None if clipboard is None else clipboard.get("copypaste"),
        "filetransfer": None if filetransfer is None else filetransfer.get("enable"),
        "video_model": None if video is None else video.get("type"),
        "video_vram": None if video is None else video.get("vram"),
        "inputs": input_devices(root) if is_vfio else None,
        "balloon": None if balloon is None else balloon.get("model"),
        "on_poweroff": text(root, "./on_poweroff"),
        "on_reboot": text(root, "./on_reboot"),
        "on_crash": text(root, "./on_crash"),
        "hostdev_bdfs": bdfs,
        "qemu_args": qemu_commandline,
        "filesystem_count": len(root.findall("./devices/filesystem")),
        "metadata": metadata_attrs or None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected", required=True)
    parser.add_argument("--actual", required=True)
    parser.add_argument("--allow-legacy-missing-dac-relabel", action="store_true")
    args = parser.parse_args()
    try:
        expected = signature(Path(args.expected))
        actual = signature(Path(args.actual))
    except (OSError, ET.ParseError, ValueError) as exc:
        print(f"domain XML contract cannot be read: {exc}", file=sys.stderr)
        return 2
    errors = [
        f"{key}: expected {expected[key]!r}, got {actual[key]!r}"
        for key in expected
        if not contract_value_matches(
            key,
            expected,
            actual,
            args.allow_legacy_missing_dac_relabel,
        )
    ]
    if errors:
        print("domain XML contract drift:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("domain XML contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
