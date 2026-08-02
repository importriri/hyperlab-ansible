#!/usr/bin/env python3
"""Host-independent contract tests for stage-1 VM storage ownership."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / "tools/bootstrap_storage_guard.py"
HYPERLAB_ROOT = "/var/lib/libvirt/images/hyperlab"


def run(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PRIVATESTACK_BOOTSTRAP_STORAGE_TEST"] = "1"
    return subprocess.run(
        args,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


def observation(source: str, fsroot: str, fstype: str = "btrfs") -> str:
    return json.dumps({
        "filesystems": [{
            "target": "/var/lib/libvirt/images",
            "source": source,
            "fstype": fstype,
            "fsroot": fsroot,
            "options": "rw,noatime",
        }]
    })


def contract(topology: str) -> dict[str, Any]:
    dedicated = topology == "dedicated-disk"
    return {
        "schema_version": 1,
        "vm_store": {
            "topology": topology,
            "mountpoint": "/var/lib/libvirt/images",
            "mapper": "/dev/mapper/cryptvm" if dedicated else "/dev/mapper/cryptroot",
            "fstype": "btrfs",
            "subvolume": None if dedicated else "@vm",
            "require_nocow": True,
            "root_partlabel": "ARCH_ROOT",
            "vm_partlabel": "ARCH_VM" if dedicated else None,
        },
    }


def write_contract(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")
    path.chmod(0o644)


def validate(path: Path, observed: str) -> subprocess.CompletedProcess[str]:
    return run(
        sys.executable,
        str(GUARD),
        "--mode",
        "validate",
        "--contract",
        str(path),
        "--hyperlab-root",
        HYPERLAB_ROOT,
        stdin=observed,
    )


def test_valid_single_and_dedicated_topologies() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "contract.yml"
        write_contract(path, contract("single-disk"))
        single = validate(path, observation("/dev/mapper/cryptroot[/@vm]", "/@vm"))
        assert single.returncode == 0, single.stderr
        single_data = json.loads(single.stdout)
        assert single_data["topology"] == "single-disk"
        assert single_data["subvolume"] == "@vm"

        write_contract(path, contract("dedicated-disk"))
        dedicated = validate(path, observation("/dev/mapper/cryptvm", "/"))
        assert dedicated.returncode == 0, dedicated.stderr
        dedicated_data = json.loads(dedicated.stdout)
        assert dedicated_data["topology"] == "dedicated-disk"
        assert dedicated_data["mapper"] == "/dev/mapper/cryptvm"


def test_declared_and_observed_mapper_drift_is_refused() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "contract.yml"
        write_contract(path, contract("dedicated-disk"))
        result = validate(path, observation("/dev/mapper/cryptroot[/@vm]", "/@vm"))
        assert result.returncode == 2
        assert "observed VM-store mapper differs" in result.stderr


def test_fsroot_fstype_and_schema_mutations_are_refused() -> None:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "contract.yml"
        write_contract(path, contract("single-disk"))
        wrong_root = validate(path, observation("/dev/mapper/cryptroot", "/"))
        assert wrong_root.returncode == 2 and "fsroot differs" in wrong_root.stderr
        wrong_fs = validate(path, observation("/dev/mapper/cryptroot", "/@vm", "ext4"))
        assert wrong_fs.returncode == 2 and "filesystem differs" in wrong_fs.stderr

        payload = contract("single-disk")
        payload["vm_store"]["extra"] = "unreviewed"
        write_contract(path, payload)
        extra = validate(path, observation("/dev/mapper/cryptroot", "/@vm"))
        assert extra.returncode == 2 and "keys differ" in extra.stderr

        payload = contract("single-disk")
        payload["vm_store"]["require_nocow"] = False
        write_contract(path, payload)
        nocow = validate(path, observation("/dev/mapper/cryptroot", "/@vm"))
        assert nocow.returncode == 2 and "must require inherited NOCOW" in nocow.stderr


def test_legacy_adoption_derives_only_the_two_supported_shapes() -> None:
    single = run(
        sys.executable,
        str(GUARD),
        "--mode",
        "adopt",
        "--hyperlab-root",
        HYPERLAB_ROOT,
        stdin=observation("/dev/mapper/cryptroot[/@vm]", "/@vm"),
    )
    assert single.returncode == 0, single.stderr
    assert yaml.safe_load(single.stdout) == contract("single-disk")

    dedicated = run(
        sys.executable,
        str(GUARD),
        "--mode",
        "adopt",
        "--hyperlab-root",
        HYPERLAB_ROOT,
        stdin=observation("/dev/mapper/cryptvm", "/"),
    )
    assert dedicated.returncode == 0, dedicated.stderr
    assert yaml.safe_load(dedicated.stdout) == contract("dedicated-disk")

    unknown = run(
        sys.executable,
        str(GUARD),
        "--mode",
        "adopt",
        "--hyperlab-root",
        HYPERLAB_ROOT,
        stdin=observation("/dev/mapper/other", "/"),
    )
    assert unknown.returncode == 2 and "supports only" in unknown.stderr


def test_role_orders_validation_before_image_store_writes() -> None:
    playbook = (ROOT / "playbooks/image-store.yml").read_text(encoding="utf-8")
    tasks = (ROOT / "roles/bootstrap_storage/tasks/main.yml").read_text(encoding="utf-8")
    bricks = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text())
    assert playbook.index("bootstrap_storage") < playbook.index("- image_store")
    assert tasks.index("Read the mounted VM-store identity") < tasks.index(
        "Commit the observed legacy contract without changing storage"
    )
    assert tasks.index("Validate declared topology against the mounted source and fsroot") < tasks.index(
        "Record that the bootstrap_storage brick is available"
    )
    assert bricks["brick_requires"]["image_store"] == ["kvm_host", "bootstrap_storage"]
    assert bricks["brick_requires"]["bootstrap_storage"] == ["kvm_host"]


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"bootstrap storage contract: OK ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
