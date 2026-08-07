#!/usr/bin/env python3
"""Host-independent structural and mutation tests for the M4 guest brick."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "tools/guest_plan.py"
VFIO_PLAN = ROOT / "tools/vfio_plan.py"
MEMORY = ROOT / "tools/guest_memory.py"
XML_CONTRACT = ROOT / "tools/guest_xml_contract.py"
STATE_GUARD = ROOT / "tools/guest_state_guard.py"
VFIO_REGISTRY = ROOT / "tools/vfio_registry.py"
LG_BUILD = "B7-263-g0140a3f6fb"


def run(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=stdin, text=True, capture_output=True, check=False)


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def standard_fixture(root: Path) -> tuple[Path, Path]:
    (root / "images").mkdir()
    (root / "vm-specs").mkdir()
    store = root / "store"
    base = store / "bases/linux/debian.qcow2"
    base.parent.mkdir(parents=True)
    base.write_bytes(b"sealed synthetic base\n")
    manifest = {
        "schema_version": 1,
        "id": "debian",
        "display_name": "Debian fixture",
        "os_family": "linux",
        "os_variant": "debian12",
        "version": "fixture",
        "format": "qcow2",
        "status": "sealed",
        "sha256": hashlib.sha256(base.read_bytes()).hexdigest(),
        "private": False,
        "contains_personal_data": False,
        "generalized": True,
        "instance_policy": "multiple",
        "source_type": "local",
        "source_url": None,
        "source_checksum_url": None,
        "filename": "debian.qcow2",
        "virtual_size_gib": 20,
        "minimum_size_gib": 8,
        "min_memory_mb": 2048,
        "supports": {"standard": True, "vfio": False, "cloud_init": True, "qemu_guest_agent": True},
        "requires": {"uefi": True, "secure_boot": False, "tpm2": False},
        "defaults": {"lifecycle": "permanent", "device_profile": "standard", "network_profile": "dev"},
        "network_allowlist": ["dev", "lab"],
        "licensing": {"redistributable": True},
        "looking_glass_host_build_required": None,
    }
    spec = {
        "schema_version": 1,
        "name": "debian-test",
        "image": "debian",
        "lifecycle": "disposable",
        "device_profile": "standard",
        "network_profile": "lab",
        "resources": {"memory_mb": "auto", "vcpus": 2, "disk_gib": None},
        "memory_overcommit": False,
        "autostart": False,
        "qemu_guest_agent": True,
        "looking_glass": False,
        "clipboard": False,
        "shared_folders": False,
        "usb_allowlist": [],
        "owner": "sid",
        "purpose": "fixture",
        "tags": ["test"],
    }
    spec_path = root / "vm-specs/debian-test.yml"
    write_yaml(root / "images/debian.yml", manifest)
    write_yaml(spec_path, spec)
    return spec_path, store


def vfio_fixture(root: Path) -> tuple[Path, Path, Path, dict[str, Any], dict[str, int]]:
    (root / "images").mkdir()
    (root / "vm-specs").mkdir()
    store = root / "store"
    base = store / "bases/windows/win11clean.qcow2"
    base.parent.mkdir(parents=True)
    base.write_bytes(b"sealed synthetic Windows base\n")
    manifest = {
        "schema_version": 1,
        "id": "win11clean",
        "display_name": "Windows fixture",
        "os_family": "windows",
        "os_variant": "win11",
        "version": "fixture",
        "format": "qcow2",
        "status": "sealed",
        "sha256": hashlib.sha256(base.read_bytes()).hexdigest(),
        "private": True,
        "contains_personal_data": True,
        "generalized": False,
        "instance_policy": "singleton",
        "source_type": "local",
        "source_url": None,
        "source_checksum_url": None,
        "filename": "win11clean.qcow2",
        "virtual_size_gib": 128,
        "minimum_size_gib": 80,
        "min_memory_mb": 6144,
        "supports": {"standard": True, "vfio": True, "cloud_init": False, "qemu_guest_agent": True},
        "requires": {"uefi": True, "secure_boot": True, "tpm2": True},
        "defaults": {"lifecycle": "permanent", "device_profile": "vfio", "network_profile": "clean"},
        "network_allowlist": ["clean"],
        "licensing": {"redistributable": False},
        "looking_glass_host_build_required": LG_BUILD,
    }
    spec = {
        "schema_version": 1,
        "name": "win11clean-test",
        "image": "win11clean",
        "lifecycle": "permanent",
        "device_profile": "vfio",
        "network_profile": "clean",
        "resources": {"memory_mb": "auto", "vcpus": 6, "disk_gib": None},
        "memory_overcommit": False,
        "autostart": False,
        "qemu_guest_agent": True,
        "looking_glass": True,
        "clipboard": True,
        "shared_folders": False,
        "usb_allowlist": [],
        "owner": "sid",
        "purpose": "VFIO fixture",
        "tags": ["windows", "vfio"],
        "benchmark": "unigine-valley",
    }
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
    profiles = {
        "nitro-3060": {
            "vfio_ids": ["10de:2520", "10de:228e"],
            "memory": {
                "host_reserved_mb": 2048,
                "qemu_overhead_per_domain_mb": 512,
                "services_reserved_mb": 0,
                "vfio_fixed_overhead_mb": 256,
                "max_auto_memory_mb": 6144,
                "standard_overcommit_ratio": 1.0,
            },
            "cpu_pinning": {
                "host_cpu_threads": 8,
                "plans": {
                    "4": {
                        "vcpu_pins": [2, 6, 3, 7],
                        "emulator_cpus": [0, 4],
                        "iothread_cpus": [1, 5],
                        "topology": {
                            "sockets": 1, "dies": 1, "cores": 2, "threads": 2
                        },
                    },
                    "6": {
                        "vcpu_pins": [1, 5, 2, 6, 3, 7],
                        "emulator_cpus": [0, 4],
                        "iothread_cpus": [0, 4],
                        "topology": {
                            "sockets": 1, "dies": 1, "cores": 3, "threads": 2
                        },
                    },
                },
            },
        }
    }
    trust = {"clean": 3, "dev": 2, "dirty": 1, "lab": 0}
    spec_path = root / "vm-specs/win11clean-test.yml"
    report_path = root / "hardware-profile.yml"
    write_yaml(root / "images/win11clean.yml", manifest)
    write_yaml(spec_path, spec)
    write_yaml(report_path, report)
    return spec_path, store, report_path, profiles, trust


def build_plan(root: Path, spec: Path, store: Path) -> dict[str, Any]:
    result = run(sys.executable, str(PLAN), "--root", str(root), "--spec", str(spec), "--store", str(store))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def build_vfio_plan(plan: dict[str, Any], report: Path, profiles: dict[str, Any], trust: dict[str, int],
                    build: str = LG_BUILD) -> subprocess.CompletedProcess[str]:
    return run(
        sys.executable,
        str(VFIO_PLAN),
        "--report", str(report),
        "--profiles-json", json.dumps(profiles),
        "--trust-levels-json", json.dumps(trust),
        "--looking-glass-build", build,
        "--looking-glass-device", "/dev/kvmfr0",
        "--looking-glass-shm-mb", "64",
        "--spice-host", "127.0.0.1",
        "--spice-port", "5900",
        stdin=json.dumps(plan),
    )


def test_standard_plan() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec, store = standard_fixture(root)
        plan = build_plan(root, spec, store)
        second = build_plan(root, root / "vm-specs/debian-test.yml", store)
        assert second["uuid"] == plan["uuid"]
        assert second["mac"] == plan["mac"]
        assert plan["device_profile"] == "standard"
        assert plan["looking_glass"] is False
        assert plan["looking_glass_mode"] is None
        assert plan["gpu_lock_path"].endswith("/state/locks/gpu.lock")

        manifest_path = root / "images/debian.yml"
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest["status"] = "not-built"
        manifest["sha256"] = None
        write_yaml(manifest_path, manifest)
        refused = run(sys.executable, str(PLAN), "--root", str(root), "--spec", str(spec), "--store", str(store))
        assert refused.returncode == 2 and "not sealed" in refused.stderr

        manifest["status"] = "sealed"
        manifest["sha256"] = hashlib.sha256((store / "bases/linux/debian.qcow2").read_bytes()).hexdigest()
        write_yaml(manifest_path, manifest)
        data = yaml.safe_load(spec.read_text())
        data["device_profile"] = "vfio"
        write_yaml(spec, data)
        refused = run(sys.executable, str(PLAN), "--root", str(root), "--spec", str(spec), "--store", str(store))
        assert refused.returncode == 2 and "does not support vfio" in refused.stderr

        data["device_profile"] = "standard"
        data["shared_folders"] = True
        write_yaml(spec, data)
        refused = run(sys.executable, str(PLAN), "--root", str(root), "--spec", str(spec), "--store", str(store))
        assert refused.returncode == 2 and "shared folders" in refused.stderr

        outside = root / "outside.yml"
        shutil.copy(spec, outside)
        refused = run(sys.executable, str(PLAN), "--root", str(root), "--spec", str(outside), "--store", str(store))
        assert refused.returncode == 2 and "below vm-specs" in refused.stderr


def test_vfio_plan() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec, store, report, profiles, trust = vfio_fixture(root)
        plan = build_plan(root, spec, store)
        result = build_vfio_plan(plan, report, profiles, trust)
        assert result.returncode == 0, result.stderr
        vfio = json.loads(result.stdout)
        assert vfio["gpu"]["bdf"] == "0000:01:00.0"
        assert vfio["audio"]["bdf"] == "0000:01:00.1"
        assert vfio["trust_level"] == 3
        assert vfio["looking_glass_shm_bytes"] == 64 * 1024 * 1024
        assert vfio["looking_glass_mode"] == "windows"
        assert vfio["spice_port"] == 5900
        assert vfio["cpu_pinning"]["enabled"] is True
        assert [item["cpuset"] for item in vfio["cpu_pinning"]["vcpu_pins"]] == [
            "1", "5", "2", "6", "3", "7"
        ]
        assert vfio["cpu_pinning"]["emulator_cpuset"] == "0,4"
        assert vfio["cpu_pinning"]["iothread_cpuset"] == "0,4"

        mismatch = build_vfio_plan(plan, report, profiles, trust, build="B7-999-g0123456789")
        assert mismatch.returncode == 2 and "differs" in mismatch.stderr

        report_data = yaml.safe_load(report.read_text())
        report_data["gpu_audio_pci"] = "02:00.1"
        report_data["vfio_devices"][1]["pci"] = "02:00.1"
        write_yaml(report, report_data)
        split = build_vfio_plan(plan, report, profiles, trust)
        assert split.returncode == 2 and "share one PCI slot" in split.stderr

        spec_data = yaml.safe_load(spec.read_text())
        spec_data["autostart"] = True
        write_yaml(spec, spec_data)
        refused = run(sys.executable, str(PLAN), "--root", str(root), "--spec", str(spec), "--store", str(store))
        assert refused.returncode == 2 and "cannot autostart" in refused.stderr


def template_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(ROOT / "roles/guest/templates")),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    env.filters.update({"bool": bool, "to_json": json.dumps})
    return env


def test_domain_templates() -> None:
    env = template_env()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec, store = standard_fixture(root)
        plan = build_plan(root, spec, store)
        rendered = env.get_template("domain.xml.j2").render(
            guest_plan=plan, guest_resolved_memory_mb=2048, guest_vfio={}
        )
        domain = ET.fromstring(rendered)
        assert domain.find("./devices/hostdev") is None
        disk_source = domain.find("./devices/disk[@device='disk']/source")
        disk_dac = disk_source.find("./seclabel[@model='dac']")
        assert disk_dac is not None and disk_dac.get("relabel") == "no"
        assert domain.find("./devices/graphics").get("autoport") == "yes"
        assert domain.find("./devices/input[@type='tablet']") is not None
        assert domain.find("./features/ps2") is None
        assert domain.find("./devices/memballoon").get("model") == "virtio"

        public_keys = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGateFixture gate"]
        state = yaml.safe_load(env.get_template("state.yml.j2").render(
            guest_plan=plan,
            guest_resolved_memory_mb=2048,
            guest_vfio=None,
            guest_cloud_init_user="sid",
            guest_cloud_init_ssh_public_keys=public_keys,
        ))
        assert state["cloud_init_user"] == "sid"
        assert state["cloud_init_ssh_public_keys"] == public_keys

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec, store, report, profiles, trust = vfio_fixture(root)
        plan = build_plan(root, spec, store)
        result = build_vfio_plan(plan, report, profiles, trust)
        assert result.returncode == 0, result.stderr
        vfio = json.loads(result.stdout)
        rendered = env.get_template("domain.xml.j2").render(
            guest_plan=plan, guest_resolved_memory_mb=6144, guest_vfio=vfio
        )
        domain = ET.fromstring(rendered)
        hostdevs = domain.findall("./devices/hostdev")
        assert len(hostdevs) == 2
        assert all(node.get("managed") == "yes" for node in hostdevs)
        disk_source = domain.find("./devices/disk[@device='disk']/source")
        disk_dac = disk_source.find("./seclabel[@model='dac']")
        assert disk_dac is not None and disk_dac.get("relabel") == "no"
        graphics = domain.find("./devices/graphics")
        assert graphics.get("port") == "5900" and graphics.get("autoport") == "no"
        assert domain.find("./devices/input[@type='mouse'][@bus='virtio']") is not None
        assert domain.find("./devices/input[@type='keyboard'][@bus='virtio']") is not None
        ps2 = domain.find("./features/ps2")
        assert ps2 is not None and ps2.get("state") == "off"
        assert domain.find("./devices/memballoon").get("model") == "none"
        assert domain.find("./iothreads").text == "1"
        pins = domain.findall("./cputune/vcpupin")
        assert [(node.get("vcpu"), node.get("cpuset")) for node in pins] == [
            ("0", "1"), ("1", "5"), ("2", "2"),
            ("3", "6"), ("4", "3"), ("5", "7"),
        ]
        assert domain.find("./cputune/emulatorpin").get("cpuset") == "0,4"
        assert domain.find("./cputune/iothreadpin").get("cpuset") == "0,4"
        topology = domain.find("./cpu/topology")
        assert topology.attrib == {
            "sockets": "1", "dies": "1", "cores": "3", "threads": "2"
        }
        disk_driver = domain.find("./devices/disk[@device='disk']/driver")
        assert disk_driver.get("iothread") == "1"
        qemu_args = [node.get("value") for node in domain.findall(
            "./{http://libvirt.org/schemas/domain/qemu/1.0}commandline/"
            "{http://libvirt.org/schemas/domain/qemu/1.0}arg"
        )]
        assert any("/dev/kvmfr0" in value for value in qemu_args if value)
        assert any("67108864" in value for value in qemu_args if value)


def test_state_guard() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec, store = standard_fixture(root)
        plan = build_plan(root, spec, store)
        state_root = store / "state/vms"
        empty = run(sys.executable, str(STATE_GUARD), "--state-root", str(state_root), stdin=json.dumps(plan))
        assert empty.returncode == 0, empty.stderr
        state_root.mkdir(parents=True)
        collision = {
            "schema_version": 1,
            "name": "other",
            "uuid": "6d7aca2e-5a7b-5c3c-a168-5b094fc306fa",
            "mac": plan["mac"],
            "image": "other-image",
            "instance_policy": "multiple",
        }
        write_yaml(state_root / "other.yml", collision)
        refused = run(sys.executable, str(STATE_GUARD), "--state-root", str(state_root), stdin=json.dumps(plan))
        assert refused.returncode == 2 and "planned MAC collides" in refused.stderr


def test_memory() -> None:
    profile = {
        "host_reserved_mb": 2048,
        "qemu_overhead_per_domain_mb": 512,
        "services_reserved_mb": 0,
        "vfio_fixed_overhead_mb": 256,
        "max_auto_memory_mb": 6144,
        "standard_overcommit_ratio": 1.0,
    }
    standard = run(
        sys.executable, str(MEMORY),
        "--profile-json", json.dumps(profile),
        "--memtotal-mb", "16384",
        "--request", "auto",
        "--floor-mb", "2048",
        "--overcommit", "false",
        "--device-profile", "standard",
    )
    assert standard.returncode == 0, standard.stderr
    standard_result = json.loads(standard.stdout)
    assert standard_result["resolved_memory_mb"] == 6144
    assert standard_result["overhead_mb"] == 512

    vfio = run(
        sys.executable, str(MEMORY),
        "--profile-json", json.dumps(profile),
        "--memtotal-mb", "16384",
        "--request", "auto",
        "--floor-mb", "6144",
        "--overcommit", "false",
        "--device-profile", "vfio",
    )
    assert vfio.returncode == 0, vfio.stderr
    vfio_result = json.loads(vfio.stdout)
    assert vfio_result["vfio_fixed_overhead_mb"] == 256
    assert vfio_result["overhead_mb"] == 768

    refused = run(
        sys.executable, str(MEMORY),
        "--profile-json", json.dumps(profile),
        "--memtotal-mb", "16384",
        "--request", "6144",
        "--floor-mb", "6144",
        "--overcommit", "true",
        "--device-profile", "vfio",
    )
    assert refused.returncode == 2 and "cannot be overcommitted" in refused.stderr


def domain_xml(name: str, bdfs: list[str], port: str = "5900") -> str:
    hostdevs = []
    for bdf in bdfs:
        domain, bus, tail = bdf.split(":")
        slot, function = tail.split(".")
        hostdevs.append(
            "<hostdev type='pci'><source><address "
            f"domain='0x{domain}' bus='0x{bus}' slot='0x{slot}' function='0x{function}'/>")
        hostdevs[-1] += "</source></hostdev>"
    return f"<domain><name>{name}</name><devices>{''.join(hostdevs)}<graphics type='spice' port='{port}'/></devices></domain>"


def test_vfio_registry() -> None:
    planned = ["0000:01:00.0", "0000:01:00.1"]
    safe_payload = {
        "planned_name": "win11clean-test",
        "planned_bdfs": planned,
        "domains": [{"name": "win11clean-test", "xml": domain_xml("win11clean-test", planned)}],
        "active_names": [],
        "spice_port": 5900,
        "mode": "start",
    }
    safe = run(sys.executable, str(VFIO_REGISTRY), stdin=json.dumps(safe_payload))
    assert safe.returncode == 0, safe.stderr

    collision = dict(safe_payload)
    collision["mode"] = "define"
    collision["domains"] = [{"name": "other", "xml": domain_xml("other", [planned[0]])}]
    refused = run(sys.executable, str(VFIO_REGISTRY), stdin=json.dumps(collision))
    assert refused.returncode == 2 and "already assigned" in refused.stderr

    port_collision = dict(safe_payload)
    port_collision["domains"] = [
        {"name": "win11clean-test", "xml": domain_xml("win11clean-test", planned)},
        {"name": "other", "xml": domain_xml("other", [], port="5900")},
    ]
    port_collision["active_names"] = ["other"]
    refused = run(sys.executable, str(VFIO_REGISTRY), stdin=json.dumps(port_collision))
    assert refused.returncode == 2 and "fixed SPICE port" in refused.stderr


def test_xml_contract() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        expected = root / "expected.xml"
        actual = root / "actual.xml"
        expected.write_text(domain_xml("vm", ["0000:01:00.0", "0000:01:00.1"]), encoding="utf-8")
        actual.write_text(domain_xml("vm", ["0000:01:00.0", "0000:01:00.1"]), encoding="utf-8")
        ok = run(sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual))
        assert ok.returncode == 0, ok.stderr
        actual.write_text(domain_xml("vm", ["0000:02:00.0", "0000:02:00.1"]), encoding="utf-8")
        drift = run(sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual))
        assert drift.returncode == 1 and "hostdev_bdfs" in drift.stderr

        expected.write_text(
            "<domain><devices><disk device='disk'><source file='/disk.qcow2'>"
            "<seclabel model='dac' relabel='no'/></source></disk></devices></domain>",
            encoding="utf-8",
        )
        actual.write_text(
            "<domain><devices><disk device='disk'><source file='/disk.qcow2'/>"
            "</disk></devices></domain>",
            encoding="utf-8",
        )
        missing_dac = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert missing_dac.returncode == 1 and "disk_dac_relabel" in missing_dac.stderr
        legacy_dac = run(
            sys.executable,
            str(XML_CONTRACT),
            "--expected",
            str(expected),
            "--actual",
            str(actual),
            "--allow-legacy-missing-dac-relabel",
        )
        assert legacy_dac.returncode == 0, legacy_dac.stderr

        actual.write_text(
            "<domain><devices><disk device='disk'><source file='/disk.qcow2'>"
            "<seclabel model='dac' relabel='yes'/></source></disk></devices></domain>",
            encoding="utf-8",
        )
        unsafe_dac = run(
            sys.executable,
            str(XML_CONTRACT),
            "--expected",
            str(expected),
            "--actual",
            str(actual),
            "--allow-legacy-missing-dac-relabel",
        )
        assert unsafe_dac.returncode == 1 and "disk_dac_relabel" in unsafe_dac.stderr

        actual.write_text(
            "<domain><devices><disk device='disk'><source file='/disk.qcow2'>"
            "<seclabel model='selinux' relabel='no'/></source></disk></devices></domain>",
            encoding="utf-8",
        )
        foreign_label = run(
            sys.executable,
            str(XML_CONTRACT),
            "--expected",
            str(expected),
            "--actual",
            str(actual),
            "--allow-legacy-missing-dac-relabel",
        )
        assert foreign_label.returncode == 1 and "disk_security_labels" in foreign_label.stderr

        expected.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='q35'>hvm</type>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        actual.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='pc-q35-11.0'>hvm</type>"
            "<firmware><feature enabled='yes' name='secure-boot'/>"
            "<feature enabled='no' name='enrolled-keys'/></firmware>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        canonical = run(sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual))
        assert canonical.returncode == 0, canonical.stderr

        actual.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='pc-i440fx-11.0'>hvm</type>"
            "<firmware><feature enabled='yes' name='secure-boot'/>"
            "<feature enabled='no' name='enrolled-keys'/></firmware>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        wrong_chipset = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert wrong_chipset.returncode == 1 and "machine" in wrong_chipset.stderr

        expected.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='pc-q35-10.0'>hvm</type>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        actual.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='pc-q35-11.0'>hvm</type>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        pinned_version = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert pinned_version.returncode == 1 and "machine" in pinned_version.stderr

        expected.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='q35'>hvm</type>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )

        actual.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='pc-q35-11.0'>hvm</type>"
            "<firmware><feature enabled='yes' name='secure-boot'/>"
            "<feature enabled='yes' name='enrolled-keys'/></firmware>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        secure_drift = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert secure_drift.returncode == 1 and "enrolled_keys" in secure_drift.stderr

        expected.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='q35'>hvm</type>"
            "<firmware><feature enabled='yes' name='secure-boot'/>"
            "<feature enabled='yes' name='enrolled-keys'/></firmware>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        actual.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='pc-q35-11.0'>hvm</type>"
            "<firmware><feature enabled='yes' name='secure-boot'/>"
            "<feature enabled='no' name='enrolled-keys'/></firmware>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        secure_required = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert secure_required.returncode == 1 and "enrolled_keys" in secure_required.stderr


def test_role_structure() -> None:
    role = ROOT / "roles/guest/tasks"
    text = "\n".join(path.read_text(encoding="utf-8") for path in role.glob("*.yml"))
    assert "ansible.builtin.shell" not in text
    assert "guest_confirm_destroy == guest_plan.name" in text
    assert "guest_confirm_reset == guest_plan.name" in text
    assert "guest_confirm_stop == guest_plan.name" in text
    create = (role / "create.yml").read_text(encoding="utf-8")
    validate = (role / "validate.yml").read_text(encoding="utf-8")
    state = (ROOT / "roles/guest/templates/state.yml.j2").read_text(encoding="utf-8")
    assert create.index("Require safe host-local SSH public keys") < create.index(
        "Validate an already-created guest instead of recreating it"
    )
    assert "cloud_init_user | default('')" in validate
    assert "cloud_init_ssh_public_keys | default([])" in validate
    assert "runtime key while reusing an old seed" in validate
    assert "cloud_init_ssh_public_keys:" in state
    assert "- -F\n              - qcow2" in create
    assert "guest_plan.base_path" not in "\n".join(
        line for line in create.splitlines() if "state: absent" in line
    )
    destroy = (role / "destroy.yml").read_text(encoding="utf-8")
    assert "guest_plan.base_path" not in destroy
    template = (ROOT / "roles/guest/templates/domain.xml.j2").read_text(encoding="utf-8")
    assert "<hostdev" in template
    assert "qemu:commandline" in template
    assert "guest_vfio.looking_glass_device" in template
    assert "org.qemu.guest_agent.0" in template
    main = (role / "main.yml").read_text(encoding="utf-8")
    assert "vfio.yml" in main
    assert "guest_plan.lock_path" in main
    start = (role / "start.yml").read_text(encoding="utf-8")
    assert "guest_plan.gpu_lock_path" in start
    assert "vfio-registry.yml" in start
    assert "guest_gpu_lock_release.rc != 0" in start


def main() -> int:
    tests = [
        test_standard_plan,
        test_vfio_plan,
        test_domain_templates,
        test_state_guard,
        test_memory,
        test_vfio_registry,
        test_xml_contract,
        test_role_structure,
    ]
    for test in tests:
        test()
    print("guest contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
