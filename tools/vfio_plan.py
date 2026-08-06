#!/usr/bin/env python3
"""Validate the host-local VFIO contract and emit XML-ready device data."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

PCI_RE = re.compile(
    r"^(?:(?P<domain>[0-9a-fA-F]{4}):)?"
    r"(?P<bus>[0-9a-fA-F]{2}):(?P<slot>[0-9a-fA-F]{2})\."
    r"(?P<function>[0-7])$"
)


class VfioError(ValueError):
    """The selected host cannot safely satisfy a VFIO plan."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VfioError(message)


def load_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise VfioError(f"{label} does not exist: {path}") from exc
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise VfioError(f"{label} cannot be read as YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise VfioError(f"{label} root must be a mapping")
    return data


def parse_json(value: str, label: str) -> dict[str, Any]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise VfioError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise VfioError(f"{label} root must be a mapping")
    return data


def parse_bdf(value: Any, label: str) -> dict[str, Any]:
    require(isinstance(value, str), f"{label} must be a PCI BDF string")
    match = PCI_RE.fullmatch(value)
    require(match is not None, f"{label} is not a canonical PCI BDF: {value!r}")
    assert match is not None
    domain = (match.group("domain") or "0000").lower()
    bus = match.group("bus").lower()
    slot = match.group("slot").lower()
    function = match.group("function").lower()
    return {
        "bdf": f"{domain}:{bus}:{slot}.{function}",
        "short_bdf": f"{bus}:{slot}.{function}",
        "domain": domain,
        "bus": bus,
        "slot": slot,
        "function": function,
        "xml_domain": f"0x{domain}",
        "xml_bus": f"0x{bus}",
        "xml_slot": f"0x{slot}",
        "xml_function": f"0x{function}",
    }


def power_of_two(value: int) -> bool:
    return value > 0 and (value & (value - 1)) == 0


def cpu_id_list(value: Any, label: str) -> list[int]:
    require(isinstance(value, list) and value, f"{label} must be a non-empty list")
    require(
        all(isinstance(item, int) and not isinstance(item, bool) and item >= 0 for item in value),
        f"{label} must contain non-negative CPU integers",
    )
    require(len(set(value)) == len(value), f"{label} contains duplicate CPU IDs")
    return value


def build_cpu_pinning(
    profile: dict[str, Any],
    report: dict[str, Any],
    guest_vcpus: Any,
) -> dict[str, Any]:
    raw = profile.get("cpu_pinning")
    if raw in (None, {}):
        return {"enabled": False}
    require(isinstance(raw, dict), "cpu_pinning must be a mapping")
    host_threads = raw.get("host_cpu_threads")
    report_threads = report.get("cpu_threads")
    require(
        isinstance(host_threads, int) and not isinstance(host_threads, bool) and host_threads > 0,
        "cpu_pinning.host_cpu_threads must be a positive integer",
    )
    require(
        isinstance(report_threads, int) and not isinstance(report_threads, bool),
        "hardware report cpu_threads must be an integer",
    )
    require(
        report_threads == host_threads,
        "reviewed CPU pinning does not match the detected host thread count",
    )
    require(
        isinstance(guest_vcpus, int) and not isinstance(guest_vcpus, bool),
        "guest vCPU count must be an integer",
    )
    plans = raw.get("plans")
    require(isinstance(plans, dict), "cpu_pinning.plans must be a mapping")
    selected = plans.get(str(guest_vcpus))
    require(
        isinstance(selected, dict),
        f"no reviewed CPU pinning plan exists for {guest_vcpus} vCPUs",
    )
    vcpu_pins = cpu_id_list(
        selected.get("vcpu_pins"),
        f"cpu_pinning.plans.{guest_vcpus}.vcpu_pins",
    )
    emulator_cpus = cpu_id_list(
        selected.get("emulator_cpus"),
        f"cpu_pinning.plans.{guest_vcpus}.emulator_cpus",
    )
    iothread_cpus = cpu_id_list(
        selected.get("iothread_cpus"),
        f"cpu_pinning.plans.{guest_vcpus}.iothread_cpus",
    )
    require(
        len(vcpu_pins) == guest_vcpus,
        "reviewed vCPU pin count differs from the guest vCPU count",
    )
    all_ids = vcpu_pins + emulator_cpus + iothread_cpus
    require(
        all(cpu_id < host_threads for cpu_id in all_ids),
        "reviewed CPU pinning names a CPU outside the detected host",
    )
    require(
        set(vcpu_pins).isdisjoint(emulator_cpus)
        and set(vcpu_pins).isdisjoint(iothread_cpus),
        "guest CPU pins must be disjoint from emulator and I/O CPU sets",
    )
    topology = selected.get("topology")
    require(isinstance(topology, dict), "cpu_pinning.topology must be a mapping")
    required_topology = ("sockets", "dies", "cores", "threads")
    require(set(topology) == set(required_topology), "CPU topology fields are incomplete")
    require(
        all(
            isinstance(topology[key], int)
            and not isinstance(topology[key], bool)
            and topology[key] > 0
            for key in required_topology
        ),
        "CPU topology values must be positive integers",
    )
    require(
        topology["sockets"]
        * topology["dies"]
        * topology["cores"]
        * topology["threads"]
        == guest_vcpus,
        "CPU topology product differs from the guest vCPU count",
    )
    return {
        "enabled": True,
        "vcpu_pins": [
            {"vcpu": index, "cpuset": str(cpu_id)}
            for index, cpu_id in enumerate(vcpu_pins)
        ],
        "emulator_cpuset": ",".join(str(item) for item in emulator_cpus),
        "iothread_cpuset": ",".join(str(item) for item in iothread_cpus),
        "topology": topology,
    }


def build_vfio_plan(
    plan: dict[str, Any],
    report: dict[str, Any],
    profiles: dict[str, Any],
    trust_levels: dict[str, Any],
    lg_build: str,
    lg_device: str,
    lg_shm_mb: int,
    spice_host: str,
    spice_port: int,
) -> dict[str, Any]:
    require(plan.get("device_profile") == "vfio", "VFIO plan requires device_profile=vfio")
    require(isinstance(plan.get("looking_glass"), bool),
            "VFIO plan needs a boolean looking_glass field")
    require(plan.get("memory_overcommit") is False, "VFIO memory overcommit must be disabled")
    require(plan.get("autostart") is False, "VFIO autostart must be disabled")

    host_profile = report.get("host_profile")
    require(isinstance(host_profile, str) and host_profile in profiles,
            "hardware report names an unknown host profile")
    profile = profiles[host_profile]
    require(isinstance(profile, dict), "selected host profile must be a mapping")
    reviewed_ids = profile.get("vfio_ids")
    require(isinstance(reviewed_ids, list) and len(reviewed_ids) == 2
            and all(isinstance(item, str) for item in reviewed_ids),
            "selected host profile must review exactly GPU and audio PCI IDs")

    devices = report.get("vfio_devices")
    require(isinstance(devices, list) and len(devices) == 2,
            "hardware report must contain exactly GPU and audio VFIO devices")
    report_ids = [item.get("id") if isinstance(item, dict) else None for item in devices]
    require(report_ids == reviewed_ids,
            "hardware report VFIO IDs differ from the selected reviewed profile")

    gpu = parse_bdf(report.get("gpu_pci"), "hardware report gpu_pci")
    audio = parse_bdf(report.get("gpu_audio_pci"), "hardware report gpu_audio_pci")
    require(gpu["bdf"] != audio["bdf"], "GPU and audio BDFs must be distinct")
    require((gpu["domain"], gpu["bus"], gpu["slot"]) ==
            (audio["domain"], audio["bus"], audio["slot"]),
            "GPU and audio functions must share one PCI slot")
    require(gpu["function"] == "0" and audio["function"] == "1",
            "reviewed GPU topology must be function 0 plus HDMI audio function 1")

    reported_devices = [parse_bdf(item.get("pci"), "hardware report vfio_devices[].pci")
                        for item in devices]
    require([item["bdf"] for item in reported_devices] == [gpu["bdf"], audio["bdf"]],
            "hardware report summary and VFIO device list disagree")

    network = plan.get("network_profile")
    require(isinstance(network, str) and network in trust_levels,
            f"VFIO network {network!r} has no GPU trust level")
    require(network != "services", "services domains can never own the GPU")
    trust_level = trust_levels[network]
    require(isinstance(trust_level, int) and not isinstance(trust_level, bool) and trust_level >= 0,
            "GPU trust level must be a non-negative integer")

    require(spice_host == "127.0.0.1", "VFIO SPICE recovery must stay loopback-only")
    require(spice_port == 5900, "VFIO recovery console requires fixed SPICE port 5900")

    cpu_pinning = build_cpu_pinning(profile, report, plan.get("vcpus"))
    looking_glass = plan["looking_glass"]
    required_build = plan.get("looking_glass_host_build_required")
    if looking_glass:
        require(plan.get("os_family") == "windows",
                "Looking Glass is supported only by reviewed Windows images")
        require(isinstance(required_build, str) and required_build == lg_build,
                "image Looking Glass host build differs from the pinned host client build")
        require(lg_device == "/dev/kvmfr0",
                "M4 supports the reviewed /dev/kvmfr0 transport only")
        require(power_of_two(lg_shm_mb) and 32 <= lg_shm_mb <= 512,
                "Looking Glass shared memory must be a reviewed power of two from 32 to 512 MiB")
        lg_bytes = lg_shm_mb * 1024 * 1024
    else:
        require(plan.get("os_family") == "linux",
                "Windows VFIO guests require Looking Glass; only Linux may use SPICE-only VFIO")
        require(required_build in (None, ""),
                "SPICE-only Linux VFIO must not carry a Looking Glass build pin")
        lg_build = None
        lg_device = None
        lg_shm_mb = None
        lg_bytes = None

    return {
        "schema_version": 1,
        "host_profile": host_profile,
        "gpu": gpu,
        "audio": audio,
        "devices": [gpu, audio],
        "network_profile": network,
        "trust_level": trust_level,
        "cpu_pinning": cpu_pinning,
        "looking_glass_enabled": looking_glass,
        "looking_glass_build": lg_build,
        "looking_glass_device": lg_device,
        "looking_glass_shm_mb": lg_shm_mb,
        "looking_glass_shm_bytes": lg_bytes,
        "spice_host": spice_host,
        "spice_port": spice_port,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--profiles-json", required=True)
    parser.add_argument("--trust-levels-json", required=True)
    parser.add_argument("--looking-glass-build", required=True)
    parser.add_argument("--looking-glass-device", required=True)
    parser.add_argument("--looking-glass-shm-mb", required=True, type=int)
    parser.add_argument("--spice-host", required=True)
    parser.add_argument("--spice-port", required=True, type=int)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = json.load(sys.stdin)
        if not isinstance(plan, dict):
            raise VfioError("guest plan JSON root must be a mapping")
        report = load_mapping(Path(args.report), "hardware profile report")
        profiles = parse_json(args.profiles_json, "host profiles")
        trust_levels = parse_json(args.trust_levels_json, "GPU trust levels")
        result = build_vfio_plan(
            plan,
            report,
            profiles,
            trust_levels,
            args.looking_glass_build,
            args.looking_glass_device,
            args.looking_glass_shm_mb,
            args.spice_host,
            args.spice_port,
        )
    except (OSError, json.JSONDecodeError, VfioError) as exc:
        print(f"VFIO plan refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
