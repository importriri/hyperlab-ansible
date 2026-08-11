#!/usr/bin/env python3
"""Focused M10 software contract.

The complete repository verifier remains authoritative. This test exercises the
new manifest matrix, generated-spec boundary and Linux/Windows VFIO split.
"""

from __future__ import annotations

import importlib.util
import stat
import sys
import tempfile
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))

from hyperlabctl.composer import build_spec, catalog, generated_specs, write_spec
from hyperlabctl.errors import ContractError


def write_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def manifest(
    image_id,
    os_family="linux",
    sealed=True,
    vfio=True,
    cloud_init=True,
    networks=None,
    singleton=False,
):
    return {
        "schema_version": 1,
        "id": image_id,
        "display_name": image_id,
        "status": "sealed" if sealed else "not-built",
        "sha256": "a" * 64 if sealed else None,
        "private": os_family == "windows",
        "contains_personal_data": False,
        "generalized": True,
        "instance_policy": "singleton" if singleton else "multiple",
        "os_family": os_family,
        "os_variant": "generic",
        "format": "qcow2",
        "filename": image_id + ".qcow2",
        "virtual_size_gib": 20,
        "minimum_size_gib": 8,
        "min_memory_mb": 2048,
        "supports": {
            "standard": True,
            "vfio": vfio,
            "cloud_init": cloud_init,
            "qemu_guest_agent": True,
        },
        "requires": {"uefi": True, "secure_boot": False, "tpm2": False},
        "defaults": {
            "lifecycle": "permanent",
            "device_profile": "standard",
            "network_profile": "dev",
        },
        "network_allowlist": networks
        or ["clean", "dirty", "dev", "lab", "services"],
        "looking_glass_host_build_required": (
            "B7-263-g0140a3f6fb" if os_family == "windows" else None
        ),
    }


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def assert_true(value, message):
    if not value:
        raise AssertionError(message)


