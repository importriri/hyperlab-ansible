#!/usr/bin/env python3
"""C10 Machine -> VM-spec -> existing planner compatibility contract."""

from __future__ import annotations

import copy
import importlib.util
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]

sys.path.insert(
    0,
    str(ROOT / "tools/hyperlabctl"),
)

from hyperlabctl.errors import ContractError
from hyperlabctl.machine_factory import (
    project_vm_spec,
    write_projected_vm_spec,
)


def load_tool(
    relative: str,
    name: str,
):
    path = ROOT / relative

    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    module = importlib.util.module_from_spec(
        spec
    )

    assert spec.loader is not None

    spec.loader.exec_module(
        module
    )

    return module


guest_plan = load_tool(
    "tools/guest_plan.py",
    "c10_guest_plan",
)

vfio_plan = load_tool(
    "tools/vfio_plan.py",
    "c10_vfio_plan",
)


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(
            message
        )


def expect_contract_error(
    function,
    message: str,
) -> None:
    try:
        function()
    except ContractError:
        return

    raise AssertionError(
        message
    )


def write_yaml(
    path: Path,
    value: dict,
) -> None:
    path.write_text(
        yaml.safe_dump(
            value,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def prepare_repo(
    root: Path,
) -> dict:
    (root / "images").mkdir()
    (root / "templates").mkdir()
    (root / "vm-specs").mkdir()

    arch = yaml.safe_load(
        (
            ROOT
            / "images"
            / "arch.yml"
        ).read_text(
            encoding="utf-8"
        )
    )

    write_yaml(
        root / "images/arch.yml",
        arch,
    )

    return arch


def machine(
    arch: dict,
    *,
    machine_id: str = "services-workload-01",
) -> dict:
    return {
        "schema_version": 1,
        "id": machine_id,
        "display_name": "Services Workload 01",
        "template": {
            "id": "development-workstation",
            "version": "1.0",
        },
        "image": {
            "id": "arch",
            "sha256": arch["sha256"],
        },
        "lifecycle": "permanent",
        "device_capability": "vfio",
        "gpu_handoff_profile": "dev",
        "network_profile": "services",
        "resources": {
            "memory_mb": 16384,
            "vcpus": 4,
            "disk_gib": 100,
        },
        "presentation": {
            "looking_glass_mode": "linux-experimental",
            "recovery_console": True,
            "workspace_profile": "development-blue",
        },
        "owner": "tester",
        "created_at": "2026-10-01T12:00:00Z",
        "purpose": "C10 projection fixture",
    }


def hardware_report() -> dict:
    return {
        "host_profile": "test",
        "gpu_pci": "01:00.0",
        "gpu_audio_pci": "01:00.1",
        "vfio_devices": [
            {
                "pci": "01:00.0",
                "id": "10de:0001",
            },
            {
                "pci": "01:00.1",
                "id": "10de:0002",
            },
        ],
    }


def host_profiles() -> dict:
    return {
        "test": {
            "vfio_ids": [
                "10de:0001",
                "10de:0002",
            ],
        },
    }


TRUST_LEVELS = {
    "clean": 3,
    "dev": 2,
    "dirty": 1,
    "lab": 0,
}


def verify_services_vfio_projection() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-projection-"
    ) as temporary:
        root = Path(
            temporary
        )

        arch = prepare_repo(
            root
        )

        record = machine(
            arch
        )

        spec = project_vm_spec(
            root,
            record,
        )

        require(
            spec["image_sha256"]
            == record["image"]["sha256"],
            "projection lost pinned Golden Image digest",
        )

        require(
            spec["network_profile"] == "services",
            "projection changed SERVICES identity",
        )

        require(
            spec["device_profile"] == "vfio",
            "projection lost VFIO",
        )

        require(
            spec["gpu_handoff_profile"] == "dev",
            "projection lost explicit GPU handoff policy",
        )

        require(
            spec["looking_glass"] is True
            and spec["looking_glass_mode"]
            == "linux-experimental",
            "projection inferred or lost Looking Glass mode",
        )

        path = write_projected_vm_spec(
            root,
            record,
        )

        require(
            path
            == "vm-specs/.generated/"
            "services-workload-01.yml",
            "projection bypassed generated VM-spec boundary",
        )

        plan = guest_plan.build_plan(
            root,
            path,
            root / "store",
        )

        require(
            plan["network_profile"] == "services",
            "guest plan changed SERVICES identity",
        )

        require(
            plan["gpu_handoff_profile"] == "dev",
            "guest plan coupled GPU policy "
            "back to network identity",
        )

        result = vfio_plan.build_vfio_plan(
            plan,
            hardware_report(),
            host_profiles(),
            TRUST_LEVELS,
            "B7-263-g0140a3f6fb",
            "/dev/kvmfr0",
            64,
            "127.0.0.1",
            5900,
        )

        require(
            result["network_profile"] == "services",
            "VFIO plan changed SERVICES identity",
        )

        require(
            result["gpu_handoff_profile"] == "dev"
            and result["trust_level"] == 2,
            "VFIO plan did not use explicit "
            "GPU handoff policy",
        )

        require(
            result["looking_glass_enabled"] is True,
            "VFIO plan lost explicit Looking Glass",
        )


def verify_digest_drift_refusal() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-digest-"
    ) as temporary:
        root = Path(
            temporary
        )

        arch = prepare_repo(
            root
        )

        record = machine(
            arch
        )

        changed = copy.deepcopy(
            arch
        )

        changed["sha256"] = "b" * 64

        write_yaml(
            root / "images/arch.yml",
            changed,
        )

        expect_contract_error(
            lambda: project_vm_spec(
                root,
                record,
            ),
            "projection accepted Golden digest drift",
        )


