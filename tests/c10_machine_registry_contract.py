#!/usr/bin/env python3
"""C10 persistent Machine registry security and durability contract."""

from __future__ import annotations

import copy
import os
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(
    0,
    str(ROOT / "tools/hyperlabctl"),
)

from hyperlabctl.errors import ContractError, Unavailable
from hyperlabctl.machine_registry import (
    create_machine,
    list_machines,
    read_machine,
)


ARCH_SHA256 = (
    "f419d4e29aebfc017ad4c9de330a3be0"
    "d7eefba710b269108b116aaca1122926"
)


def require(
    condition: bool,
    message: str,
) -> None:
    if not condition:
        raise AssertionError(
            message
        )


def machine(
    machine_id: str = "development-01",
) -> dict:
    return {
        "schema_version": 1,
        "id": machine_id,
        "display_name": "Development 01",
        "template": {
            "id": "development-workstation",
            "version": "1.0",
        },
        "image": {
            "id": "arch",
            "sha256": ARCH_SHA256,
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
        "purpose": "C10 registry contract fixture",
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


def expect_unavailable(
    function,
    message: str,
) -> None:
    try:
        function()
    except Unavailable:
        return

    raise AssertionError(
        message
    )


def verify_persistent_registry() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-registry-"
    ) as temporary:
        root = Path(
            temporary
        )
        state = root / "state"

        require(
            list_machines(
                state_home=state,
            )
            == [],
            "first-boot registry is not empty",
        )

        require(
            not state.exists(),
            "read-only first-boot inventory "
            "created persistent state",
        )

        first = machine()

        path = create_machine(
            first,
            state_home=state,
        )

        expected = (
            state
            / "hyperlab"
            / "machines"
            / "development-01.yml"
        )

        require(
            path == expected,
            "Machine registry path changed",
        )

        directory_info = (
            expected.parent.lstat()
        )
        file_info = (
            expected.lstat()
        )

        require(
            stat.S_ISDIR(
                directory_info.st_mode
            )
            and not stat.S_ISLNK(
                directory_info.st_mode
            ),
            "Machine registry is not "
            "a real directory",
        )

        require(
            stat.S_IMODE(
                directory_info.st_mode
            )
            == 0o700,
            "Machine registry mode is not 0700",
        )

        require(
            directory_info.st_uid
            == os.getuid(),
            "Machine registry owner changed",
        )

        require(
            stat.S_ISREG(
                file_info.st_mode
            )
            and not stat.S_ISLNK(
                file_info.st_mode
            ),
            "Machine record is not "
            "a real regular file",
        )

        require(
            stat.S_IMODE(
                file_info.st_mode
            )
            == 0o600,
            "Machine record mode is not 0600",
        )

        require(
            file_info.st_uid
            == os.getuid(),
            "Machine record owner changed",
        )

        loaded = read_machine(
            "development-01",
            state_home=state,
        )

        require(
            loaded == first,
            "persisted Machine record changed",
        )

        require(
            loaded["template"]
            == {
                "id": "development-workstation",
                "version": "1.0",
            },
            "Template identity/version "
            "was not pinned",
        )

        require(
            loaded["image"]
            == {
                "id": "arch",
                "sha256": ARCH_SHA256,
            },
            "Golden Image digest "
            "was not pinned",
        )

        require(
            loaded["network_profile"]
            == "services"
            and loaded["device_capability"]
            == "vfio",
            "network/GPU capability "
            "independence changed",
        )

        expect_contract_error(
            lambda: create_machine(
                first,
                state_home=state,
            ),
            "existing Machine was overwritten",
        )

        second = machine(
            "development-02"
        )
        second["display_name"] = (
            "Development 02"
        )

        create_machine(
            second,
            state_home=state,
        )

        inventory = list_machines(
            state_home=state,
        )

        require(
            [
                item["id"]
                for item in inventory
            ]
            == [
                "development-01",
                "development-02",
            ],
            "Machine inventory is not stable "
            "and sorted",
        )


def verify_runtime_authority_refusal() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-authority-"
    ) as temporary:
        state = (
            Path(temporary)
            / "state"
        )

        forbidden = {
            "state": "running",
            "trust": "dev",
            "provenance": "dev",
            "gpu_owner": "development-01",
            "transport_available": True,
        }

        for key, value in forbidden.items():
            record = copy.deepcopy(
                machine()
            )
            record[key] = value

            expect_contract_error(
                lambda record=record: create_machine(
                    record,
                    state_home=state,
                ),
                f"runtime authority field "
                f"{key} was accepted",
            )

        require(
            not state.exists(),
            "rejected Machine intent "
            "created persistent state",
        )


def verify_file_refusals() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-files-"
    ) as temporary:
        root = Path(
            temporary
        )
        state = root / "state"

        path = create_machine(
            machine(),
            state_home=state,
        )

        path.chmod(
            0o644
        )

        expect_unavailable(
            lambda: read_machine(
                "development-01",
                state_home=state,
            ),
            "unsafe Machine record mode "
            "was accepted",
        )

    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-symlink-file-"
    ) as temporary:
        root = Path(
            temporary
        )
        state = root / "state"
        machines = (
            state
            / "hyperlab"
            / "machines"
        )

        machines.mkdir(
            parents=True,
            mode=0o700,
        )

        target = (
            root
            / "target.yml"
        )

        target.write_text(
            "not a Machine\n",
            encoding="utf-8",
        )

        (
            machines
            / "development-01.yml"
        ).symlink_to(
            target
        )

        expect_unavailable(
            lambda: read_machine(
                "development-01",
                state_home=state,
            ),
            "symlinked Machine record "
            "was accepted",
        )

    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-symlink-dir-"
    ) as temporary:
        root = Path(
            temporary
        )
        state = root / "state"
        hyperlab = (
            state
            / "hyperlab"
        )
        target = (
            root
            / "target"
        )

        hyperlab.mkdir(
            parents=True,
            mode=0o700,
        )
        target.mkdir(
            mode=0o700,
        )

        (
            hyperlab
            / "machines"
        ).symlink_to(
            target,
            target_is_directory=True,
        )

        expect_unavailable(
            lambda: create_machine(
                machine(),
                state_home=state,
            ),
            "symlinked Machine registry "
            "directory was accepted",
        )

        require(
            not (
                target
                / "development-01.yml"
            ).exists(),
            "registry wrote through "
            "a symlinked directory",
        )


def verify_filename_identity() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-identity-"
    ) as temporary:
        state = (
            Path(temporary)
            / "state"
        )

        path = create_machine(
            machine(),
            state_home=state,
        )

        renamed = (
            path.parent
            / "development-99.yml"
        )

        path.rename(
            renamed
        )

        expect_unavailable(
            lambda: read_machine(
                "development-99",
                state_home=state,
            ),
            "filename/id mismatch "
            "was accepted",
        )


def main() -> int:
    verify_persistent_registry()
    verify_runtime_authority_refusal()
    verify_file_refusals()
    verify_filename_identity()

    print(
        "C10 persistent Machine registry contract: OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
