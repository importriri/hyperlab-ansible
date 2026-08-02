#!/usr/bin/env python3
"""Build one deterministic M7 service registration and recovery plan."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

SERVICE_RE = re.compile(r"^svc-[a-z0-9][a-z0-9-]*$")
MAC_RE = re.compile(r"^52:54:00(?::[0-9a-f]{2}){3}$")
EXPOSURE_RE = re.compile(r"^(tcp|udp)/([1-9][0-9]{0,4})$")
SERVICE_KEYS = {
    "schema_version",
    "id",
    "vm",
    "network_profile",
    "memory_reservation_mb",
    "backup_policy",
    "restore_policy",
    "dhcp",
    "exposures",
    "owner",
    "purpose",
}


class ServicePlanError(ValueError):
    """A checked-in service contract cannot become a safe runtime plan."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ServicePlanError(message)


def load_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ServicePlanError(f"{label} does not exist: {path}") from exc
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ServicePlanError(f"{label} cannot be read as YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ServicePlanError(f"{label} root must be a mapping")
    return data


def within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def derive_mac(name: str) -> str:
    digest = hashlib.sha256(f"hyperlab:{name}".encode()).digest()
    return "52:54:00:" + ":".join(f"{byte:02x}" for byte in digest[:3])


def validate_exposures(exposures: Any, allowlist: Any) -> list[str]:
    require(isinstance(exposures, list), "service exposures must be a list")
    require(all(isinstance(item, str) for item in exposures), "service exposures must contain strings")
    require(len(exposures) == len(set(exposures)), "service exposures contain duplicates")
    require(isinstance(allowlist, list), "service_lan_exposure_allowlist must be a list")
    for exposure in exposures:
        match = EXPOSURE_RE.fullmatch(exposure)
        require(match is not None, f"invalid service exposure {exposure!r}")
        require(int(match.group(2)) <= 65535, f"service exposure port exceeds 65535: {exposure}")
        require(exposure in allowlist, f"service exposure {exposure} is not reviewed in the LAN allowlist")
    return exposures


def build_plan(root: Path, spec_arg: str, store: Path) -> dict[str, Any]:
    root = root.resolve()
    specs_root = (root / "service-specs").resolve()
    vm_specs_root = (root / "vm-specs").resolve()
    store = store.resolve()
    spec_path = Path(spec_arg)
    spec_path = (root / spec_path).resolve() if not spec_path.is_absolute() else spec_path.resolve()
    require(within(spec_path, specs_root), "service_spec must resolve below service-specs/")
    require(spec_path.is_file() and not spec_path.is_symlink(), "service_spec must be one regular checked-in file")

    spec = load_mapping(spec_path, "service spec")
    require(set(spec) == SERVICE_KEYS, "service spec fields drift from schema v1")
    require(spec.get("schema_version") == 1, "service spec schema_version must be 1")
    service_id = spec.get("id")
    require(isinstance(service_id, str) and SERVICE_RE.fullmatch(service_id) is not None, "service id is invalid")
    require(spec_path.name == f"{service_id}.yml", "service spec filename must equal service id")
    vm_name = spec.get("vm")
    require(vm_name == service_id, "M7 requires service id and VM name to be identical")
    require(spec.get("network_profile") == "services", "service VMs must use network_profile: services")

    memory_mb = spec.get("memory_reservation_mb")
    require(
        isinstance(memory_mb, int) and not isinstance(memory_mb, bool) and memory_mb >= 512,
        "memory_reservation_mb must be an integer >= 512",
    )
    require(spec.get("backup_policy") in {"manual", "weekly"}, "unsupported service backup policy")
    require(spec.get("restore_policy") == "offline-only", "service restore policy must be offline-only")
    require(isinstance(spec.get("owner"), str) and spec["owner"], "service owner must be non-empty")
    require(isinstance(spec.get("purpose"), str) and spec["purpose"], "service purpose must be non-empty")

    vm_spec_path = (vm_specs_root / f"{vm_name}.yml").resolve()
    require(within(vm_spec_path, vm_specs_root), "linked VM spec escaped vm-specs/")
    vm = load_mapping(vm_spec_path, "linked VM spec")
    require(vm.get("name") == vm_name, "linked VM spec name differs from service VM")
    require(vm.get("network_profile") == "services", "linked service VM must use the services network")
    require(vm.get("lifecycle") == "permanent", "service VM lifecycle must be permanent")
    require(vm.get("device_profile") == "standard", "service VM must use the standard device profile")
    require(vm.get("memory_overcommit") is False, "service VM memory overcommit is forbidden")
    require(vm.get("autostart") is False, "M7 service VMs require operator-controlled start")
    require(vm.get("qemu_guest_agent") is True, "service VM requires QEMU Guest Agent")
    for key in ("looking_glass", "clipboard", "shared_folders"):
        require(vm.get(key) is False, f"service VM {key} must be false")
    require(vm.get("usb_allowlist") == [], "service VM USB allowlist must be empty")
    resources = vm.get("resources")
    require(isinstance(resources, dict), "linked VM resources must be a mapping")
    require(resources.get("memory_mb") == memory_mb, "service reservation must equal fixed VM memory")
    require(vm.get("backup_policy") == spec.get("backup_policy"), "service and VM backup policies differ")

    services = load_mapping(root / "group_vars/all/services.yml", "service contract")
    networks = load_mapping(root / "group_vars/all/networks.yml", "network contract")
    leases = services.get("service_dhcp_leases")
    require(isinstance(leases, list) and leases, "service_dhcp_leases must be a non-empty list")
    names: set[str] = set()
    macs: set[str] = set()
    ips: set[str] = set()
    selected: dict[str, Any] | None = None
    for index, lease in enumerate(leases):
        require(
            isinstance(lease, dict) and set(lease) == {"name", "mac", "ip"},
            f"service_dhcp_leases[{index}] must contain name, mac and ip",
        )
        name = lease.get("name")
        mac = lease.get("mac")
        ip = str(lease.get("ip"))
        require(isinstance(name, str) and SERVICE_RE.fullmatch(name) is not None, f"invalid service lease name {name!r}")
        require(isinstance(mac, str) and MAC_RE.fullmatch(mac) is not None, f"invalid service lease MAC {mac!r}")
        require(name not in names and mac not in macs and ip not in ips, "service leases contain a name, MAC or IP collision")
        names.add(name)
        macs.add(mac)
        ips.add(ip)
        if name == service_id:
            selected = {"name": name, "mac": mac, "ip": ip}
    require(selected is not None, f"service {service_id} has no reviewed DHCP lease")

    dhcp = spec.get("dhcp")
    require(isinstance(dhcp, dict) and set(dhcp) == {"mac", "ip"}, "service dhcp must contain mac and ip")
    requested_mac = dhcp.get("mac")
    requested_ip = str(dhcp.get("ip"))
    require(
        requested_mac == selected["mac"] and requested_ip == selected["ip"],
        "service spec DHCP identity differs from the reviewed lease",
    )
    require(requested_mac == derive_mac(vm_name), "service lease MAC differs from the deterministic guest MAC")

    domains = networks.get("network_domains")
    require(isinstance(domains, list), "network_domains must be a list")
    service_domain = next(
        (item for item in domains if isinstance(item, dict) and item.get("name") == "services"),
        None,
    )
    require(isinstance(service_domain, dict), "services network domain is missing")
    subnet = ipaddress.ip_network(str(service_domain.get("subnet")), strict=True)
    gateway = ipaddress.ip_address(str(service_domain.get("gateway")))
    address = ipaddress.ip_address(requested_ip)
    require(address in subnet and address != gateway, "service lease IP is outside the services subnet or equals its gateway")
    dynamic_start = ipaddress.ip_address(str(subnet.network_address + 100))
    dynamic_end = ipaddress.ip_address(str(subnet.network_address + 199))
    require(not (dynamic_start <= address <= dynamic_end), "service lease overlaps the dynamic DHCP range")
    require(
        address != subnet.network_address and address != subnet.broadcast_address,
        "service lease cannot use the subnet or broadcast address",
    )

    exposures = validate_exposures(spec.get("exposures"), services.get("service_lan_exposure_allowlist", []))
    return {
        "schema_version": 1,
        "id": service_id,
        "vm": vm_name,
        "owner": spec["owner"],
        "purpose": spec["purpose"],
        "network_profile": "services",
        "memory_reservation_mb": memory_mb,
        "backup_policy": spec["backup_policy"],
        "restore_policy": spec["restore_policy"],
        "dhcp": {"mac": requested_mac, "ip": requested_ip},
        "exposures": exposures,
        "spec_path": str(spec_path),
        "spec_sha256": sha256(spec_path),
        "vm_spec_path": str(vm_spec_path),
        "vm_spec_sha256": sha256(vm_spec_path),
        "disk_path": str(store / "permanent" / f"{vm_name}.qcow2"),
        "vm_state_path": str(store / "state" / "vms" / f"{vm_name}.yml"),
        "receipt_path": str(store / "state" / "services" / f"{service_id}.yml"),
        "receipt_new_path": str(store / "state" / "services" / f"{service_id}.yml.new"),
        "lock_path": str(store / "state" / "locks" / f"service-{service_id}.lock"),
        "backup_dir": str(store / "snapshots" / "services" / service_id),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--store", required=True)
    args = parser.parse_args()
    try:
        plan = build_plan(Path(args.root), args.spec, Path(args.store))
    except (OSError, ValueError) as exc:
        print(f"service plan refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(plan, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
