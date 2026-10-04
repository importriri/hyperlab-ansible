#!/usr/bin/env python3
"""C10 product Machine CLI and inventory separation contract."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/hyperlabctl/bin/hyperlabctl"

sys.path.insert(
    0,
    str(ROOT / "tools/hyperlabctl"),
)

from hyperlabctl.commands import REGISTRY
from hyperlabctl.commands import machine as machine_command


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
    path.write_text(
        yaml.safe_dump(
            payload,
            sort_keys=False,
        ),
        encoding="utf-8",
    )


def prepare_repo(
    root: Path,
) -> None:
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
            "dirty",
            "lab",
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

    write_yaml(
        root
        / "templates"
        / "development-workstation.yml",
        template,
    )


def run_cli(
    repo: Path,
    state: Path,
    *arguments: str,
) -> dict:
    env = {
        **os.environ,
        "XDG_STATE_HOME": str(
            state
        ),
        "PYTHONDONTWRITEBYTECODE": "1",
    }

    result = subprocess.run(
        [
            str(CLI),
            "--repo",
            str(repo),
            "--json",
            "machine",
            *arguments,
        ],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )

    require(
        result.returncode == 0,
        "Machine CLI failed: "
        + result.stderr
        + result.stdout,
    )

    return json.loads(
        result.stdout
    )


def runtime_domain(
    name: str,
    *,
    state: str,
    device_profile: str,
    provenance: str,
    product_managed: bool = False,
    image: str | None = None,
    image_sha256: str | None = None,
    gpu_handoff_profile: str | None = None,
) -> dict:
    return {
        "name": name,
        "state": state,
        "memory_mb": 8192,
        "network": provenance,
        "networks": [
            provenance
        ],
        "vcpus": 4,
        "vfio": (
            device_profile == "vfio"
        ),
        "managed": True,
        "product_managed": product_managed,
        "image": image,
        "image_sha256": image_sha256,
        "device_profile": device_profile,
        "lifecycle": "permanent",
        "network_profile": provenance,
        "gpu_handoff_profile": gpu_handoff_profile,
        "gpu_trust_profile": gpu_handoff_profile,
        # Mirrors providers/domains.py: a product Machine row always carries
        # the observed root GPU policy state.
        "gpu_policy_state": (
            ("legacy-static" if gpu_handoff_profile else "not-configured")
            if not product_managed
            else "verified"
            if device_profile == "vfio"
            else "not-required"
        ),
        "trust_profile": provenance,
        "trust_source": "network-profile",
        "blocked": None,
    }


def verify_first_install_is_product_empty(
    state: Path,
) -> None:
    original = machine_command.doc.build

    def forbidden_runtime(*_args, **_kwargs):
        raise AssertionError(
            "empty product inventory touched libvirt"
        )

    machine_command.doc.build = forbidden_runtime

    try:
        payload = (
            machine_command.build_product_inventory(
                object(),
                state_home=state,
            )
        )
    finally:
        machine_command.doc.build = original

    require(
        payload["machines_available"] is True,
        "empty product registry became unavailable",
    )

    require(
        payload["machines"] == [],
        "first install inherited raw libvirt domains",
    )

    require(
        payload["runtime_available"] is None,
        "empty registry unnecessarily queried runtime",
    )


def verify_runtime_filtering(
    state: Path,
) -> None:
    original = machine_command.doc.build

    record = machine_command.read_machine(
        "development-01",
        state_home=state,
    )

    unrelated = runtime_domain(
        "arch-dev-vfio",
        state="shut off",
        device_profile="vfio",
        provenance="dev",
    )

    machine_command.doc.build = (
        lambda *_args, **_kwargs: {
            "domains": [
                unrelated
            ],
            "gpu": {
                "held_by": None,
                "bound": True,
            },
            "problems": [],
        }
    )

    try:
        payload = (
            machine_command.build_product_inventory(
                object(),
                state_home=state,
            )
        )
    finally:
        machine_command.doc.build = original

    require(
        [
            row["name"]
            for row in payload["machines"]
        ]
        == [
            "development-01"
        ],
        "raw fixture leaked into product inventory",
    )

    require(
        payload["machines"][0]["state"]
        == "not-created",
        "unrelated libvirt fixture became Machine runtime",
    )

    require(
        payload["machines"][0]["provenance"]
        == "unclassified",
        "persistent Machine intent invented provenance",
    )

    matching = runtime_domain(
        "development-01",
        state="running",
        device_profile="standard",
        provenance="dev",
        product_managed=True,
        image=record["image"]["id"],
        image_sha256=record["image"]["sha256"],
        gpu_handoff_profile=record["gpu_handoff_profile"],
    )

    machine_command.doc.build = (
        lambda *_args, **_kwargs: {
            "domains": [
                unrelated,
                matching,
            ],
            "gpu": {
                "held_by": None,
                "bound": True,
            },
            "problems": [],
        }
    )

    try:
        payload = (
            machine_command.build_product_inventory(
                object(),
                state_home=state,
            )
        )
    finally:
        machine_command.doc.build = original

    row = payload["machines"][0]

    require(
        row["state"] == "running"
        and row["provenance"] == "dev"
        and row["runtime_present"] is True
        and row["runtime_drift"] is False,
        "matching managed runtime was not adopted",
    )

    # Without a checkout the operating system is unknown, never guessed.
    require(row["os"] is None, "an operating system was invented without a checkout")

    class Config:
        repo_root = ROOT

    class Context:
        config = Config()

    machine_command.doc.build = lambda *_args, **_kwargs: {
        "domains": [unrelated, matching],
        "gpu": {"held_by": None, "bound": True},
        "problems": [],
    }
    try:
        named = machine_command.build_product_inventory(Context(), state_home=state)
    finally:
        machine_command.doc.build = original
    require(named["machines"][0]["os"] == "Arch Linux",
            f"the operating system was not read from the image: {named['machines'][0].get('os')}")

    missing_root_policy = dict(
        matching
    )
    missing_root_policy["device_profile"] = "vfio"
    missing_root_policy["gpu_handoff_profile"] = "dev"
    missing_root_policy["gpu_trust_profile"] = None
    missing_root_policy["gpu_policy_state"] = "missing"

    require(
        not machine_command._runtime_matches_machine(
            missing_root_policy,
            {
                **record,
                "device_capability": "vfio",
                "gpu_handoff_profile": "dev",
            },
        ),
        "product VFIO runtime accepted metadata "
        "without verified root GPU policy",
    )

    wrong_digest = dict(
        matching
    )
    wrong_digest["image_sha256"] = "f" * 64

    machine_command.doc.build = (
        lambda *_args, **_kwargs: {
            "domains": [
                wrong_digest
            ],
            "gpu": {
                "held_by": None,
                "bound": True,
            },
            "problems": [],
        }
    )

    try:
        payload = (
            machine_command.build_product_inventory(
                object(),
                state_home=state,
            )
        )
    finally:
        machine_command.doc.build = original

    require(
        payload["machines"][0]["state"]
        == "configuration-drift"
        and payload["machines"][0]["runtime_drift"]
        is True,
        "wrong Golden Image digest was adopted "
        "as product runtime",
    )

    drifted = runtime_domain(
        "development-01",
        state="running",
        device_profile="vfio",
        provenance="dev",
        product_managed=True,
        image=record["image"]["id"],
        image_sha256=record["image"]["sha256"],
        gpu_handoff_profile="dev",
    )

    machine_command.doc.build = (
        lambda *_args, **_kwargs: {
            "domains": [
                drifted
            ],
            "gpu": {
                "held_by": None,
                "bound": True,
            },
            "problems": [],
        }
    )

    try:
        payload = (
            machine_command.build_product_inventory(
                object(),
                state_home=state,
            )
        )
    finally:
        machine_command.doc.build = original

    row = payload["machines"][0]

    require(
        row["state"] == "configuration-drift"
        and row["provenance"] == "unclassified"
        and row["runtime_drift"] is True,
        "runtime drift was trusted as product state",
    )


def verify_cli() -> None:
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-c10-machine-cli-"
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

        require(
            "machine" in REGISTRY,
            "Machine command was not discovered",
        )

        verify_first_install_is_product_empty(
            state
        )

        templates = run_cli(
            repo,
            state,
            "templates",
        )

        require(
            len(
                templates["templates"]
            )
            == 1
            and templates[
                "templates"
            ][0]["id"]
            == "development-workstation",
            "Template catalogue was not exposed",
        )

        empty = run_cli(
            repo,
            state,
            "list",
        )

        require(
            empty["machines"] == [],
            "fresh product Machine list is not empty",
        )

        inventory = run_cli(
            repo,
            state,
            "inventory",
        )

        require(
            inventory["machines_available"] is True
            and inventory["machines"] == [],
            "first-install CLI inventory is not empty",
        )

        created = run_cli(
            repo,
            state,
            "create",
            "development-workstation",
            "development-01",
            "--display-name",
            "Development 01",
            "--owner",
            "tester",
        )

        machine = created[
            "machine"
        ]

        require(
            machine["id"] == "development-01"
            and machine["device_capability"]
            == "standard"
            and machine["network_profile"]
            == "dev",
            "Machine create changed Template defaults",
        )

        require(
            not (
                repo
                / "vm-specs"
                / ".generated"
                / "development-01.yml"
            ).exists(),
            "Machine create implicitly projected a VM spec",
        )

        listed = run_cli(
            repo,
            state,
            "list",
        )

        require(
            [
                item["id"]
                for item in listed["machines"]
            ]
            == [
                "development-01"
            ],
            "persistent Machine list changed",
        )

        shown = run_cli(
            repo,
            state,
            "show",
            "development-01",
        )

        require(
            shown["template"]["version"] == "1.0",
            "Machine show lost Template pin",
        )

        verify_runtime_filtering(
            state
        )

        projected = run_cli(
            repo,
            state,
            "project",
            "development-01",
        )

        require(
            projected["spec"]
            == "vm-specs/.generated/"
            "development-01.yml",
            "Machine projection path changed",
        )

        spec_text = (
            repo
            / projected["spec"]
        ).read_text(
            encoding="utf-8"
        )

        require(
            "device_profile: standard"
            in spec_text
            and "device_capability:"
            not in spec_text,
            "derived VM spec crossed the naming boundary",
        )

        projected_document = yaml.safe_load(
            spec_text
        )

        require(
            projected_document["image_sha256"]
            == machine["image"]["sha256"],
            "CLI projection lost the Machine Golden digest pin",
        )


def verify_shell_binding() -> None:
    bridge = (
        ROOT
        / "roles/host_desktop_sway/files/"
        "privatestack-hyperlab.sh"
    ).read_text(
        encoding="utf-8"
    )

    require(
        "[[ ${field} == vms ]]"
        in bridge
        and "machine inventory --json"
        in bridge,
        "vms bridge does not use product inventory",
    )

    require(
        "[[ ${field} == diagnostics-domains ]]"
        in bridge
        and "waybar --field vms"
        in bridge,
        "Diagnostics has no raw domain observation",
    )

    state = (
        ROOT
        / "roles/host_desktop_common/files/"
        "quickshell/hyperlab/ShellState.qml"
    ).read_text(
        encoding="utf-8"
    )

    require(
        '"diagnostics-domains"' in state
        and "state.applyOutsideDomainsPayload(this.text)" in state
        and "state.applyMachinePayload(this.text)" in state,
        "raw domains and product Machines share one source",
    )

    stage = (
        ROOT
        / "roles/host_desktop_common/files/"
        "quickshell/hyperlab/MachineStage.qml"
    ).read_text(
        encoding="utf-8"
    )

    require(
        "No Machines yet"
        in stage,
        "Machines workspace kept legacy empty copy",
    )

    require(
        "This host has no libvirt domains"
        not in stage,
        "normal product workspace still describes raw libvirt inventory",
    )


def main() -> int:
    verify_cli()
    verify_shell_binding()

    print(
        "C10 Machine CLI and product inventory contract: OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
