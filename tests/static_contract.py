#!/usr/bin/env python3
"""Fast, host-independent invariants for the public pipeline contract."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_mapping(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        errors.append(f"{path.relative_to(ROOT)} cannot be parsed: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{path.relative_to(ROOT)} root must be a mapping")
        return {}
    return data


def collect_errors(root: Path = ROOT) -> list[str]:
    global ROOT
    ROOT = root.resolve()
    errors: list[str] = []

    def check(ok: bool, message: str) -> None:
        if not ok:
            errors.append(message)

    hardware_path = ROOT / "group_vars/all/hardware.yml"
    networks_path = ROOT / "group_vars/all/networks.yml"
    bricks_path = ROOT / "group_vars/all/bricks.yml"
    hardware = load_mapping(hardware_path, errors)
    networks = load_mapping(networks_path, errors)
    bricks = load_mapping(bricks_path, errors)

    check(hardware.get("host_profile") == "auto", "physical laptop selector must be host_profile: auto")
    check("host_profiles" in hardware, "physical laptop profiles must be named host_profiles")
    check("device_profile" not in hardware, "device_profile belongs to VM specs, never host hardware")
    check("hardware_profile" not in hardware_path.read_text(), "legacy hardware_profile key must not return")

    profiles = hardware.get("host_profiles", {})
    check(set(profiles) == {"nitro-3060", "predator-3070"}, "both reviewed laptop profiles must exist")
    for name, profile in profiles.items():
        vfio_ids = profile.get("vfio_ids", [])
        check(len(vfio_ids) == 2, f"{name} must bind GPU and HDMI audio")
        check(all(re.fullmatch(r"[0-9a-f]{4}:[0-9a-f]{4}", str(x)) for x in vfio_ids), f"bad PCI ID in {name}")
        check("desktop" in profile, f"{name} must declare per-machine input")
        memory = profile.get("memory", {})
        expected_memory = {"host_reserved_mb", "qemu_overhead_per_domain_mb", "services_reserved_mb", "vfio_fixed_overhead_mb", "max_auto_memory_mb", "standard_overcommit_ratio"}
        check(set(memory) == expected_memory, f"{name} must declare the complete memory budget contract")
        for key in expected_memory - {"standard_overcommit_ratio"}:
            check(isinstance(memory.get(key), int) and memory.get(key, -1) >= 0, f"{name}.{key} must be a non-negative integer")
        ratio = memory.get("standard_overcommit_ratio")
        check(isinstance(ratio, (int, float)) and not isinstance(ratio, bool), f"{name} overcommit ratio must be numeric")
        if isinstance(ratio, (int, float)) and not isinstance(ratio, bool):
            check(1.0 <= float(ratio) <= 2.0, f"{name} overcommit ratio must stay between 1.0 and 2.0")
        check("memory_total_mb" not in profile, f"{name} must not hardcode a RAM total")

    image_schema = load_mapping(ROOT / "schemas/image-manifest.v1.yml", errors)
    spec_schema = load_mapping(ROOT / "schemas/vm-spec.v1.yml", errors)
    image_schema_text = (ROOT / "schemas/image-manifest.v1.yml").read_text()
    spec_schema_text = (ROOT / "schemas/vm-spec.v1.yml").read_text()
    check("device_profile" in image_schema_text and "host_profile" not in image_schema_text, "image defaults must use device_profile only")
    check("device_profile" in spec_schema_text and "host_profile" not in spec_schema_text, "VM specs must use device_profile only")
    check("min_items" in spec_schema_text and "unique_items" in spec_schema_text, "schema vocabulary must constrain lists")
    check("instance_policy" in image_schema.get("fields", {}), "image schema must make instance policy explicit")

    domains = networks.get("network_domains", [])
    check([d.get("name") for d in domains] == ["clean", "dirty", "dev", "lab", "services"], "domain order/coverage drift")
    check([d.get("name") for d in domains if d.get("forward") == "isolated"] == ["lab"], "lab must be the only isolated domain")
    check("services" not in networks.get("gpu_trust_levels", {}), "services must never receive the GPU")

    lab = yaml.safe_load((ROOT / "playbooks/lab.yml").read_text())
    lab_roles = [str(x) for x in lab[0]["roles"]]
    check(lab_roles == ["base", "hardware_probe", "kvm_host", "vfio_boot", "network_domains", "lab_isolation", "gpu_handoff"], "lab role order drift")

    vfio_defaults = (ROOT / "roles/vfio_boot/defaults/main.yml").read_text()
    check("hardware_probe_vfio_ids_csv" not in vfio_defaults, "vfio defaults must not embed cross-role facts")
    check(vfio_defaults.count("bind_vfio_devices: true") == 1, "exactly one boot profile must request VFIO binding")

    hardware_tasks = (ROOT / "roles/hardware_probe/tasks/main.yml").read_text()
    check("lspci" in hardware_tasks and "-Dn" in hardware_tasks, "hardware probe must use numeric PCI discovery")
    check("when: host_profile == 'auto'" in hardware_tasks, "unknown-machine rescue must be limited to automatic selection")
    check("Unknown host_profile={{ host_profile }}" in hardware_tasks, "explicit unknown host profile must keep its own error")
    check("requested_host_profile:" in hardware_tasks, "unknown report must name the requested host profile")
    check("gpu_pci:" in hardware_tasks and "gpu_audio_pci:" in hardware_tasks and "cpu_threads:" in hardware_tasks, "preflight report must collect PCI addresses and CPU threads")
    check("hardware_probe_vfio_devices" in hardware_tasks, "preflight must retain the ID-to-address mapping")

    network_tasks = (ROOT / "roles/network_domains/tasks/main.yml").read_text()
    check("net-dumpxml --inactive" in network_tasks, "network drift must compare persistent XML")
    check("network_domains_reconcile" in network_tasks, "network role must reconcile changed definitions")
    check("network_domains_restart_changed" in network_tasks, "active network restart must be explicit")

    looking_tasks = (ROOT / "roles/looking_glass/tasks/main.yml").read_text()
    looking_handlers = (ROOT / "roles/looking_glass/handlers/main.yml").read_text()
    looking_defaults = load_mapping(ROOT / "roles/looking_glass/defaults/main.yml", errors)
    check("stat.ischr" in looking_tasks, "kvmfr must be verified as a character device")
    check("failed_when: looking_glass_unload.rc != 0" in looking_handlers, "kvmfr resize must fail when unload fails")
    check("rev-parse" in looking_tasks and "resolved_commit:" in looking_tasks, "Looking Glass stamp must record the resolved full SHA")
    check("--abbrev=10" in looking_tasks, "Looking Glass build identity must use the client's ten-digit SHA abbreviation")
    lg_commit = str(looking_defaults.get("looking_glass_commit", ""))
    lg_build = str(looking_defaults.get("looking_glass_build", ""))
    check(re.fullmatch(r"[0-9a-f]{40}", lg_commit) is not None, "Looking Glass checkout pin must be the reviewed full commit")
    check(lg_build.endswith(lg_commit[:10]), "Looking Glass build string must end with the reviewed ten-digit commit selector")

    client = (ROOT / "roles/looking_glass/templates/client.ini.j2").read_text().splitlines()
    check(not any(line.startswith("#") for line in client), "Looking Glass B7 comments must use semicolons")
    check(any(line == "port={{ looking_glass_spice_port }}" for line in client), "SPICE port must remain templated")

    requires = bricks.get("brick_requires", {})
    role_names = {d.name for d in (ROOT / "roles").iterdir() if d.is_dir()}
    check(set(requires) <= role_names, "brick_requires names a role that does not exist")
    check(set(requires) == role_names - {"brick_guard"}, "every brick must appear in the graph")
    for brick, prerequisites in requires.items():
        check(set(prerequisites) <= set(requires), f"{brick} requires an unknown brick")
        check(brick not in prerequisites, f"{brick} requires itself")
    check(set(bricks.get("brick_playbooks", {})) == set(requires), "every brick must name its mounting playbook")
    check(requires.get("looking_glass") == ["desktop", "kvm_host"], "Looking Glass needs desktop and kvm_host")

    guard_tasks = (ROOT / "roles/brick_guard/tasks/main.yml").read_text()
    check("brick_guard_brick in brick_requires" in guard_tasks, "brick_guard must reject an unknown brick name")
    check("brick_guard_brick in brick_playbooks" in guard_tasks, "brick_guard must reject a brick without a playbook mapping")
    check("default([])" not in guard_tasks, "brick_guard must not turn an unknown brick into an empty prerequisite list")

    resolved: set[str] = set()
    for _ in range(len(requires) + 1):
        resolved |= {brick for brick, prereqs in requires.items() if set(prereqs) <= resolved}
    check(resolved == set(requires), "the brick graph has a cycle")

    readme = (ROOT / "README.md").read_text()
    check("brick_requires" in readme and "brick_playbooks" in readme and "stamp" in readme.lower(), "README extension contract must include graph, playbook map and stamp")

    check(requires.get("image_store") == ["kvm_host"], "the image store belongs to the brick that owns libvirt")
    store_play = yaml.safe_load((root / "playbooks/image-store.yml").read_text())[0]
    check(any(isinstance(r, dict) and r.get("role") == "brick_guard" for r in store_play["roles"]), "image-store.yml must mount brick_guard before the brick")

    verify_text = (root / "verify.sh").read_text()
    ci_text = (root / ".github/workflows/ci.yml").read_text()
    for text, where in ((verify_text, "verify.sh"), (ci_text, "CI")):
        check("tests/*_contract.py" in text, f"{where} must discover structural contracts")
        check("tests/*-refusals.yml" in text, f"{where} must discover refusal suites")

    return errors


def main() -> int:
    errors = collect_errors()
    if errors:
        print("STATIC CONTRACT FAILED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("static contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