def main():
    temporary = tempfile.TemporaryDirectory()
    root = Path(temporary.name)
    try:
        (root / "vm-specs").mkdir()
        write_yaml(root / "images/arch.yml", manifest("arch"))
        write_yaml(
            root / "images/win11clean.yml",
            manifest(
                "win11clean",
                os_family="windows",
                cloud_init=False,
                networks=["clean", "dev"],
                singleton=True,
            ),
        )
        write_yaml(
            root / "images/fedora.yml",
            manifest("fedora", sealed=False),
        )

        entries = {entry["id"]: entry for entry in catalog(root)}
        assert_true("vfio" in entries["arch"]["device_profiles"], "Arch VFIO absent")
        assert_true(
            "services" not in entries["arch"]["network_profiles_by_device"]["vfio"],
            "services offered to VFIO",
        )
        assert_true(not entries["fedora"]["ready"], "unsealed Fedora shown ready")

        linux = build_spec(
            root,
            "arch-vfio-test",
            "arch",
            "disposable",
            "vfio",
            "lab",
            "tester",
        )
        assert_true(linux["looking_glass"] is False, "Linux VFIO enabled LG")
        windows = build_spec(
            root,
            "win11clean-test",
            "win11clean",
            "permanent",
            "vfio",
            "clean",
            "tester",
        )
        assert_true(windows["looking_glass"] is True, "Windows VFIO lacks LG")

        try:
            build_spec(
                root,
                "bad-services",
                "arch",
                "permanent",
                "vfio",
                "services",
                "tester",
            )
        except ContractError:
            pass
        else:
            raise AssertionError("VFIO services combination accepted")

        try:
            build_spec(
                root,
                "blocked-fedora",
                "fedora",
                "permanent",
                "standard",
                "dev",
                "tester",
            )
        except ContractError:
            pass
        else:
            raise AssertionError("unsealed image composition accepted")

        path = write_spec(root, linux)
        written = root / path
        assert_true(written.is_file(), "generated spec missing")
        assert_true(
            stat.S_IMODE(written.stat().st_mode) == 0o600,
            "generated spec mode is not 0600",
        )
        payload = written.read_text(encoding="utf-8")
        sequence_lines = [
            line for line in payload.splitlines() if line.lstrip().startswith("- ")
        ]
        assert_true(sequence_lines, "generated spec lacks a block sequence fixture")
        assert_true(
            all(len(line) - len(line.lstrip()) >= 2 for line in sequence_lines),
            "generated spec contains an indentless block sequence",
        )
        assert_true(
            yaml.safe_load(payload) == linux,
            "generated spec serialization changed its values",
        )
        assert_true(generated_specs(root) == [path], "generated list drift")

        guest_plan = load_module(ROOT / "tools/guest_plan.py", "m10_guest_plan")
        store = root / "store"
        plan = guest_plan.build_plan(root, path, store)
        assert_true(plan["device_profile"] == "vfio", "guest plan lost VFIO")
        assert_true(plan["looking_glass"] is False, "guest plan re-enabled LG")

        vfio_plan = load_module(ROOT / "tools/vfio_plan.py", "m10_vfio_plan")
        result = vfio_plan.build_vfio_plan(
            plan,
            {
                "host_profile": "test",
                "gpu_pci": "01:00.0",
                "gpu_audio_pci": "01:00.1",
                "vfio_devices": [
                    {"pci": "01:00.0", "id": "10de:0001"},
                    {"pci": "01:00.1", "id": "10de:0002"},
                ],
            },
            {"test": {"vfio_ids": ["10de:0001", "10de:0002"]}},
            {"lab": 0},
            "B7-263-g0140a3f6fb",
            "/dev/kvmfr0",
            64,
            "127.0.0.1",
            5900,
        )
        assert_true(
            result["looking_glass_enabled"] is False,
            "Linux VFIO plan enabled LG",
        )
        assert_true(
            result["looking_glass_shm_bytes"] is None,
            "Linux VFIO allocated kvmfr",
        )

        manager = (
            ROOT
            / "roles/host_desktop_sway/files/privatestack-hyperlab-domains.py"
        )
        source = manager.read_text(encoding="utf-8")
        assert_true("shell=True" not in source, "manager uses shell=True")
        assert_true("eval(" not in source, "manager uses eval")
        compile(source, str(manager), "exec")

        registry = (
            ROOT / "tools/hyperlabctl/hyperlabctl/registry.py"
        ).read_text(encoding="utf-8")
        for action_id in (
            "domain.manager",
            "vm.console",
            "vm.looking-glass",
            "image.validate",
        ):
            assert_true(
                '"id": "%s"' % action_id in registry,
                "missing action %s" % action_id,
            )
        for command in (
            '["hyperlabctl", "open", "manager"]',
            '["hyperlabctl", "open", "console", "{domain}"]',
            '["hyperlabctl", "open", "looking-glass"]',
        ):
            assert_true(command in registry, "unprivileged action bypasses CLI")

        waybar = (
            ROOT / "roles/host_desktop_sway/files/waybar.jsonc"
        ).read_text(encoding="utf-8")
        render_contract = (ROOT / "tests/render.yml").read_text(encoding="utf-8")
        manager_click = (
            "/usr/local/bin/privatestack-hyperlab-domains "
            "--surface drawer --section vms"
        )
        assert_true(
            '"on-click": "%s"' % manager_click in waybar,
            "Waybar VM pill does not enter the resident CLI-backed drawer",
        )
        assert_true(
            "- %s" % manager_click in render_contract,
            "render contract does not allow the resident VM drawer click",
        )
        assert_true(
            'CLI = "/usr/local/bin/hyperlabctl"' in source,
            "resident manager is no longer backed by hyperlabctl",
        )

        open_command = (
            ROOT / "tools/hyperlabctl/hyperlabctl/commands/open.py"
        ).read_text(encoding="utf-8")
        assert_true("shell=True" not in open_command, "open command uses shell")
        assert_true("os.system" not in open_command, "open command uses os.system")
        assert_true("os.execv(" in open_command, "open command does not preserve argv")
        compile(open_command, "open.py", "exec")

        template = (
            ROOT / "roles/guest/templates/domain.xml.j2"
        ).read_text(encoding="utf-8")
        assert_true(
            "guest_plan.device_profile == 'vfio' and guest_plan.looking_glass"
            in template,
            "kvmfr commandline is not LG-conditional",
        )

        print("M10 domain manager contract: OK")
        return 0
    finally:
        temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
