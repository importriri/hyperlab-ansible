#!/usr/bin/env python3
"""Build a deterministic, side-effect-free plan for one Hyperlab VM."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import uuid
from pathlib import Path
from typing import Any

import yaml

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
IMAGE_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
LG_BUILD_RE = re.compile(r"^B[0-9]+-[0-9]+-g[0-9a-f]{10}$")
UUID_NAMESPACE = uuid.UUID("c18dd2cb-f9d3-4d27-8f90-f2f54dbef5b6")


class PlanError(ValueError):
    """A checked-in contract cannot be turned into a safe guest plan."""


def load_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PlanError(f"{label} does not exist: {path}") from exc
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise PlanError(f"{label} cannot be read as YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise PlanError(f"{label} root must be a mapping")
    return data


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PlanError(message)


def derive_mac(name: str) -> str:
    digest = hashlib.sha256(f"hyperlab:{name}".encode()).digest()
    return "52:54:00:" + ":".join(f"{byte:02x}" for byte in digest[:3])


def within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def strict_bool(mapping: dict[str, Any], key: str, label: str) -> bool:
    value = mapping.get(key)
    require(isinstance(value, bool), f"{label}.{key} must be boolean")
    return value


def build_plan(root: Path, spec_arg: str, store: Path) -> dict[str, Any]:
    root = root.resolve()
    specs_root = (root / "vm-specs").resolve()
    images_root = (root / "images").resolve()
    store = store.resolve()

    spec_path = Path(spec_arg)
    spec_path = (root / spec_path).resolve() if not spec_path.is_absolute() else spec_path.resolve()
    require(within(spec_path, specs_root), "guest_spec must resolve below vm-specs/")

    spec = load_mapping(spec_path, "VM spec")
    require(spec.get("schema_version") == 1, "VM spec schema_version must be 1")
    name = spec.get("name")
    require(isinstance(name, str) and bool(NAME_RE.fullmatch(name)), "VM name is invalid")
    require(spec_path.name == f"{name}.yml", "VM spec filename must equal spec.name")

    image_id = spec.get("image")
    require(isinstance(image_id, str) and bool(IMAGE_RE.fullmatch(image_id)),
            "spec.image must be a valid image id")
    manifest_path = (images_root / f"{image_id}.yml").resolve()
    require(within(manifest_path, images_root), "image manifest escaped images/")
    manifest = load_mapping(manifest_path, "image manifest")
    require(manifest.get("schema_version") == 1, "image manifest schema_version must be 1")
    require(manifest.get("id") == image_id, "manifest id must equal spec.image")
    require(manifest.get("status") == "sealed", f"image {image_id} is not sealed")
    sha256 = manifest.get("sha256")
    require(isinstance(sha256, str) and re.fullmatch(r"[a-f0-9]{64}", sha256) is not None,
            f"sealed image {image_id} needs a lowercase sha256")
    require(manifest.get("format") == "qcow2", "guest lifecycle supports qcow2 bases only")

    filename = manifest.get("filename")
    require(isinstance(filename, str) and filename == Path(filename).name and filename.endswith(".qcow2"),
            "sealed qcow2 filename must be one basename ending in .qcow2")

    lifecycle = spec.get("lifecycle")
    require(lifecycle in {"disposable", "permanent"}, "unsupported lifecycle")
    device_profile = spec.get("device_profile")
    require(device_profile in {"standard", "vfio"}, "unsupported device_profile")

    supports = manifest.get("supports", {})
    require(isinstance(supports, dict), "manifest.supports must be a mapping")
    require(supports.get(device_profile) is True,
            f"image {image_id} does not support {device_profile} guests")
    qemu_guest_agent = strict_bool(spec, "qemu_guest_agent", "spec")
    require(not qemu_guest_agent or supports.get("qemu_guest_agent") is True,
            f"image {image_id} does not support the requested QEMU Guest Agent")

    network = spec.get("network_profile")
    allowlist = manifest.get("network_allowlist", [])
    require(isinstance(network, str) and network in allowlist,
            f"network {network!r} is outside image {image_id} allowlist")

    clipboard = strict_bool(spec, "clipboard", "spec")
    shared_folders = strict_bool(spec, "shared_folders", "spec")
    looking_glass = strict_bool(spec, "looking_glass", "spec")
    require(not shared_folders, "guest lifecycle does not implement shared folders")
    if device_profile == "standard":
        require(not looking_glass, "standard guests cannot request Looking Glass")
    else:
        require(looking_glass, "VFIO guests require Looking Glass in M4")
    usb_allowlist = spec.get("usb_allowlist")
    require(isinstance(usb_allowlist, list) and not usb_allowlist,
            "M4 requires an empty usb_allowlist; reviewed USB passthrough is a later stage")
    require(spec.get("mac") in (None, ""), "guest lifecycle derives MAC addresses; spec.mac must be null or absent")
    require(spec.get("ip") in (None, ""), "guest lifecycle does not assign static IPs; spec.ip must be null or absent")
    if network not in {"clean", "dev"}:
        require(not clipboard, f"clipboard must be false on {network}")

    resources = spec.get("resources")
    require(isinstance(resources, dict), "spec.resources must be a mapping")
    vcpus = resources.get("vcpus")
    require(isinstance(vcpus, int) and not isinstance(vcpus, bool) and 1 <= vcpus <= 256,
            "resources.vcpus must be between 1 and 256")
    memory_request = resources.get("memory_mb")
    require(memory_request == "auto" or
            (isinstance(memory_request, int) and not isinstance(memory_request, bool) and memory_request >= 512),
            "resources.memory_mb must be auto or an integer >= 512")
    disk_gib = resources.get("disk_gib")
    virtual_size_gib = manifest.get("virtual_size_gib")
    require(isinstance(virtual_size_gib, int) and not isinstance(virtual_size_gib, bool)
            and virtual_size_gib > 0, "manifest.virtual_size_gib must be positive")
    if disk_gib is None:
        disk_gib = virtual_size_gib
    require(isinstance(disk_gib, int) and not isinstance(disk_gib, bool)
            and disk_gib >= virtual_size_gib,
            "requested disk is smaller than the sealed image virtual size")

    os_family = manifest.get("os_family")
    require(os_family in {"linux", "windows"}, "unsupported os_family")
    cloud_init = supports.get("cloud_init") is True
    if os_family == "linux":
        require(cloud_init, "Linux guests require a cloud-init capable image")
    else:
        require(not cloud_init, "Windows manifests must not request cloud-init")

    instance_policy = manifest.get("instance_policy")
    require(instance_policy in {"multiple", "singleton"}, "unsupported instance_policy")
    if instance_policy == "singleton":
        require(lifecycle == "permanent", "singleton images require permanent lifecycle")

    requirements = manifest.get("requires")
    require(isinstance(requirements, dict), "manifest.requires must be a mapping")
    requires_uefi = requirements.get("uefi") is True
    requires_secure_boot = requirements.get("secure_boot") is True
    requires_tpm2 = requirements.get("tpm2") is True
    require(not requires_secure_boot or requires_uefi, "Secure Boot requires UEFI")

    memory_overcommit = strict_bool(spec, "memory_overcommit", "spec")
    autostart = strict_bool(spec, "autostart", "spec")
    lg_required = manifest.get("looking_glass_host_build_required")
    if device_profile == "vfio":
        require(os_family == "windows", "M4 VFIO lifecycle supports reviewed Windows images only")
        require(not memory_overcommit, "VFIO guests cannot request memory overcommit")
        require(not autostart, "VFIO guests cannot autostart; GPU trust state starts at an operator action")
        require(isinstance(lg_required, str) and LG_BUILD_RE.fullmatch(lg_required) is not None,
                "VFIO image needs a pinned looking_glass_host_build_required")
    else:
        lg_required = None

    owner = spec.get("owner")
    purpose = spec.get("purpose")
    tags = spec.get("tags")
    require(isinstance(owner, str) and owner, "spec.owner must be non-empty")
    require(isinstance(purpose, str) and purpose, "spec.purpose must be non-empty")
    require(isinstance(tags, list) and tags and all(isinstance(tag, str) and tag for tag in tags),
            "spec.tags must be a non-empty string list")

    base_dir = store / "bases" / ("windows" if os_family == "windows" else "linux")
    base_path = base_dir / filename
    disk_dir = store / lifecycle
    disk_path = disk_dir / f"{name}.qcow2"
    seed_dir = store / "cloud-init" / name
    state_root = store / "state" / "vms"
    xml_root = store / "state" / "domains"
    lock_root = store / "state" / "locks"

    return {
        "schema_version": 1,
        "name": name,
        "uuid": str(uuid.uuid5(UUID_NAMESPACE, name)),
        "mac": derive_mac(name),
        "image": image_id,
        "image_sha256": sha256,
        "image_filename": filename,
        "os_family": os_family,
        "os_variant": manifest.get("os_variant"),
        "lifecycle": lifecycle,
        "device_profile": device_profile,
        "network_profile": network,
        "memory_request": memory_request,
        "image_min_memory_mb": manifest.get("min_memory_mb"),
        "vcpus": vcpus,
        "disk_gib": disk_gib,
        "image_virtual_size_gib": virtual_size_gib,
        "memory_overcommit": memory_overcommit,
        "autostart": autostart,
        "qemu_guest_agent": qemu_guest_agent,
        "looking_glass": looking_glass,
        "looking_glass_host_build_required": lg_required,
        "clipboard": clipboard,
        "shared_folders": shared_folders,
        "requires_uefi": requires_uefi,
        "requires_secure_boot": requires_secure_boot,
        "requires_tpm2": requires_tpm2,
        "cloud_init": cloud_init,
        "instance_policy": instance_policy,
        "owner": owner,
        "purpose": purpose,
        "tags": tags,
        "snapshot_policy": spec.get("snapshot_policy", "none"),
        "backup_policy": spec.get("backup_policy", "none"),
        "benchmark": spec.get("benchmark"),
        "spec_path": str(spec_path),
        "manifest_path": str(manifest_path),
        "base_path": str(base_path),
        "disk_path": str(disk_path),
        "seed_dir": str(seed_dir),
        "seed_user_data": str(seed_dir / "user-data"),
        "seed_meta_data": str(seed_dir / "meta-data"),
        "seed_image": str(seed_dir / "seed.iso"),
        "nvram_path": str(store / "nvram" / f"{name}_VARS.fd"),
        "tpm_path": str(store / "tpm" / name),
        "state_path": str(state_root / f"{name}.yml"),
        "xml_path": str(xml_root / f"{name}.xml"),
        "lock_path": str(lock_root / f"{name}.lock"),
        "capacity_lock_path": str(lock_root / "capacity.lock"),
        "gpu_lock_path": str(lock_root / "gpu.lock"),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--spec", required=True)
    parser.add_argument("--store", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = build_plan(Path(args.root), args.spec, Path(args.store))
    except PlanError as exc:
        print(f"guest plan refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(plan, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
