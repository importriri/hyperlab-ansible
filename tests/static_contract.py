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


def role_name(entry: Any) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return str(entry.get("role"))
    return "<invalid>"


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
    looking_contract_path = ROOT / "group_vars/all/looking-glass.yml"
    runtime_identity_path = ROOT / "host_vars/localhost.yml"
    hardware = load_mapping(hardware_path, errors)
    networks = load_mapping(networks_path, errors)
    bricks = load_mapping(bricks_path, errors)
    looking_contract = load_mapping(looking_contract_path, errors)
    runtime_identity = load_mapping(runtime_identity_path, errors)

    check(
        runtime_identity == {
            "hyperlab_qemu_user_declared": "libvirt-qemu",
            "hyperlab_qemu_group_declared": "libvirt-qemu",
            "hyperlab_swtpm_user_declared": "tss",
            "hyperlab_swtpm_group_declared": "tss",
        },
        "localhost must declare the reviewed Arch libvirt and swtpm identities",
    )

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
    trust_levels = networks.get("gpu_trust_levels", {})
    domain_profiles = networks.get("gpu_domain_profiles", {})
    check("services" not in trust_levels, "services must never receive the GPU")
    check(set(domain_profiles) == {"win11clean-valley", "win11dirty-disposable"}, "reviewed VFIO domain map drift")
    check(set(domain_profiles.values()) <= set(trust_levels), "every VFIO domain must map to a reviewed GPU trust level")
    check("services" not in domain_profiles.values(), "no VFIO domain may map to services")
    for vm_name, network_name in domain_profiles.items():
        spec_path = ROOT / "vm-specs" / f"{vm_name}.yml"
        spec = load_mapping(spec_path, errors)
        check(spec.get("device_profile") == "vfio", f"{vm_name} must remain a VFIO spec")
        check(spec.get("network_profile") == network_name, f"{vm_name} trust mapping must equal its VM network")
        check(spec.get("looking_glass") is True, f"{vm_name} must request Looking Glass")
    rotation = (ROOT / "roles/gpu_handoff/templates/rotation.j2").read_text()
    domain_allowlist = (ROOT / "roles/gpu_handoff/templates/domains.j2").read_text()
    gpu_tasks = (ROOT / "roles/gpu_handoff/tasks/main.yml").read_text()
    gpu_hook = (ROOT / "roles/gpu_handoff/files/qemu").read_text()
    check("gpu_trust_levels.items()" in rotation, "GPU trust rotation must render security-domain levels")
    check("gpu_domain_profiles.items()" not in rotation, "GPU trust rotation must not embed VM names")
    check("gpu_domain_profiles.items()" in domain_allowlist, "GPU domain allowlist must render exact VM names")
    check("/etc/gpu-handoff/domains" in gpu_tasks, "GPU handoff role must install the exact domain allowlist")
    check("GPU_HANDOFF_DOMAINS" in gpu_hook, "GPU hook must consume the exact domain allowlist")

    foundation = yaml.safe_load((ROOT / "playbooks/foundation.yml").read_text())
    foundation_roles = [role_name(x) for x in foundation[0]["roles"]]
    check(
        foundation_roles == [
            "base", "hardware_probe", "kvm_host", "vfio_boot",
            "network_domains", "lab_isolation", "gpu_handoff", "brick_guard",
            "bootstrap_storage", "brick_guard", "image_store",
        ],
        "foundation role order drift",
    )
    lab = yaml.safe_load((ROOT / "playbooks/lab.yml").read_text())
    check(lab[0].get("import_playbook") == "foundation.yml", "lab must import the complete foundation first")
    lab_roles = [role_name(x) for x in lab[1]["roles"]]
    check(lab_roles == ["desktop", "brick_guard", "looking_glass"], "lab cockpit role order drift")

    vfio_defaults = (ROOT / "roles/vfio_boot/defaults/main.yml").read_text()
    vfio_tasks = (ROOT / "roles/vfio_boot/tasks/main.yml").read_text()
    check("hardware_probe_vfio_ids_csv" not in vfio_defaults, "vfio defaults must not embed cross-role facts")
    check(vfio_defaults.count("bind_vfio_devices: true") == 1, "exactly one boot profile must request VFIO binding")
    check("default Arch-Linux-Hardened-Vfio.conf" in vfio_tasks, "the managed loader default must be VFIO")

    hardware_tasks = (ROOT / "roles/hardware_probe/tasks/main.yml").read_text()
    check("lspci" in hardware_tasks and "-Dn" in hardware_tasks, "hardware probe must use numeric PCI discovery")
    check("when: host_profile == 'auto'" in hardware_tasks, "unknown-machine rescue must be limited to automatic selection")
    check("Unknown host_profile={{ host_profile }}" in hardware_tasks, "explicit unknown host profile must keep its own error")
    check("requested_host_profile:" in hardware_tasks, "unknown report must name the requested host profile")
    check("gpu_pci:" in hardware_tasks and "gpu_audio_pci:" in hardware_tasks and "cpu_threads:" in hardware_tasks, "preflight report must collect PCI addresses and CPU threads")
    check("hardware_probe_vfio_devices" in hardware_tasks, "preflight must retain the ID-to-address mapping")

    kvm_packages = load_mapping(ROOT / "roles/kvm_host/defaults/main.yml", errors).get(
        "kvm_host_packages", []
    )
    check(
        "swtpm" in kvm_packages,
        "the KVM foundation must create the swtpm runtime identity before image_store",
    )

    guest_packages = load_mapping(ROOT / "group_vars/all/guest.yml", errors).get(
        "guest_required_packages", []
    )
    check(
        {
            "qemu-ui-spice-core",
            "qemu-chardev-spice",
            "qemu-audio-spice",
        } <= set(guest_packages),
        "SPICE guests require the complete split QEMU UI, chardev and audio modules",
    )

    network_tasks = (ROOT / "roles/network_domains/tasks/main.yml").read_text()
    check("net-dumpxml --inactive" in network_tasks, "network drift must compare persistent XML")
    check("network_domains_reconcile" in network_tasks, "network role must reconcile changed definitions")
    check("network_domains_restart_changed" in network_tasks, "active network restart must be explicit")
    check("net-define" in network_tasks, "network reconciliation must update persistent XML with virsh net-define")
    check("command: define" not in network_tasks, "virt_net define must not silently skip existing networks")

    looking_tasks = (ROOT / "roles/looking_glass/tasks/main.yml").read_text()
    looking_handlers = (ROOT / "roles/looking_glass/handlers/main.yml").read_text()
    looking_defaults = load_mapping(ROOT / "roles/looking_glass/defaults/main.yml", errors)
    check("stat.ischr" in looking_tasks, "kvmfr must be verified as a character device")
    check("failed_when: looking_glass_unload.rc != 0" in looking_handlers, "kvmfr resize must fail when unload fails")
    check("rev-parse" in looking_tasks and "resolved_commit:" in looking_tasks, "Looking Glass stamp must record the resolved full SHA")
    check("--abbrev=10" in looking_tasks, "Looking Glass build identity must use the client's ten-digit SHA abbreviation")
    lg_commit = str(looking_contract.get("hyperlab_looking_glass_commit", ""))
    lg_build = str(looking_contract.get("hyperlab_looking_glass_build", ""))
    check(re.fullmatch(r"[0-9a-f]{40}", lg_commit) is not None, "Looking Glass checkout pin must be the reviewed full commit")
    check(lg_build.endswith(lg_commit[:10]), "Looking Glass build string must end with the reviewed ten-digit commit selector")
    check(looking_defaults.get("looking_glass_commit") == "{{ hyperlab_looking_glass_commit }}", "Looking Glass role must consume the shared commit")
    check(looking_defaults.get("looking_glass_build") == "{{ hyperlab_looking_glass_build }}", "Looking Glass role must consume the shared build")
    check(looking_contract.get("hyperlab_looking_glass_device") == "/dev/kvmfr0", "reviewed Looking Glass transport must remain kvmfr0")
    check(looking_contract.get("hyperlab_looking_glass_spice_host") == "127.0.0.1", "SPICE input must remain loopback-only")
    check(looking_contract.get("hyperlab_looking_glass_spice_port") == 5900, "SPICE input must remain fixed at 5900")

    client = (ROOT / "roles/looking_glass/templates/client.ini.j2").read_text().splitlines()
    check(not any(line.startswith("#") for line in client), "Looking Glass B7 comments must use semicolons")
    check(any(line == "port={{ looking_glass_spice_port }}" for line in client), "SPICE port must remain templated")

    guest_template = (ROOT / "roles/guest/templates/domain.xml.j2").read_text()
    check(
        '<seclabel model="dac" relabel="no"/>' in guest_template,
        "managed disks must refuse libvirt DAC relabel of sealed backing chains",
    )
    check("<hostdev" in guest_template and "managed=\"yes\"" in guest_template, "VFIO XML must use managed PCI hostdevs")
    check("qemu:commandline" in guest_template and "guest_vfio.looking_glass_device" in guest_template, "VFIO XML must use the reviewed kvmfr command line")
    check("autoport=\"no\"" in guest_template and "guest_vfio.spice_port" in guest_template, "VFIO XML must pin the SPICE input endpoint")

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
    brick_catalog = (ROOT / "docs/brick-catalog.md").read_text()
    playbook_map = (ROOT / "docs/playbooks.md").read_text()
    check("docs/brick-catalog.md" in readme and "docs/playbooks.md" in readme,
          "README must route details to the grouped operator documentation")
    check("group_vars/all/bricks.yml" in readme and "stamp" in brick_catalog.lower(),
          "extension documentation must retain graph and stamp ownership")
    check("foundation.yml" in playbook_map and "lab.yml" in playbook_map,
          "playbook documentation must explain both broad targets")

    check(requires.get("bootstrap_storage") == ["kvm_host"],
          "bootstrap storage validation belongs to the brick that owns libvirt")
    check(requires.get("image_store") == ["kvm_host", "bootstrap_storage"],
          "the image store must require the verified stage-1 storage hand-off")
    store_play = yaml.safe_load((root / "playbooks/image-store.yml").read_text())[0]
    store_roles = [entry.get("role") if isinstance(entry, dict) else entry for entry in store_play["roles"]]
    check(store_roles == ["brick_guard", "bootstrap_storage", "brick_guard", "image_store"],
          "image-store.yml must validate bootstrap storage before the image-store brick")

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
