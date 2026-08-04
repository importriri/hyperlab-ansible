"""Manifest-driven VM catalogue and host-local spec composition.

This module owns no lifecycle operation. It turns checked-in image policy into
a constrained choice matrix and writes operator-created specs below
``vm-specs/.generated``. The existing planners, Ansible transactions, locks and
exact confirmations remain authoritative.
"""

from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from .config import load_yaml
from .errors import ContractError, Unavailable


NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
OWNER_RE = re.compile(r"^[a-z_][a-z0-9_-]{0,30}$")
SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
GENERATED_DIR = ".generated"
RESOURCE_PROFILES = ("minimum", "balanced", "performance", "custom")


def _repo_root(repo_root):
    if repo_root is None:
        raise Unavailable("no repository checkout found: run from the repo or pass --repo")
    root = Path(repo_root).resolve()
    if not (root / "images").is_dir() or not (root / "vm-specs").is_dir():
        raise Unavailable("repository is missing images/ or vm-specs/ under %s" % root)
    return root


def _inside(path, parent):
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _vm_name(value):
    if not isinstance(value, str) or NAME_RE.fullmatch(value) is None:
        raise ContractError("VM name must match %s" % NAME_RE.pattern)
    return value


def _owner(value):
    if not isinstance(value, str) or OWNER_RE.fullmatch(value) is None:
        raise ContractError("owner must be a portable local account name")
    return value


def image_manifests(repo_root):
    root = _repo_root(repo_root)
    manifests = []
    for path in sorted((root / "images").glob("*.yml")):
        if path.is_symlink() or not path.is_file():
            continue
        data = load_yaml(path)
        if not isinstance(data, dict):
            raise ContractError("%s must contain a mapping" % path)
        if data.get("id") != path.stem:
            raise ContractError("%s id must equal its file name" % path)
        manifests.append((path, data))
    if not manifests:
        raise ContractError("images/ contains no manifests")
    return manifests


def _ready(image):
    return (
        image.get("status") == "sealed"
        and isinstance(image.get("sha256"), str)
        and SHA256_RE.fullmatch(image["sha256"]) is not None
    )


def _lifecycles(image):
    policy = image.get("instance_policy")
    if policy == "singleton":
        return ["permanent"]
    if policy == "multiple":
        return ["permanent", "disposable"]
    raise ContractError("image %s has unsupported instance_policy" % image.get("id"))


def _devices(image):
    supports = image.get("supports")
    if not isinstance(supports, dict):
        raise ContractError("image %s supports must be a mapping" % image.get("id"))
    result = [name for name in ("standard", "vfio") if supports.get(name) is True]
    if not result:
        raise ContractError("image %s supports no device profile" % image.get("id"))
    return result


def _networks(image, device_profile):
    allowlist = image.get("network_allowlist")
    if not isinstance(allowlist, list) or not allowlist:
        raise ContractError("image %s needs a non-empty network_allowlist" % image.get("id"))
    networks = []
    for value in allowlist:
        if not isinstance(value, str) or not value:
            raise ContractError("image %s has an invalid network name" % image.get("id"))
        if device_profile == "vfio" and value == "services":
            continue
        if value not in networks:
            networks.append(value)
    if not networks:
        raise ContractError(
            "image %s/%s has no permitted network" % (image.get("id"), device_profile)
        )
    return networks


def _resources(image, profile):
    if profile not in RESOURCE_PROFILES:
        raise ContractError("unknown resource profile %s" % profile)
    virtual = image.get("virtual_size_gib")
    minimum = image.get("minimum_size_gib")
    memory_floor = image.get("min_memory_mb")
    if not isinstance(virtual, int) or isinstance(virtual, bool) or virtual < 1:
        raise ContractError("image virtual_size_gib must be a positive integer")
    if not isinstance(minimum, int) or isinstance(minimum, bool) or minimum < 1:
        raise ContractError("image minimum_size_gib must be a positive integer")
    if (
        not isinstance(memory_floor, int)
        or isinstance(memory_floor, bool)
        or memory_floor < 512
    ):
        raise ContractError("image min_memory_mb must be an integer >= 512")

    os_family = image.get("os_family")
    if profile == "minimum":
        return {
            "memory_mb": memory_floor,
            "vcpus": 2,
            "disk_gib": max(virtual, minimum),
        }
    if profile == "performance":
        return {
            "memory_mb": "auto",
            "vcpus": 6,
            "disk_gib": max(virtual, 96 if os_family == "windows" else 40),
        }
    return {
        "memory_mb": "auto",
        "vcpus": 4,
        "disk_gib": max(virtual, 64 if os_family == "windows" else 20),
    }


