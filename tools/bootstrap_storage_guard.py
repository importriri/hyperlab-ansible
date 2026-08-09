#!/usr/bin/env python3
"""Validate or safely derive the arch-bootstrap VM-store hand-off contract."""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

import yaml


class ContractError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def load_observation() -> dict[str, Any]:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise ContractError(f"findmnt evidence is not valid JSON: {exc}") from exc
    require(isinstance(payload, dict), "findmnt evidence root must be a mapping")
    filesystems = payload.get("filesystems")
    require(isinstance(filesystems, list) and len(filesystems) == 1,
            "findmnt evidence must describe exactly one mounted filesystem")
    observed = filesystems[0]
    require(isinstance(observed, dict), "findmnt filesystem entry must be a mapping")
    return observed


def normalized_source(value: Any) -> str:
    require(isinstance(value, str) and value.startswith("/dev/mapper/"),
            "observed VM-store source must be one device-mapper path")
    return value.split("[", 1)[0]


def normalized_observation(observed: dict[str, Any]) -> dict[str, str]:
    target = observed.get("target")
    source = observed.get("source")
    fstype = observed.get("fstype")
    fsroot = observed.get("fsroot")
    options = observed.get("options", "")
    require(isinstance(target, str) and target.startswith("/") and target != "/",
            "observed VM-store target must be one absolute non-root path")
    require(isinstance(fstype, str), "observed VM-store fstype must be a string")
    require(isinstance(fsroot, str) and fsroot.startswith("/"),
            "observed VM-store fsroot must be absolute")
    require(isinstance(options, str), "observed VM-store options must be a string")
    return {
        "target": target,
        "source": normalized_source(source),
        "fstype": fstype,
        "fsroot": fsroot,
        "options": options,
    }


def read_contract(path: Path) -> dict[str, Any]:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise ContractError(f"bootstrap storage contract is missing: {path}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            "bootstrap storage contract must be one regular non-symlink file")
    test_mode = os.environ.get("PRIVATESTACK_BOOTSTRAP_STORAGE_TEST") == "1"
    require(info.st_uid == 0 or test_mode, "bootstrap storage contract must be root-owned")
    require(info.st_mode & 0o022 == 0,
            "bootstrap storage contract must not be group/world writable")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ContractError(f"bootstrap storage contract cannot be read: {exc}") from exc
    require(isinstance(data, dict), "bootstrap storage contract root must be a mapping")
    return data


def expected_from_topology(topology: str) -> dict[str, Any]:
    require(topology in {"single-disk", "dedicated-disk"},
            "vm_store.topology must be single-disk or dedicated-disk")
    if topology == "single-disk":
        return {
            "mapper": "/dev/mapper/cryptroot",
            "fsroot": "/@vm",
            "subvolume": "@vm",
            "vm_partlabel": None,
        }
    return {
        "mapper": "/dev/mapper/cryptvm",
        "fsroot": "/",
        "subvolume": None,
        "vm_partlabel": "ARCH_VM",
    }


def validate_contract(data: dict[str, Any], observed: dict[str, str], hyperlab_root: str) -> dict[str, Any]:
    require(data.get("schema_version") == 1, "bootstrap storage schema_version must be 1")
    store = data.get("vm_store")
    require(isinstance(store, dict), "bootstrap storage vm_store must be a mapping")
    allowed = {
        "topology", "mountpoint", "mapper", "fstype", "subvolume",
        "require_nocow", "root_partlabel", "vm_partlabel",
    }
    require(set(store) == allowed,
            f"bootstrap storage vm_store keys differ from the schema: {sorted(set(store) ^ allowed)}")
    topology = store.get("topology")
    expected = expected_from_topology(topology)
    mountpoint = store.get("mountpoint")
    require(mountpoint == "/var/lib/libvirt/images",
            "bootstrap storage mountpoint must be /var/lib/libvirt/images")
    require(hyperlab_root == mountpoint or hyperlab_root.startswith(mountpoint + "/"),
            "HyperLab root must live below the bootstrap VM-store mountpoint")
    require(store.get("mapper") == expected["mapper"],
            "declared mapper differs from the topology contract")
    require(store.get("fstype") == "btrfs", "bootstrap storage fstype must be btrfs")
    require(store.get("subvolume") == expected["subvolume"],
            "declared subvolume differs from the topology contract")
    require(store.get("require_nocow") is True,
            "bootstrap storage must require inherited NOCOW")
    require(store.get("root_partlabel") == "ARCH_ROOT",
            "bootstrap storage root_partlabel must be ARCH_ROOT")
    require(store.get("vm_partlabel") == expected["vm_partlabel"],
            "bootstrap storage vm_partlabel differs from the topology contract")

    require(observed["target"] == mountpoint,
            f"observed VM-store target differs: {observed['target']}")
    require(observed["source"] == expected["mapper"],
            f"observed VM-store mapper differs: {observed['source']}")
    require(observed["fstype"] == "btrfs",
            f"observed VM-store filesystem differs: {observed['fstype']}")
    require(observed["fsroot"] == expected["fsroot"],
            f"observed VM-store fsroot differs: {observed['fsroot']}")

    return {
        "schema_version": 1,
        "topology": topology,
        "mountpoint": mountpoint,
        "mapper": expected["mapper"],
        "fstype": "btrfs",
        "fsroot": expected["fsroot"],
        "subvolume": expected["subvolume"],
        "require_nocow": True,
        "root_partlabel": "ARCH_ROOT",
        "vm_partlabel": expected["vm_partlabel"],
        "hyperlab_root": hyperlab_root,
    }


def adopt_contract(observed: dict[str, str], hyperlab_root: str) -> dict[str, Any]:
    require(observed["target"] == "/var/lib/libvirt/images",
            "legacy adoption requires the canonical libvirt image mountpoint")
    require(observed["fstype"] == "btrfs", "legacy adoption requires Btrfs")
    if observed["source"] == "/dev/mapper/cryptroot" and observed["fsroot"] == "/@vm":
        topology = "single-disk"
    elif observed["source"] == "/dev/mapper/cryptvm" and observed["fsroot"] == "/":
        topology = "dedicated-disk"
    else:
        raise ContractError(
            "legacy adoption supports only cryptroot:/@vm or cryptvm:/; "
            f"observed {observed['source']}:{observed['fsroot']}"
        )
    expected = expected_from_topology(topology)
    require(hyperlab_root.startswith("/var/lib/libvirt/images/"),
            "legacy adoption HyperLab root is outside the VM-store mountpoint")
    return {
        "schema_version": 1,
        "vm_store": {
            "topology": topology,
            "mountpoint": "/var/lib/libvirt/images",
            "mapper": expected["mapper"],
            "fstype": "btrfs",
            "subvolume": expected["subvolume"],
            "require_nocow": True,
            "root_partlabel": "ARCH_ROOT",
            "vm_partlabel": expected["vm_partlabel"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("validate", "adopt"), default="validate")
    parser.add_argument("--contract")
    parser.add_argument("--hyperlab-root", required=True)
    args = parser.parse_args()
    try:
        observed = normalized_observation(load_observation())
        if args.mode == "adopt":
            print(yaml.safe_dump(adopt_contract(observed, args.hyperlab_root), sort_keys=False), end="")
        else:
            require(args.contract is not None and args.contract != "",
                    "--contract is required in validate mode")
            result = validate_contract(
                read_contract(Path(args.contract)), observed, args.hyperlab_root
            )
            print(json.dumps(result, sort_keys=True))
    except (OSError, ContractError) as exc:
        print(f"bootstrap storage refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
