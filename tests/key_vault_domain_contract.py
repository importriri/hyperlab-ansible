#!/usr/bin/env python3
"""The key vault Machine and its clients, as planned and rendered (ADR 0048).

  1. A vault plans with network "none" and renders with no interface and one
     vsock device; a client keeps its network and gains the vsock device; a
     Machine that is neither has no vsock device.
  2. The plan refuses: network "none" for anything but the vault, a vault on
     a network, a VFIO or disposable vault, a vault with the guest agent or
     the clipboard, a vault or client that is not Linux, an unknown role.
  3. The domain XML guard accepts each rendered domain and refuses a live
     domain that gained a vsock device or an interface it was not planned
     with, or lost the one it was.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import guest_contract  # noqa: E402
from graphics_exposure_contract import guard, mutate  # noqa: E402

VSOCK = '<vsock model="virtio">\n      <cid auto="yes"/>\n    </vsock>'


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def plan_for(changes: dict, manifest_changes: dict | None = None) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec_path, store = guest_contract.standard_fixture(root)
        spec = yaml.safe_load(spec_path.read_text())
        spec.update({"lifecycle": "permanent", **changes})
        guest_contract.write_yaml(spec_path, spec)
        if manifest_changes:
            manifest_path = root / "images/debian.yml"
            manifest = yaml.safe_load(manifest_path.read_text())
            manifest.update(manifest_changes)
            guest_contract.write_yaml(manifest_path, manifest)
        return guest_contract.run(sys.executable, str(guest_contract.PLAN), "--root", str(root),
                                  "--spec", str(spec_path), "--store", str(store))


def render(changes: dict) -> str:
    result = plan_for(changes)
    require(result.returncode == 0, f"the plan refused {changes}: {result.stderr}")
    plan = json.loads(result.stdout)
    return guest_contract.template_env().get_template("domain.xml.j2").render(
        guest_plan=plan, guest_resolved_memory_mb=2048, guest_vfio={})


VAULT = {"key_vault": "vault", "network_profile": "none", "qemu_guest_agent": False}


def main() -> int:
    vault = render(VAULT)
    client = render({"key_vault": "client"})
    plain = render({})
    require("<interface" not in vault and vault.count("<vsock") == 1 and VSOCK in vault,
            "the vault has an interface or no vsock device")
    require(client.count("<interface") == 1 and VSOCK in client, "a client lost its network or has no vsock")
    require("<vsock" not in plain and plain.count("<interface") == 1, "a plain Machine gained a vsock device")

    refused = {
        "network none without the vault role": ({"network_profile": "none"}, None),
        "network none for a client": ({"network_profile": "none", "key_vault": "client"}, None),
        "a vault on a network": ({**VAULT, "network_profile": "lab"}, None),
        "a disposable vault": ({**VAULT, "lifecycle": "disposable"}, None),
        "a vault with the guest agent": ({**VAULT, "qemu_guest_agent": True}, None),
        "a vault with the clipboard": ({**VAULT, "clipboard": True}, None),
        "a VFIO vault": ({**VAULT, "device_profile": "vfio"}, {"supports": {
            "standard": True, "vfio": True, "cloud_init": True, "qemu_guest_agent": True}}),
        "a Windows client": ({"key_vault": "client", "qemu_guest_agent": False},
                             {"os_family": "windows", "supports": {"standard": True, "vfio": False,
                                                                   "cloud_init": False,
                                                                   "qemu_guest_agent": False}}),
        "a vault without cloud-init": (VAULT, {"supports": {"standard": True, "vfio": False, "cloud_init": False,
                                                            "qemu_guest_agent": True}}),
        "an unknown role": ({"key_vault": "agent"}, None),
    }
    for label, (changes, manifest_changes) in refused.items():
        result = plan_for(changes, manifest_changes)
        require(result.returncode != 0, f"the plan accepted {label}")

    for name, xml in (("vault", vault), ("client", client), ("plain", plain)):
        result = guard(xml, xml)
        require(result.returncode == 0, f"the guard refused the rendered {name} domain: {result.stderr}")
    live = {
        "a vsock device added to a plain Machine": (plain, mutate(plain, "    <memballoon", f"    {VSOCK}\n    <memballoon")),
        "an interface added to the vault": (vault, mutate(vault, "    <serial", '    <interface type="network">'
                                                          '<source network="dev"/><model type="virtio"/>'
                                                          '</interface>\n    <serial')),
        "a client's vsock device removed": (client, mutate(client, f"    {VSOCK}\n", "")),
        "a second vsock device on the vault": (vault, mutate(vault, f"    {VSOCK}\n", f"    {VSOCK}\n    {VSOCK}\n")),
    }
    for label, (expected, actual) in live.items():
        result = guard(expected, actual)
        require(result.returncode == 1 and "drift" in result.stderr, f"the guard accepted {label}: {result.stderr}")
    print("Key vault domain contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
