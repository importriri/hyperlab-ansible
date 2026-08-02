#!/usr/bin/env python3
"""Structural contracts for the operator-facing playbook hierarchy."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> Any:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def role_name(entry: Any) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        return str(entry.get("role"))
    raise AssertionError(f"unexpected role entry: {entry!r}")


def test_foundation_is_the_complete_headless_host_target() -> None:
    plays = load_yaml("playbooks/foundation.yml")
    assert len(plays) == 1
    play = plays[0]
    assert play["hosts"] == "hypervisor"
    roles = [role_name(entry) for entry in play["roles"]]
    assert roles == [
        "base",
        "hardware_probe",
        "kvm_host",
        "vfio_boot",
        "network_domains",
        "lab_isolation",
        "gpu_handoff",
        "brick_guard",
        "bootstrap_storage",
        "brick_guard",
        "image_store",
    ]
    assert "desktop" not in roles and "looking_glass" not in roles
    assert "guest" not in roles and "image_factory" not in roles


def test_lab_adds_only_the_interactive_host_layer() -> None:
    plays = load_yaml("playbooks/lab.yml")
    assert plays[0]["name"] == "Assemble the headless foundation first"
    assert plays[0]["import_playbook"] == "foundation.yml"
    assert plays[1]["hosts"] == "hypervisor"
    roles = [role_name(entry) for entry in plays[1]["roles"]]
    assert roles == ["desktop", "brick_guard", "looking_glass"]
    assert roles.index("desktop") < roles.index("looking_glass")
    text = (ROOT / "playbooks/lab.yml").read_text(encoding="utf-8")
    assert "guest" not in text and "image_factory" not in text


def test_targeted_playbooks_remain_available() -> None:
    desktop = load_yaml("playbooks/desktop.yml")[0]
    looking_glass = load_yaml("playbooks/looking-glass.yml")[0]
    assert desktop["hosts"] == "hypervisor:workstations"
    assert desktop["roles"] == ["desktop"]
    assert looking_glass["hosts"] == "hypervisor"
    assert [role_name(entry) for entry in looking_glass["roles"]] == [
        "brick_guard",
        "looking_glass",
    ]


def test_operator_docs_match_the_playbook_topology() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    adr = (ROOT / "docs/adr/0013-cockpit-surface.md").read_text(encoding="utf-8")
    desktop_defaults = (ROOT / "roles/desktop/defaults/main.yml").read_text(encoding="utf-8")
    assert "`playbooks/lab.yml` imports the complete foundation" in readme
    assert "`desktop.yml` and `looking-glass.yml` playbooks remain available for focused" in readme
    assert "which `lab.yml` mounts before `looking_glass`" in adr
    assert "foundation.yml keeps a recovery host blind (TTY)" in desktop_defaults
    stale_claims = (
        "lab.yml` never mounts",
        "never by lab.yml",
        "never pulled in by the base lab playbook",
    )
    current_contract = "\n".join((readme, adr, desktop_defaults))
    assert not any(claim in current_contract for claim in stale_claims)


def test_vfio_is_the_managed_loader_default() -> None:
    tasks = (ROOT / "roles/vfio_boot/tasks/main.yml").read_text(encoding="utf-8")
    assert "line: default Arch-Linux-Hardened-Vfio.conf" in tasks
    assert "line: default Arch-Linux-Hardened.conf" not in tasks
    assert "Make VFIO the normal laboratory boot path" in tasks


def main() -> int:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"playbook topology contract: OK ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