def catalog(repo_root):
    root = _repo_root(repo_root)
    entries = []
    for path, image in image_manifests(root):
        devices = _devices(image)
        by_device = {device: _networks(image, device) for device in devices}
        lifecycles = _lifecycles(image)
        defaults = image.get("defaults")
        if not isinstance(defaults, dict):
            raise ContractError("image %s defaults must be a mapping" % image.get("id"))

        default_device = defaults.get("device_profile")
        if default_device not in devices:
            default_device = devices[0]
        default_lifecycle = defaults.get("lifecycle")
        if default_lifecycle not in lifecycles:
            default_lifecycle = lifecycles[0]
        default_network = defaults.get("network_profile")
        if default_network not in by_device[default_device]:
            default_network = by_device[default_device][0]

        ready = _ready(image)
        entries.append({
            "id": image["id"],
            "display_name": image.get("display_name") or image["id"],
            "os_family": image.get("os_family"),
            "os_variant": image.get("os_variant"),
            "cloud_init": bool(image.get("supports", {}).get("cloud_init")),
            "qemu_guest_agent": bool(
                image.get("supports", {}).get("qemu_guest_agent")
            ),
            "status": image.get("status"),
            "ready": ready,
            "blocked_reason": None if ready else "image is not sealed with a valid sha256",
            "private": bool(image.get("private")),
            "instance_policy": image.get("instance_policy"),
            "lifecycles": lifecycles,
            "device_profiles": devices,
            "network_profiles_by_device": by_device,
            "manifest": path.relative_to(root).as_posix(),
            "defaults": {
                "lifecycle": default_lifecycle,
                "device_profile": default_device,
                "network_profile": default_network,
                "resources": _resources(image, "balanced"),
            },
            "resource_profiles": {
                name: _resources(image, name)
                for name in ("minimum", "balanced", "performance")
            },
        })
    return entries


def image_entry(repo_root, image_id):
    for entry in catalog(repo_root):
        if entry["id"] == image_id:
            return entry
    raise ContractError("unknown image %s" % image_id)


def build_spec(
    repo_root,
    name,
    image_id,
    lifecycle,
    device_profile,
    network_profile,
    owner,
    purpose=None,
    resource_profile="balanced",
    memory_mb=None,
    vcpus=None,
    disk_gib=None,
    clipboard=False,
):
    name = _vm_name(name)
    owner = _owner(owner)
    entry = image_entry(repo_root, image_id)
    if not entry["ready"]:
        raise ContractError("%s is blocked: %s" % (image_id, entry["blocked_reason"]))
    if lifecycle not in entry["lifecycles"]:
        raise ContractError("%s does not permit lifecycle %s" % (image_id, lifecycle))
    if device_profile not in entry["device_profiles"]:
        raise ContractError(
            "%s does not permit device profile %s" % (image_id, device_profile)
        )
    permitted_networks = entry["network_profiles_by_device"][device_profile]
    if network_profile not in permitted_networks:
        raise ContractError(
            "%s/%s does not permit network %s"
            % (image_id, device_profile, network_profile)
        )

    image = next(
        data for _, data in image_manifests(repo_root) if data["id"] == image_id
    )
    if resource_profile == "custom":
        resources = {
            "memory_mb": memory_mb,
            "vcpus": vcpus,
            "disk_gib": disk_gib,
        }
    else:
        resources = dict(_resources(image, resource_profile))

    memory = resources.get("memory_mb")
    if memory != "auto" and (
        not isinstance(memory, int)
        or isinstance(memory, bool)
        or memory < 512
    ):
        raise ContractError("memory_mb must be auto or an integer >= 512")
    cpu_count = resources.get("vcpus")
    if (
        not isinstance(cpu_count, int)
        or isinstance(cpu_count, bool)
        or not 1 <= cpu_count <= 256
    ):
        raise ContractError("vcpus must be an integer between 1 and 256")
    disk = resources.get("disk_gib")
    if disk is not None and (
        not isinstance(disk, int)
        or isinstance(disk, bool)
        or disk < image["virtual_size_gib"]
    ):
        raise ContractError("disk_gib must cover the sealed image virtual size")

    looking_glass = (
        entry["os_family"] == "windows" and device_profile == "vfio"
    )
    clipboard = bool(clipboard) and network_profile in {"clean", "dev"}
    purpose = purpose or "%s %s %s workload" % (
        entry["display_name"],
        lifecycle,
        device_profile,
    )

    tags = []
    for tag in (
        entry["os_family"],
        image_id,
        lifecycle,
        device_profile,
        network_profile,
    ):
        if tag and tag not in tags:
            tags.append(tag)

    return {
        "schema_version": 1,
        "name": name,
        "image": image_id,
        "lifecycle": lifecycle,
        "device_profile": device_profile,
        "network_profile": network_profile,
        "resources": resources,
        "memory_overcommit": False,
        "autostart": False,
        "qemu_guest_agent": entry["qemu_guest_agent"],
        "looking_glass": looking_glass,
        "clipboard": clipboard,
        "shared_folders": False,
        "usb_allowlist": [],
        "owner": owner,
        "purpose": purpose,
        "tags": tags,
        "snapshot_policy": "none" if lifecycle == "disposable" else "manual",
        "backup_policy": "none" if lifecycle == "disposable" else "manual",
    }


