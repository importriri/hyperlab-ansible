#!/usr/bin/env python3
"""Structural contract for the libvirt KVMFR cgroup policy."""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    defaults_path = ROOT / "roles/looking_glass/defaults/main.yml"
    tasks_path = ROOT / "roles/looking_glass/tasks/main.yml"
    handlers_path = ROOT / "roles/looking_glass/handlers/main.yml"

    defaults = yaml.safe_load(
        defaults_path.read_text(encoding="utf-8")
    )
    tasks = tasks_path.read_text(encoding="utf-8")
    handlers = handlers_path.read_text(encoding="utf-8")

    assert defaults["looking_glass_qemu_conf"] == "/etc/libvirt/qemu.conf"
    assert defaults["looking_glass_libvirt_service"] == "libvirtd.service"

    required = defaults["looking_glass_cgroup_required_devices"]
    optional = defaults["looking_glass_cgroup_optional_devices"]

    for device in (
        "/dev/null",
        "/dev/full",
        "/dev/zero",
        "/dev/random",
        "/dev/urandom",
        "/dev/ptmx",
        "/dev/kvm",
    ):
        assert device in required

    assert optional == ["/dev/userfaultfd"]

    assert "Count active libvirt cgroup device ACL assignments" in tasks
    assert "Refuse an unmanaged libvirt cgroup device ACL" in tasks
    assert "looking_glass_qemu_acl_active_count" in tasks
    assert "looking_glass_qemu_acl_managed" in tasks
    assert "PRIVATESTACK KVMFR CGROUP ACL" in tasks
    assert "cgroup_device_acl = [" in tasks
    assert "+ [looking_glass_device]" in tasks
    assert "selectattr('stat.exists')" in tasks
    assert "Restart libvirtd for KVMFR cgroup policy" in tasks

    assert "Restart libvirtd for KVMFR cgroup policy" in handlers
    assert "ansible.builtin.systemd_service" in handlers
    assert 'name: "{{ looking_glass_libvirt_service }}"' in handlers
    assert "state: restarted" in handlers

    print("looking glass cgroup contract: OK")


if __name__ == "__main__":
    main()
