#!/usr/bin/env python3
"""C10 Template catalogue and Machine materialization contract."""

from __future__ import annotations

import copy
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
    create_from_template,
    materialize_machine,
    template_catalog,
)
from hyperlabctl.machine_registry import (
    read_machine,
)


IMAGE_SHA = "a" * 64


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(
            message
        )


def write_yaml(
    path: Path,
    payload: dict,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    path.write_text(
        yaml.safe_dump(
            payload,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def image() -> dict:
    return {
        "schema_version": 1,
        "id": "arch-workstation",
        "display_name": "Arch Workstation",
        "os_family": "linux",
        "status": "sealed",
        "sha256": IMAGE_SHA,
        "generalized": True,
        "contains_personal_data": False,
        "instance_policy": "multiple",
        "virtual_size_gib": 20,
        "minimum_size_gib": 8,
        "min_memory_mb": 2048,
        "supports": {
            "standard": True,
            "vfio": True,
            "cloud_init": True,
            "qemu_guest_agent": True,
        },
        "network_allowlist": [
            "clean",
            "dev",
            "services",
            "dirty",
            "lab",
        ],
    }


def template(
    *,
    version: str = "1.0",
    status: str = "ready",
) -> dict:
    return {
        "schema_version": 1,
        "id": "development-workstation",
        "display_name": "Development Workstation",
        "version": version,
        "status": status,
        "image": "arch-workstation",
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


def prepare_repo(
    root: Path,
) -> None:
    (root / "images").mkdir()
    (root / "templates").mkdir()

    write_yaml(
        root / "images/arch-workstation.yml",
        image(),
    )

    write_yaml(
        root
        / "templates"
        / "development-workstation.yml",
        template(),
    )


def materialize(
    root: Path,
    **overrides,
) -> dict:
    arguments = {
        "template_id": "development-workstation",
        "machine_id": "development-01",
        "display_name": "Development 01",
        "owner": "tester",
        "created_at": "2026-09-30T21:00:00Z",
        "lifecycle": "permanent",
        "device_capability": "vfio",
        "gpu_handoff_profile": "dev",
        "network_profile": "services",
        "resource_profile": "balanced",
        "looking_glass_mode": "linux-experimental",
        "purpose": "C10 materialization fixture",
    }

    arguments.update(
        overrides
    )

    return materialize_machine(
        root,
        **arguments,
    )


def verify_catalog_and_materialization() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-factory-"
    ) as temporary:
        root = Path(
            temporary
        )

        prepare_repo(
            root
        )

        catalog = template_catalog(
            root
        )

        require(
            len(catalog) == 1,
            "Template catalogue count changed",
        )

        entry = catalog[0]

        require(
            entry["id"]
            == "development-workstation"
            and entry["version"] == "1.0"
            and entry["ready"] is True,
            "ready Template was not catalogued",
        )

        require(
            "services"
            in entry["network_profiles"]
            and "vfio"
            in entry["device_capabilities"],
            "Template catalogue coupled "
            "network identity to GPU capability",
        )

        require(
            entry["presentation"][
                "looking_glass_mode"
            ]
            == "linux-experimental",
            "Template lost explicit "
            "Looking Glass capability",
        )

        record = materialize(
            root
        )

        require(
            record["template"]
            == {
                "id": "development-workstation",
                "version": "1.0",
            },
            "Machine did not pin "
            "Template identity/version",
        )

        require(
            record["image"]
            == {
                "id": "arch-workstation",
                "sha256": IMAGE_SHA,
            },
            "Machine did not pin "
            "Golden Image digest",
        )

        require(
            record["network_profile"]
            == "services"
            and record["device_capability"]
            == "vfio"
            and record["gpu_handoff_profile"]
            == "dev",
            "network identity and GPU handoff "
            "policy were coupled",
        )

        require(
            record["presentation"][
                "looking_glass_mode"
            ]
            == "linux-experimental",
            "Linux Looking Glass mode "
            "was inferred or lost",
        )

        require(
            record["presentation"][
                "workspace_profile"
            ]
            == "development-blue",
            "Machine did not pin "
            "Template workspace presentation",
        )

        pinned = copy.deepcopy(
            record
        )

        changed_template = template(
            version="2.0"
        )

        write_yaml(
            root
            / "templates"
            / "development-workstation.yml",
            changed_template,
        )

        changed_image = image()
        changed_image["sha256"] = "b" * 64

        write_yaml(
            root
            / "images"
            / "arch-workstation.yml",
            changed_image,
        )

        require(
            record == pinned,
            "existing Machine intent changed "
            "after source policy changed",
        )


def verify_persistent_creation() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-create-"
    ) as temporary:
        root = Path(
            temporary
        )
        repo = root / "repo"
        state = root / "state"

        repo.mkdir()

        prepare_repo(
            repo
        )

        path = create_from_template(
            repo,
            state_home=state,
            template_id="development-workstation",
            machine_id="development-01",
            display_name="Development 01",
            owner="tester",
            created_at="2026-09-30T21:00:00Z",
            lifecycle="permanent",
            device_capability="vfio",
            gpu_handoff_profile="dev",
            network_profile="services",
            resource_profile="balanced",
            looking_glass_mode="linux-experimental",
        )

        require(
            path
            == state
            / "hyperlab"
            / "machines"
            / "development-01.yml",
            "materialized Machine used "
            "the wrong persistent path",
        )

        loaded = read_machine(
            "development-01",
            state_home=state,
        )

        require(
            loaded["template"]["version"]
            == "1.0",
            "persistent Machine lost "
            "Template version pin",
        )

        require(
            loaded["image"]["sha256"]
            == IMAGE_SHA,
            "persistent Machine lost "
            "Golden Image digest pin",
        )


def verify_transport_and_policy_refusals() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-policy-"
    ) as temporary:
        root = Path(
            temporary
        )

        prepare_repo(
            root
        )

        disabled = materialize(
            root,
            looking_glass_mode="disabled",
        )

        require(
            disabled["presentation"][
                "looking_glass_mode"
            ]
            == "disabled",
            "explicit Looking Glass disable "
            "was not preserved",
        )

        expect_contract_error(
            lambda: materialize(
                root,
                looking_glass_mode="windows",
            ),
            "Linux Template accepted "
            "Windows Looking Glass mode",
        )

        expect_contract_error(
            lambda: materialize(
                root,
                device_capability="standard",
                looking_glass_mode=(
                    "linux-experimental"
                ),
            ),
            "standard Machine accepted "
            "Looking Glass",
        )

        expect_contract_error(
            lambda: materialize(
                root,
                network_profile="dirty",
            ),
            "Template network boundary "
            "was ignored",
        )

        draft = template(
            status="draft"
        )

        write_yaml(
            root
            / "templates"
            / "development-workstation.yml",
            draft,
        )

        expect_contract_error(
            lambda: materialize(
                root
            ),
            "draft Template materialized "
            "a Machine",
        )


def main() -> int:
    verify_catalog_and_materialization()
    verify_persistent_creation()
    verify_transport_and_policy_refusals()

    print(
        "C10 Template catalogue and "
        "Machine materialization contract: OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
