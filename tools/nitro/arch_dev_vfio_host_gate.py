#!/usr/bin/env python3
"""Read-only host gate for the reviewed Nitro arch-dev-vfio contract."""
from __future__ import annotations

import argparse
import fcntl
import json
import stat
import struct
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml

QEMU_NS = "http://libvirt.org/schemas/domain/qemu/1.0"
EXPECTED_PINS = [("0", "2"), ("1", "6"), ("2", "3"), ("3", "7")]
VFIO_GROUP_GET_STATUS = (ord(";") << 8) | 103
VFIO_GROUP_FLAGS_VIABLE = 1


class GateError(ValueError):
    """The active host differs from the reviewed Nitro contract."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GateError(message)


def command(*argv: str) -> str:
    result = subprocess.run(argv, text=True, capture_output=True, check=False)
    require(result.returncode == 0, result.stderr.strip() or "command failed")
    return result.stdout


def vfio_group_is_viable(path: Path) -> bool:
    status = bytearray(struct.pack("II", 8, 0))
    with path.open("rb+", buffering=0) as handle:
        fcntl.ioctl(
            handle,
            VFIO_GROUP_GET_STATUS,
            status,
            True,
        )
    argsz, flags = struct.unpack("II", status)
    require(argsz >= 8, f"VFIO group status is truncated: {path.name}")
    return bool(flags & VFIO_GROUP_FLAGS_VIABLE)


def load_report(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(data, dict), "hardware report root must be a mapping")
    require(data.get("host_profile") == "nitro-3060", "Nitro profile is not selected")
    require(data.get("cpu_threads") == 8, "Nitro gate requires eight CPU threads")
    return data


def pci_from_xml(address: ET.Element) -> str:
    def number(name: str) -> int:
        value = address.get(name)
        require(value is not None, f"PCI address lacks {name}")
        return int(value, 0)

    return f"{number('domain'):04x}:{number('bus'):02x}:{number('slot'):02x}.{number('function')}"


def validate_xml(xml_text: str, report: dict[str, Any]) -> dict[str, Any]:
    root = ET.fromstring(xml_text)
    require(root.findtext("name") == "arch-dev-vfio", "unexpected domain name")
    memory = root.find("memory")
    require(memory is not None and memory.get("unit") == "MiB", "memory must use MiB")
    memory_mib = int(memory.text or "0")
    require(memory_mib in {8192, 16384}, "memory must use balanced or heavy profile")
    current_memory = root.find("currentMemory")
    require(
        current_memory is not None
        and current_memory.get("unit") == "MiB"
        and int(current_memory.text or "0") == memory_mib,
        "current memory must match the selected profile",
    )
    require(root.findtext("vcpu") == "4", "Nitro Linux profile requires four vCPUs")
    require(root.findtext("iothreads") == "1", "one QEMU I/O thread is required")

    pins = [(node.get("vcpu"), node.get("cpuset")) for node in root.findall("./cputune/vcpupin")]
    require(pins == EXPECTED_PINS, "vCPU pins differ from 2/6 and 3/7")
    emulator = root.find("./cputune/emulatorpin")
    io_pin = root.find("./cputune/iothreadpin")
    require(emulator is not None and emulator.get("cpuset") == "0,4", "emulator pin drift")
    require(io_pin is not None and io_pin.get("cpuset") == "1,5", "I/O thread pin drift")

    topology = root.find("./cpu/topology")
    require(topology is not None, "virtual CPU topology is missing")
    require(
        topology.attrib == {"sockets": "1", "dies": "1", "cores": "2", "threads": "2"},
        "virtual CPU topology drift",
    )
    disk_driver = root.find("./devices/disk[@device='disk']/driver")
    require(disk_driver is not None and disk_driver.get("iothread") == "1", "disk I/O thread missing")

    hostdevs = root.findall("./devices/hostdev/source/address")
    observed_bdfs = [pci_from_xml(node) for node in hostdevs]
    expected_bdfs = [
        str(report.get("gpu_pci", "")).removeprefix("0000:"),
        str(report.get("gpu_audio_pci", "")).removeprefix("0000:"),
    ]
    require(all(expected_bdfs), "hardware report lacks reviewed PCI addresses")
    observed_short = [value.removeprefix("0000:") for value in observed_bdfs]
    require(observed_short == expected_bdfs, "domain PCI functions differ from preflight")

    graphics = root.find("./devices/graphics[@type='spice']")
    require(graphics is not None, "SPICE recovery device is missing")
    require(graphics.get("listen") == "127.0.0.1", "SPICE must stay loopback-only")
    require(graphics.get("port") == "5900" and graphics.get("autoport") == "no", "SPICE port drift")
    require(root.find("./devices/video") is not None, "recovery video is missing")

    qemu_args = [
        node.get("value", "")
        for node in root.findall(f"./{{{QEMU_NS}}}commandline/{{{QEMU_NS}}}arg")
    ]
    joined = "\n".join(qemu_args)
    require("ivshmem-plain" in joined, "IVSHMEM device is missing")
    require("/dev/kvmfr0" in joined, "kvmfr transport is missing")
    require("67108864" in joined, "64 MiB shared-memory size is missing")
    return {"memory_mib": memory_mib, "bdfs": observed_bdfs}


def validate_runtime(
    report: dict[str, Any],
    sysfs: Path,
    kvmfr: Path,
    vfio_root: Path,
) -> None:
    require(kvmfr.exists(), "kvmfr device is missing")
    require(stat.S_ISCHR(kvmfr.stat().st_mode), "kvmfr path is not a character device")
    groups: list[str] = []
    for key in ("gpu_pci", "gpu_audio_pci"):
        bdf = str(report.get(key, ""))
        require(bdf, f"hardware report lacks {key}")
        full = bdf if bdf.startswith("0000:") else f"0000:{bdf}"
        device = sysfs / "bus/pci/devices" / full
        require(device.is_dir(), f"PCI function is missing: {full}")
        driver = device / "driver"
        require(driver.is_symlink(), f"PCI driver link is missing: {full}")
        require(driver.resolve().name == "vfio-pci", f"PCI function is not bound to vfio-pci: {full}")
        group = device / "iommu_group"
        require(group.is_symlink(), f"IOMMU group is missing: {full}")
        group_name = group.resolve().name
        groups.append(group_name)
        vfio_group = vfio_root / group_name
        require(vfio_group.exists(), f"VFIO group device is missing: {group_name}")
        require(stat.S_ISCHR(vfio_group.stat().st_mode), f"VFIO group is not a character device: {group_name}")

    unique_groups = sorted(set(groups))
    require(
        len(unique_groups) == 1,
        "reviewed GPU functions must share one IOMMU group",
    )

    for group_name in unique_groups:
        vfio_group = vfio_root / group_name
        require(
            vfio_group_is_viable(vfio_group),
            f"VFIO group is not viable: {group_name}",
        )

        group_devices = sysfs / "kernel/iommu_groups" / group_name / "devices"
        require(
            group_devices.is_dir(),
            f"IOMMU group directory is missing: {group_name}",
        )

        for member in group_devices.iterdir():
            driver = member / "driver"
            require(
                driver.is_symlink(),
                f"IOMMU peer lacks a driver: {member.name}",
            )
            driver_name = driver.resolve().name

            if driver_name == "vfio-pci":
                continue

            class_path = member / "class"
            require(
                class_path.is_file(),
                f"IOMMU peer class is missing: {member.name}",
            )
            class_code = class_path.read_text(encoding="utf-8").strip().lower()

            require(
                class_code.startswith("0x0604")
                and driver_name == "pcieport",
                (
                    "IOMMU peer still uses an unsupported host driver: "
                    f"{member.name} ({driver_name}, {class_code})"
                ),
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", default="arch-dev-vfio")
    parser.add_argument("--uri", default="qemu:///system")
    parser.add_argument("--report", default="/etc/privatestack/hardware-profile.yml")
    parser.add_argument("--xml-file")
    parser.add_argument("--sysfs-root", default="/sys")
    parser.add_argument("--vfio-root", default="/dev/vfio")
    parser.add_argument("--kvmfr-device", default="/dev/kvmfr0")
    parser.add_argument("--offline", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        report = load_report(Path(args.report))
        if args.xml_file:
            xml_text = Path(args.xml_file).read_text(encoding="utf-8")
        else:
            state = command("virsh", "-c", args.uri, "domstate", args.domain).strip()
            require(state == "running", f"domain is not running: {state}")
            xml_text = command("virsh", "-c", args.uri, "dumpxml", args.domain)
        summary = validate_xml(xml_text, report)
        if not args.offline:
            validate_runtime(
                report,
                Path(args.sysfs_root),
                Path(args.kvmfr_device),
                Path(args.vfio_root),
            )
    except (OSError, ET.ParseError, GateError, yaml.YAMLError) as error:
        print(f"Nitro VFIO host gate refused: {error}", file=sys.stderr)
        return 2
    print(json.dumps(summary, sort_keys=True))
    print("ARCH_DEV_VFIO_HOST_GATE_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
