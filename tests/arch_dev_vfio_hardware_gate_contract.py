#!/usr/bin/env python3
"""Offline contracts for the read-only Nitro acceleration gate tools."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import os
import tempfile
from pathlib import Path
from types import ModuleType

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]


def module(relative: str, name: str) -> ModuleType:
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def run(*argv: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(argv, input=stdin, text=True, capture_output=True, check=False)


def main() -> int:
    host_gate = module(
        "tools/nitro/arch_dev_vfio_host_gate.py",
        "arch_dev_vfio_host_gate",
    )
    plan_result = run(
        sys.executable,
        str(ROOT / "tools/guest_plan.py"),
        "--root",
        str(ROOT),
        "--spec",
        str(ROOT / "vm-specs/arch-dev-vfio.yml"),
        "--store",
        "/var/lib/privatestack/hyperlab",
        "--resource-profiles",
        str(ROOT / "group_vars/all/vm-resource-profiles.yml"),
    )
    assert plan_result.returncode == 0, plan_result.stderr
    plan = json.loads(plan_result.stdout)
    hardware = yaml.safe_load((ROOT / "group_vars/all/hardware.yml").read_text())
    networks = yaml.safe_load((ROOT / "group_vars/all/networks.yml").read_text())
    looking = yaml.safe_load((ROOT / "group_vars/all/looking-glass.yml").read_text())
    report = {
        "host_profile": "nitro-3060",
        "vfio_ids": ["10de:2520", "10de:228e"],
        "vfio_devices": [
            {"id": "10de:2520", "pci": "01:00.0"},
            {"id": "10de:228e", "pci": "01:00.1"},
        ],
        "gpu_pci": "01:00.0",
        "gpu_audio_pci": "01:00.1",
        "cpu_threads": 8,
    }
    with tempfile.TemporaryDirectory() as temporary:
        report_path = Path(temporary) / "report.yml"
        report_path.write_text(yaml.safe_dump(report, sort_keys=False))
        vfio_result = run(
            sys.executable,
            str(ROOT / "tools/vfio_plan.py"),
            "--report",
            str(report_path),
            "--profiles-json",
            json.dumps(hardware["host_profiles"]),
            "--trust-levels-json",
            json.dumps(networks["gpu_trust_levels"]),
            "--looking-glass-build",
            looking["hyperlab_looking_glass_build"],
            "--looking-glass-device",
            looking["hyperlab_looking_glass_device"],
            "--looking-glass-shm-mb",
            "64",
            "--spice-host",
            looking["hyperlab_looking_glass_spice_host"],
            "--spice-port",
            str(looking["hyperlab_looking_glass_spice_port"]),
            stdin=json.dumps(plan),
        )
        assert vfio_result.returncode == 0, vfio_result.stderr
        vfio = json.loads(vfio_result.stdout)

        env = Environment(
            loader=FileSystemLoader(str(ROOT / "roles/guest/templates")),
            undefined=StrictUndefined,
            autoescape=False,
            keep_trailing_newline=True,
        )
        xml = env.get_template("domain.xml.j2").render(
            guest_plan=plan,
            guest_resolved_memory_mb=8192,
            guest_vfio=vfio,
        )
        summary = host_gate.validate_xml(xml, report)
        assert summary == {
            "memory_mib": 8192,
            "bdfs": ["0000:01:00.0", "0000:01:00.1"],
        }

        broken = xml.replace('cpuset="2"', 'cpuset="1"', 1)
        try:
            host_gate.validate_xml(broken, report)
        except host_gate.GateError as error:
            assert "vCPU pins" in str(error)
        else:
            raise AssertionError("drifted vCPU pin was accepted")

        sysfs = Path(temporary) / "sys"
        vfio_root = Path(temporary) / "vfio"
        drivers = sysfs / "bus/pci/drivers"
        iommu_root = sysfs / "kernel/iommu_groups"
        devices_root = sysfs / "bus/pci/devices"
        drivers.mkdir(parents=True)
        vfio_root.mkdir()
        (drivers / "vfio-pci").mkdir()
        for bdf, group_name in (("0000:01:00.0", "17"), ("0000:01:00.1", "18")):
            device = devices_root / bdf
            device.mkdir(parents=True)
            os.symlink(drivers / "vfio-pci", device / "driver")
            group = iommu_root / group_name
            (group / "devices").mkdir(parents=True)
            os.symlink(group, device / "iommu_group")
            os.symlink(device, group / "devices" / bdf)
            os.symlink("/dev/null", vfio_root / group_name)

        host_gate.validate_runtime(
            report,
            sysfs,
            Path("/dev/null"),
            vfio_root,
        )

        unsafe_driver = drivers / "nvidia"
        unsafe_driver.mkdir()
        peer = devices_root / "0000:01:00.2"
        peer.mkdir()
        os.symlink(unsafe_driver, peer / "driver")
        os.symlink(peer, iommu_root / "17/devices/0000:01:00.2")
        try:
            host_gate.validate_runtime(
                report,
                sysfs,
                Path("/dev/null"),
                vfio_root,
            )
        except host_gate.GateError as error:
            assert "IOMMU peer" in str(error)
        else:
            raise AssertionError("unsafe IOMMU peer was accepted")

    guest_module = module(
        "tools/nitro/arch_dev_vfio_guest_gate.py",
        "arch_dev_vfio_guest_gate",
    )
    expected_pin = guest_module.load_expected_pin(ROOT)
    assert expected_pin == (
        looking["hyperlab_looking_glass_commit"],
        looking["hyperlab_looking_glass_build"],
    )
    assert guest_module.pci_class("0000:01:00.0 0300: 10de:2520") == "0300"
    assert guest_module.pci_class("0000:01:00.1 0403: 10de:228e") == "0403"

    guest_gate = (ROOT / "tools/nitro/arch_dev_vfio_guest_gate.py").read_text()
    assert '"10de:"' in guest_gate
    assert '"1af4:1110"' in guest_gate
    assert '"nvidia-smi"' in guest_gate
    assert "runtime_enabled" in guest_gate
    assert "nvidia_drm/parameters" in guest_gate
    assert "Linux sender commit pin drift" in guest_gate
    assert "ARCH_DEV_VFIO_GUEST_GATE_OK" in guest_gate

    print("arch-dev-vfio hardware gate contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
