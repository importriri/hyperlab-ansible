#!/usr/bin/env python3
"""C10 Machine Factory schema contract."""

from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import schema_validate


def write_yaml(path: Path, payload: dict) -> None:
    path.write_text(
        yaml.safe_dump(payload, sort_keys=False),
        encoding="utf-8",
    )


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    validator = schema_validate.RepositoryValidator(ROOT)
    validator.valid_domains = validator.domains()

    template_schema = validator.load_yaml(
        ROOT / "schemas/template.v1.yml"
    )
    machine_schema = validator.load_yaml(
        ROOT / "schemas/machine-record.v1.yml"
    )

    arch = validator.load_yaml(ROOT / "images/arch.yml")

    require(
        arch.get("status") == "sealed"
        and isinstance(arch.get("sha256"), str),
        "Arch fixture must expose a sealed digest",
    )

    template = {
        "schema_version": 1,
        "id": "development-workstation",
        "display_name": "Development Workstation",
        "version": "1.0",
        "status": "ready",
        "image": "arch",
        "lifecycles": {
            "permanent": True,
            "disposable": True,
        },
        "device_capabilities": {
            "standard": True,
            "vfio": True,
        },
        "gpu_handoff_profiles": {
            "clean": True,
            "dev": True,
            "dirty": True,
            "lab": True,
        },
        "network_allowlist": [
            "clean",
            "dev",
            "services",
        ],
        "resource_profiles": {
            "minimum": True,
            "balanced": True,
            "performance": True,
            "custom": True,
        },
        "presentation": {
            "looking_glass_mode": "linux-experimental",
            "recovery_console": True,
            "workspace_profile": "development-blue",
        },
        "defaults": {
            "lifecycle": "permanent",
            "device_capability": "standard",
            "gpu_handoff_profile": None,
            "network_profile": "dev",
            "resource_profile": "balanced",
        },
    }

    machine = {
        "schema_version": 1,
        "id": "development-01",
        "display_name": "Development 01",
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
        "created_at": "2026-09-30T20:00:00Z",
        "purpose": "Machine Factory contract fixture",
    }

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        template_path = root / "development-workstation.yml"
        machine_path = root / "development-01.yml"

        write_yaml(template_path, template)
        write_yaml(machine_path, machine)

        validator.result.errors.clear()
        validator.check_document(
            template_path,
            template,
            template_schema,
        )
        validator.validate_template_policy(
            template_path,
            template,
            {"arch": arch},
        )

        require(
            not validator.result.errors,
            "valid Template rejected: "
            + repr(validator.result.errors),
        )

        validator.result.errors.clear()
        validator.check_document(
            machine_path,
            machine,
            machine_schema,
        )

        require(
            not validator.result.errors,
            "valid Machine intent rejected: "
            + repr(validator.result.errors),
        )

        require(
            machine["network_profile"] == "services"
            and machine["device_capability"] == "vfio",
            "services/VFIO independence drifted",
        )

        forbidden = {
            "state": "running",
            "trust": "dev",
            "provenance": "dev",
            "gpu_owner": "development-01",
            "transport_available": True,
        }

        for field, value in forbidden.items():
            invalid = copy.deepcopy(machine)
            invalid[field] = value

            validator.result.errors.clear()
            validator.check_document(
                machine_path,
                invalid,
                machine_schema,
            )

            require(
                any(
                    field in error
                    and "not in schema" in error
                    for error in validator.result.errors
                ),
                f"Machine record accepted runtime authority field {field}",
            )

    print("C10 Machine Factory schema contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
