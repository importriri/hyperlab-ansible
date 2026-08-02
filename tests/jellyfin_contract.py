#!/usr/bin/env python3
"""Structural contracts for the M8 Jellyfin appliance and future service slots."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]


def load_yaml(path: str) -> Any:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def test_jellyfin_contract_identity_and_exposure() -> None:
    services = load_yaml("group_vars/all/services.yml")
    spec = load_yaml("service-specs/svc-jellyfin.yml")
    vm = load_yaml("vm-specs/svc-jellyfin.yml")
    inventory = (ROOT / "inventory.ini").read_text(encoding="utf-8")
    jellyfin_vars = load_yaml("group_vars/all/jellyfin.yml")

    assert services["service_lan_exposure_allowlist"] == ["tcp/8096"]
    assert spec["exposures"] == ["tcp/8096"]
    assert spec["dhcp"] == {"mac": "52:54:00:66:29:6e", "ip": "10.10.5.10"}
    assert vm["name"] == spec["vm"] == "svc-jellyfin"
    assert vm["network_profile"] == "services"
    assert vm["device_profile"] == "standard"
    assert vm["lifecycle"] == "permanent"
    assert vm["autostart"] is False and vm["memory_overcommit"] is False
    assert "[jellyfin]\nsvc-jellyfin" in inventory
    assert "ansible_host=10.10.5.10" in inventory
    assert jellyfin_vars["jellyfin_http_port"] == 8096
    assert jellyfin_vars["jellyfin_health_url"].startswith("http://127.0.0.1:8096/")


def test_jellyfin_role_stays_inside_the_guest() -> None:
    tasks_text = (ROOT / "roles/jellyfin/tasks/main.yml").read_text(encoding="utf-8")
    defaults = load_yaml("roles/jellyfin/defaults/main.yml")
    playbook = load_yaml("playbooks/jellyfin.yml")

    assert defaults["jellyfin_packages"] == ["jellyfin"]
    assert defaults["jellyfin_prerequisite_packages"] == ["ca-certificates", "extrepo"]
    assert "repo.jellyfin.org" in tasks_text
    assert "extrepo" in tasks_text
    assert "ansible.builtin.get_url" not in tasks_text
    assert "ansible.builtin.shell" not in tasks_text
    assert "curl" not in tasks_text and "wget" not in tasks_text
    assert "docker" in tasks_text and "podman" in tasks_text
    assert "state: present" in tasks_text
    assert "jellyfin.service" in (ROOT / "roles/jellyfin/defaults/main.yml").read_text()
    assert "127.0.0.1" in tasks_text and "jellyfin_health_url" in tasks_text
    assert "owner: root" in tasks_text and "group: jellyfin" in tasks_text and 'mode: "0750"' in tasks_text

    assert playbook[0]["hosts"] == "hypervisor"
    first_roles = [entry if isinstance(entry, str) else entry.get("role") for entry in playbook[0]["roles"]]
    assert first_roles == [
        "brick_guard",
        "service_registry",
        "brick_guard",
        "service_exposure",
        "brick_guard",
        "guest",
    ]
    assert playbook[1]["hosts"] == "jellyfin"
    assert playbook[1]["roles"] == ["jellyfin"]
    assert playbook[1]["pre_tasks"][0]["ansible.builtin.wait_for_connection"]["timeout"] == 300


def test_exposure_role_is_host_plumbing_only() -> None:
    tasks = (ROOT / "roles/service_exposure/tasks/main.yml").read_text(encoding="utf-8")
    handler = (ROOT / "roles/service_exposure/handlers/main.yml").read_text(encoding="utf-8")
    hook = (ROOT / "roles/service_exposure/files/qemu-hook").read_text(encoding="utf-8")
    plan = (ROOT / "tools/service_exposure_plan.py").read_text(encoding="utf-8")
    apply = (ROOT / "tools/service_exposure_apply.py").read_text(encoding="utf-8")

    assert "M8 may expose only svc-jellyfin tcp/8096" in tasks
    assert "service_exposure_receipt_guard_tool" in tasks
    assert tasks.index("Verify the M7 service registration receipt before exposure") < tasks.index(
        "Install nftables for service exposure"
    )
    assert "Install the static qemu.d service exposure hook" in tasks
    assert "libvirtd.service" in handler and "Refuse libvirt hook reload while any domain is active" in handler
    assert "/etc/libvirt/hooks/qemu.d/50-service-exposure" in (
        ROOT / "group_vars/all/service-exposure.yml"
    ).read_text()
    assert hook.startswith("#!/usr/bin/env bash\n")
    assert ">/dev/null" in hook and "set -euo pipefail" in hook
    assert "exactly one default-route interface" in plan
    assert "physical/default-route interface" in plan
    assert "privatestack_services" in plan and "guest_input" in plan
    assert "COMMENT_PREFIX" in apply and "matching_rule_handles" in apply
    assert "delete rule" not in apply
    assert "flush ruleset" not in apply
    assert "dnat to" in apply and "new,established" in apply


def test_future_service_slots_are_inert() -> None:
    slots = load_yaml("group_vars/all/service-slots.yml")["service_slots"]
    leases = load_yaml("group_vars/all/services.yml")["service_dhcp_leases"]
    brick_graph = load_yaml("group_vars/all/bricks.yml")["brick_requires"]
    inventory = (ROOT / "inventory.ini").read_text(encoding="utf-8")
    active_specs = {path.stem for path in (ROOT / "service-specs").glob("*.yml")}
    active_vm_specs = {path.stem for path in (ROOT / "vm-specs").glob("*.yml")}
    lease_names = {entry["name"] for entry in leases}

    assert set(slots) == {"nextcloud", "vaultwarden", "immich", "pihole"}
    for name, slot in slots.items():
        service_id = slot["service_id"]
        assert slot["status"] == "planned"
        assert slot["application_role"] is None
        assert slot["service_spec"] is None and slot["vm_spec"] is None
        assert service_id not in lease_names
        assert service_id not in active_specs
        assert service_id not in active_vm_specs
        assert service_id not in inventory
        assert name not in brick_graph
        assert not (ROOT / "roles" / name).exists()
    assert (ROOT / "docs/service-slots.md").is_file()


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"jellyfin contract: OK ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
