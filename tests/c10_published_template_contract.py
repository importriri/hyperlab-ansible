#!/usr/bin/env python3
"""The published Templates resolve, through the real catalogue, to Machines
the existing planners accept, pinned to the sealed Golden Image digest."""

from __future__ import annotations

import importlib.util
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))

from hyperlabctl.errors import ContractError  # noqa: E402
from hyperlabctl.machine_factory import (  # noqa: E402
    materialize_machine,
    template_catalog,
    write_projected_vm_spec,
)


def load_tool(relative: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


guest_plan = load_tool("tools/guest_plan.py", "published_guest_plan")
vfio_plan = load_tool("tools/vfio_plan.py", "published_vfio_plan")
projection = load_tool("tests/c10_machine_vm_spec_projection_contract.py", "published_projection")

CREATED_AT = "2026-10-03T20:00:00Z"


def refused(message: str, template: str = "workstation-dev", **kwargs) -> None:
    try:
        materialize_machine(ROOT, template_id=template, machine_id="dev-01",
                            owner="sid", created_at=CREATED_AT, **kwargs)
    except ContractError as exc:
        assert message in str(exc), (message, str(exc))
        return
    raise AssertionError(f"{template} accepted {kwargs}")


def check_catalogue() -> None:
    entries = {entry["id"]: entry for entry in template_catalog(ROOT)}
    assert "workstation-dev" in entries, entries
    template = yaml.safe_load((ROOT / "templates/workstation-dev.yml").read_text())
    image = yaml.safe_load((ROOT / f"images/{template['image']}.yml").read_text())
    assert template["status"] == "ready"
    assert image["status"] == "sealed" and image["generalized"] is True
    assert image["contains_personal_data"] is False
    assert image["sha256"] == image["source_sha256"]
    # The image carries the NVIDIA-only session of the VFIO workstation it was
    # captured from, so the Template offers only VFIO Machines on dev.
    assert template["device_capabilities"] == {"standard": False, "vfio": True}
    assert template["network_allowlist"] == ["dev"]
    assert [name for name, on in template["gpu_handoff_profiles"].items() if on] == ["dev"]
    # Disposable Machines do not discard their writable layer yet.
    assert template["lifecycles"]["disposable"] is False
    assert template["presentation"]["workspace_profile"] == "dev"


def check_refusals() -> None:
    refused("does not permit device capability standard", device_capability="standard", gpu_handoff_profile=None)
    refused("does not permit network dirty", network_profile="dirty")
    refused("does not permit GPU handoff profile dirty", gpu_handoff_profile="dirty")
    refused("does not permit lifecycle disposable", lifecycle="disposable")
    refused("disk_gib must cover", resource_profile="custom", memory_mb=8192, vcpus=4, disk_gib=40)


def check_machine_to_plan() -> None:
    image = yaml.safe_load((ROOT / "images/arch-dev-20261003.yml").read_text())
    record = materialize_machine(ROOT, template_id="workstation-dev", machine_id="dev-01",
                                 owner="sid", created_at=CREATED_AT,
                                 looking_glass_mode="linux-experimental")
    assert record["image"] == {"id": "arch-dev-20261003", "sha256": image["sha256"]}
    assert record["template"] == {"id": "workstation-dev", "version": "1.0"}
    assert (record["device_capability"], record["gpu_handoff_profile"], record["network_profile"]) == ("vfio", "dev", "dev")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for name in ("images", "templates", "vm-specs", "group_vars", "schemas"):
            shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns(".generated"))
        path = write_projected_vm_spec(root, record)
        assert path == "vm-specs/.generated/dev-01.yml", path
        spec = yaml.safe_load((root / path).read_text())
        assert spec["image_sha256"] == image["sha256"]
        assert spec["clipboard"] is False and spec["shared_folders"] is False
        assert "managed-machine" in spec["tags"]

        plan = guest_plan.build_plan(root, path, root / "store")
        assert plan["image_sha256"] == image["sha256"]
        assert plan["base_path"].endswith("/bases/linux/arch-dev-20261003.qcow2")
        assert plan["cloud_init"] is True and plan["looking_glass_mode"] == "linux-experimental"
        assert plan["disk_gib"] >= image["virtual_size_gib"]

        result = vfio_plan.build_vfio_plan(
            plan, projection.hardware_report(), projection.host_profiles(),
            projection.TRUST_LEVELS, "B7-263-g0140a3f6fb", "/dev/kvmfr0", 64, "127.0.0.1", 5900,
        )
        assert result["gpu_handoff_profile"] == "dev" and result["trust_level"] == 2


def check_server_arch() -> None:
    template = yaml.safe_load((ROOT / "templates/server-arch.yml").read_text())
    image = yaml.safe_load((ROOT / "images/arch.yml").read_text())
    assert template["status"] == "ready" and image["status"] == "sealed"
    assert template["device_capabilities"] == {"standard": True, "vfio": False}
    assert not any(template["gpu_handoff_profiles"].values()), "a server Template offers the GPU"
    assert template["presentation"]["looking_glass_mode"] == "disabled"
    assert set(template["network_allowlist"]) == {"dev", "services", "lab"}

    refused("does not permit device capability vfio", template="server-arch",
            device_capability="vfio", gpu_handoff_profile="dev")
    refused("does not permit network clean", template="server-arch", network_profile="clean")
    refused("does not permit network dirty", template="server-arch", network_profile="dirty")
    refused("Looking Glass requires VFIO", template="server-arch", looking_glass_mode="linux-experimental")
    refused("does not permit resource profile minimum", template="server-arch", resource_profile="minimum")

    record = materialize_machine(ROOT, template_id="server-arch", machine_id="srv-01",
                                 owner="sid", created_at=CREATED_AT, network_profile="services",
                                 resource_profile="custom", memory_mb=2048, vcpus=2, disk_gib=16)
    assert record["image"] == {"id": "arch", "sha256": image["sha256"]}
    assert record["gpu_handoff_profile"] is None and record["device_capability"] == "standard"
    assert record["resources"] == {"memory_mb": 2048, "vcpus": 2, "disk_gib": 16}

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for name in ("images", "templates", "vm-specs", "group_vars", "schemas"):
            shutil.copytree(ROOT / name, root / name, ignore=shutil.ignore_patterns(".generated"))
        path = write_projected_vm_spec(root, record)
        plan = guest_plan.build_plan(root, path, root / "store")
        assert plan["device_profile"] == "standard" and plan["network_profile"] == "services"
        assert plan["looking_glass"] is False and plan["cloud_init"] is True
        assert plan["base_path"].endswith("/bases/linux/arch.qcow2")


def main() -> int:
    check_catalogue()
    check_refusals()
    check_machine_to_plan()
    check_server_arch()
    print("C10 published Template contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