def generated_root(repo_root, create=False):
    root = _repo_root(repo_root)
    specs = root / "vm-specs"
    if specs.is_symlink():
        raise ContractError("vm-specs must not be a symlink")
    target = specs / GENERATED_DIR
    if target.exists() and (target.is_symlink() or not target.is_dir()):
        raise ContractError("vm-specs/%s must be a real directory" % GENERATED_DIR)
    if create and not target.exists():
        target.mkdir(mode=0o700)
    resolved = target.resolve()
    if not _inside(resolved, specs.resolve()):
        raise ContractError("generated spec directory escaped vm-specs")
    return target


def generated_specs(repo_root):
    root = _repo_root(repo_root)
    directory = generated_root(root)
    if not directory.exists():
        return []
    return [
        path.relative_to(root).as_posix()
        for path in sorted(directory.glob("*.yml"))
        if path.is_file() and not path.is_symlink()
    ]


def find_spec(repo_root, name):
    name = _vm_name(name)
    root = _repo_root(repo_root)
    candidates = (
        root / "vm-specs" / ("%s.yml" % name),
        root / "vm-specs" / GENERATED_DIR / ("%s.yml" % name),
    )
    for path in candidates:
        if path.is_file() and not path.is_symlink():
            return path.relative_to(root).as_posix()
    raise Unavailable("no checked-in or generated spec exists for %s" % name)


def write_spec(repo_root, spec, replace=False):
    name = _vm_name(spec.get("name"))
    root = _repo_root(repo_root)
    directory = generated_root(root, create=True)
    destination = directory / ("%s.yml" % name)
    if destination.is_symlink():
        raise ContractError("refusing symlinked generated spec %s" % destination)
    if destination.exists() and not replace:
        raise ContractError("generated spec %s already exists" % name)
    try:
        import yaml
    except ImportError as exc:
        raise Unavailable("PyYAML is not importable; install python-yaml") from exc

    payload = yaml.safe_dump(spec, sort_keys=False, explicit_start=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=".%s." % name,
        suffix=".tmp",
        dir=str(directory),
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return destination.relative_to(root).as_posix()


def remove_spec(repo_root, name, confirmation):
    name = _vm_name(name)
    if confirmation != name:
        raise ContractError("generated spec removal requires exact confirmation %s" % name)
    root = _repo_root(repo_root)
    destination = generated_root(root) / ("%s.yml" % name)
    if not destination.exists():
        raise Unavailable("generated spec %s does not exist" % name)
    if destination.is_symlink() or not destination.is_file():
        raise ContractError("generated spec %s is not a regular file" % name)
    destination.unlink()
    return destination.relative_to(root).as_posix()