def verify_existing_projection_refuses_resealed_image() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-adapter-digest-"
    ) as temporary:
        root = Path(
            temporary
        )

        arch = prepare_repo(
            root
        )

        record = machine(
            arch,
            machine_id="digest-pin-01",
        )

        path = write_projected_vm_spec(
            root,
            record,
        )

        projected = yaml.safe_load(
            (
                root
                / path
            ).read_text(
                encoding="utf-8"
            )
        )

        require(
            projected["image_sha256"]
            == record["image"]["sha256"],
            "written adapter lost Golden Image digest pin",
        )

        resealed = copy.deepcopy(
            arch
        )

        resealed["sha256"] = "b" * 64

        write_yaml(
            root / "images/arch.yml",
            resealed,
        )

        try:
            guest_plan.build_plan(
                root,
                path,
                root / "store",
            )
        except guest_plan.PlanError:
            pass
        else:
            raise AssertionError(
                "already-projected VM spec accepted "
                "a resealed Golden Image with another digest"
            )


def verify_windows_vfio_without_lg() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-windows-"
    ) as temporary:
        root = Path(
            temporary
        )

        arch = prepare_repo(
            root
        )

        windows = copy.deepcopy(
            arch
        )

        windows.update(
            {
                "id": "win-test",
                "display_name": "Windows test",
                "os_family": "windows",
                "os_variant": "win11",
                "sha256": "c" * 64,
                "filename": "win-test.qcow2",
                "instance_policy": "multiple",
                "network_allowlist": ["clean"],
                "looking_glass_host_build_required": (
                    "B7-263-g0140a3f6fb"
                ),
                "looking_glass_host_build_observed": (
                    "B7-263-g0140a3f6fb"
                ),
            }
        )

        windows["supports"] = dict(
            windows["supports"]
        )
        windows["supports"]["cloud_init"] = False

        windows["requires"] = {
            "uefi": True,
            "secure_boot": True,
            "tpm2": True,
        }

        write_yaml(
            root / "images/win-test.yml",
            windows,
        )

        record = {
            "schema_version": 1,
            "id": "windows-test-01",
            "display_name": "Windows test 01",
            "template": {
                "id": "windows-workstation",
                "version": "1.0",
            },
            "image": {
                "id": "win-test",
                "sha256": "c" * 64,
            },
            "lifecycle": "permanent",
            "device_capability": "vfio",
            "gpu_handoff_profile": "clean",
            "network_profile": "clean",
            "resources": {
                "memory_mb": 8192,
                "vcpus": 4,
                "disk_gib": 100,
            },
            "presentation": {
                "looking_glass_mode": "disabled",
                "recovery_console": True,
                "workspace_profile": "development-blue",
            },
            "owner": "tester",
            "created_at": "2026-10-01T12:00:00Z",
        }

        path = write_projected_vm_spec(
            root,
            record,
        )

        plan = guest_plan.build_plan(
            root,
            path,
            root / "store",
        )

        require(
            plan["os_family"] == "windows"
            and plan["looking_glass"] is False
            and plan["looking_glass_mode"] is None,
            "Windows VFIO still inferred Looking Glass",
        )

        result = vfio_plan.build_vfio_plan(
            plan,
            hardware_report(),
            host_profiles(),
            TRUST_LEVELS,
            "B7-263-g0140a3f6fb",
            "/dev/kvmfr0",
            64,
            "127.0.0.1",
            5900,
        )

        require(
            result["looking_glass_enabled"] is False,
            "VFIO plan re-enabled Windows Looking Glass",
        )


def main() -> int:
    verify_services_vfio_projection()
    verify_digest_drift_refusal()
    verify_existing_projection_refuses_resealed_image()
    verify_windows_vfio_without_lg()

    print(
        "C10 Machine -> VM-spec projection contract: OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
