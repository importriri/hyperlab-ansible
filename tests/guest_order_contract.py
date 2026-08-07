#!/usr/bin/env python3
"""Protect guest refusal, store, VFIO, network and lock ordering."""
from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
TASKS = ROOT / "roles/guest/tasks"


def main() -> int:
    main_text = (TASKS / "main.yml").read_text(encoding="utf-8")

    plan = main_text.index("- name: Build the deterministic guest plan without side effects")
    publish = main_text.index("- name: Publish the deterministic guest plan")
    store_guard = main_text.index(
        "- name: Verify managed store paths before inspecting guest-owned artefacts"
    )
    inspect = main_text.index("- name: Inspect existing guest-owned state")
    network = main_text.index(
        "- name: Refuse a missing or inactive selected network before VM operations"
    )
    transaction_preflight = main_text.index(
        "- name: Refuse create or reset on an unsafe transaction shape before host writes"
    )
    reset_preflight = main_text.index(
        "- name: Refuse an unsafe reset request before host writes"
    )
    vfio = main_text.index(
        "- name: Rebuild the live VFIO contract for hardware-sensitive operations"
    )
    verify_base = main_text.index(
        "- name: Verify the sealed base before any operation that depends on it"
    )
    packages = main_text.index(
        "- name: Install lifecycle dependencies after every read-only gate"
    )
    roots = main_text.index(
        "- name: Create guest management roots before acquiring the first VM lock"
    )
    post_roots = main_text.index("- name: Verify the reconciled guest management roots")
    per_vm = main_text.index("- name: Acquire the per-VM operation lock")
    registry = main_text.index("- name: Acquire the global guest registry lock")
    libvirt_registry = main_text.index(
        "- name: Check UUID, MAC and host-device ownership across libvirt"
    )
    dispatch_create = main_text.index("- name: Dispatch guest creation")
    dispatch_resize = main_text.index("- name: Dispatch managed disk expansion")
    dispatch_destroy = main_text.index("- name: Dispatch guest destruction")
    release_registry = main_text.index(
        "- name: Release the global guest registry lock owned by this operation"
    )
    release_per_vm = main_text.index("- name: Release the per-VM operation lock")

    assert plan < publish < store_guard < inspect < network < transaction_preflight
    assert transaction_preflight < reset_preflight < vfio < verify_base
    assert verify_base < packages < roots < post_roots < per_vm
    assert per_vm < registry < libvirt_registry < dispatch_create
    assert dispatch_create < dispatch_resize < dispatch_destroy
    assert dispatch_destroy < release_registry < release_per_vm

    assert "ansible.builtin.package:" not in main_text[:verify_base]
    verify_block = main_text[verify_base:packages]
    assert "guest_operation == 'create' and guest_transaction_clean" in verify_block
    assert "guest_plan.lifecycle == 'disposable'" in verify_block
    assert (
        "guest_operation in ['create', 'reset', 'start', 'validate', 'resize']"
        in verify_block
    )
    assert "guest_confirm_reset == guest_plan.name" in main_text[reset_preflight:vfio]
    assert "guest_network_defined" in main_text[network:transaction_preflight]
    assert "guest_network_active" in main_text[network:transaction_preflight]
    assert "vfio.yml" in main_text[vfio:verify_base]
    assert "guest_registry_lock_acquire.rc == 0" in main_text[registry:release_per_vm]
    assert "libvirt-registry.yml" in main_text[registry:dispatch_create]
    assert "guest_store_guard_tool" in main_text[store_guard:inspect]
    assert "--require-management-roots" in main_text[store_guard:inspect]

    inspect_text = (TASKS / "inspect.yml").read_text(encoding="utf-8")
    required = inspect_text.index("guest_required_artifact_flags")
    transient = inspect_text.index("guest_transient_artifact_flags")
    unexpected = inspect_text.index("guest_unexpected_artifact_flags")
    classify = inspect_text.index("- name: Classify the managed guest transaction")
    required_block = inspect_text[required:transient]
    unexpected_block = inspect_text[unexpected:classify]
    assert "guest_nvram_stat.stat.exists" not in required_block
    assert "guest_nvram_stat.stat.exists" in unexpected_block
    assert "if not guest_plan.requires_uefi else []" in unexpected_block
    assert "and not guest_nvram_stat.stat.exists" in inspect_text[classify:]

    libvirt_text = (TASKS / "libvirt-registry.yml").read_text(encoding="utf-8")
    assert "domname" in libvirt_text
    assert "domiflist" in libvirt_text
    assert "--persistent" in libvirt_text
    assert "guest_libvirt_active_domain_names" in libvirt_text
    assert "guest_libvirt_persistent_domain_names" in libvirt_text
    assert "guest_libvirt_live_interfaces" in libvirt_text
    assert "guest_libvirt_persistent_interfaces" in libvirt_text
    assert libvirt_text.count("item.item == guest_plan.name") == 2
    assert "vfio-registry.yml" in libvirt_text

    vfio_text = (TASKS / "vfio.yml").read_text(encoding="utf-8")
    assert vfio_text.index(
        "Build the host-local VFIO plan without side effects"
    ) < vfio_text.index("Inspect the kvmfr character device")
    assert vfio_text.index(
        "Inspect the kvmfr character device"
    ) < vfio_text.index(
        "Read the loaded kvmfr shared-memory size through its ioctl"
    )
    assert "guest_kvmfr_size_tool" in vfio_text
    assert "/sys/module/kvmfr/parameters/static_size_mb" not in vfio_text
    assert "vfio-pci" in vfio_text
    assert "iommu_group" in vfio_text

    start_text = (TASKS / "start.yml").read_text(encoding="utf-8")
    gpu_lock = start_text.index("- name: Acquire the global GPU start lock")
    capacity_lock = start_text.index("- name: Acquire the global start-capacity lock")
    registry_check = start_text.index(
        "- name: Recheck exclusive PCI and SPICE ownership under the GPU lock"
    )
    virsh_start = start_text.index("- name: Start the managed domain")
    release_capacity = start_text.index("- name: Release the global start-capacity lock")
    release_gpu = start_text.index("- name: Release the global GPU start lock")
    assert gpu_lock < capacity_lock < registry_check < virsh_start
    assert virsh_start < release_capacity < release_gpu

    create_text = (TASKS / "create.yml").read_text(encoding="utf-8")
    freeze = create_text.index("- name: Freeze ownership of a new guest transaction")
    create = create_text.index("- name: Create a new standard guest transaction")
    define = create_text.index("- name: Define the persistent libvirt domain")
    refresh = create_text.index("- name: Refresh committed artifact observations")
    read_state = create_text.index("- name: Read the new managed state")
    verify = create_text.index(
        "- name: Verify the complete transaction before returning success"
    )
    rescue = create_text.index(
        "- name: Undefine a domain created by the failed transaction"
    )
    assert freeze < create < define < refresh < read_state < verify < rescue
    assert 'guest_create_new_transaction: "{{ guest_transaction_clean }}"' in create_text
    assert "when: guest_create_new_transaction" in create_text[create:define]
    assert "register: guest_domain_define" in create_text[define:rescue]
    assert "guest_domain_define is defined" in create_text[rescue:]
    assert "guest_domain_define.rc | default(1) == 0" in create_text[rescue:]

    validate_text = (TASKS / "validate.yml").read_text(encoding="utf-8")
    assert "Create the transient guest validation parent" not in validate_text
    assert 'path: "{{ guest_tmp_root }}"' in validate_text
    assert 'prefix: "privatestack-guest.{{ guest_plan.name }}."' in validate_text
    validate_tasks = yaml.safe_load(validate_text)
    disk_chain_read = next(
        task
        for task in validate_tasks
        if task.get("name")
        == "Inspect the managed qcow2 chain while the domain is shut off"
    )
    assert disk_chain_read.get("check_mode") is False
    assert disk_chain_read.get("changed_when") is False

    task_names = [task.get("name") for task in validate_tasks]
    memory_binding_name = "Bind the committed memory allocation to domain validation"
    render_name = "Verify the managed domain contract in a transient directory"
    assert memory_binding_name in task_names
    assert task_names.index(memory_binding_name) < task_names.index(render_name)
    memory_binding = validate_tasks[task_names.index(memory_binding_name)]
    assert memory_binding["ansible.builtin.set_fact"]["guest_resolved_memory_mb"] == (
        "{{ guest_existing_state.memory_mb | int }}"
    )

    xml_validation = validate_tasks[task_names.index(render_name)]["block"]
    xml_task_names = [task.get("name") for task in xml_validation]
    strict_xml = xml_task_names.index("Compare only the domain fields owned by the guest brick")
    legacy_xml = xml_task_names.index("Recognize only the pre-DAC-pin managed domain contract")
    refuse_xml = xml_task_names.index("Refuse domain drift or an unsafe DAC migration context")
    commit_xml = xml_task_names.index("Commit the DAC-pinned managed XML")
    redefine_xml = xml_task_names.index("Redefine only the exact shut-off legacy domain")
    verify_xml = xml_task_names.index("Verify the migrated domain against the strict contract")
    assert strict_xml < legacy_xml < refuse_xml < commit_xml < redefine_xml < verify_xml
    legacy_task = xml_validation[legacy_xml]
    assert "--allow-legacy-missing-dac-relabel" in legacy_task["ansible.builtin.command"]["argv"]
    refusal = xml_validation[refuse_xml]["ansible.builtin.assert"]
    refusal_text = " ".join(str(item) for item in refusal["that"])
    assert "guest_operation == 'create'" in refusal_text
    assert "guest_domain_state == 'shut off'" in refusal_text

    resize_text = (TASKS / "resize.yml").read_text(encoding="utf-8")
    pending_commit = resize_text.index(
        "- name: Commit the pending resize marker before touching qcow2"
    )
    qcow2_resize = resize_text.index(
        "- name: Expand the qcow2 only when it still has the committed old size"
    )
    expanded_verify = resize_text.index(
        "- name: Verify the expanded virtual size and lifecycle chain"
    )
    state_commit = resize_text.index(
        "- name: Atomically commit the new managed disk size"
    )
    final_validation = resize_text.index(
        "- name: Validate the complete resized transaction"
    )

    assert pending_commit < qcow2_resize < expanded_verify
    assert expanded_verify < state_commit < final_validation
    assert "guest_domain_state == 'shut off'" in resize_text
    assert "guest_confirm_resize == guest_plan.name" in resize_text
    assert "resize_pending" in resize_text
    assert "guest_resize_needs_qcow2_growth | bool" in resize_text
    assert "'backing-filename-format'" in resize_text

    defaults = yaml.safe_load(
        (ROOT / "roles/guest/defaults/main.yml").read_text(encoding="utf-8")
    )
    assert "resize" in defaults["guest_supported_operations"]
    key_pattern = re.compile(defaults["guest_ssh_public_key_pattern"])
    assert key_pattern.fullmatch("ssh-ed25519 AAAA workstation")
    assert key_pattern.fullmatch("sk-ssh-ed25519@openssh.com AAAA token")
    assert key_pattern.fullmatch("sk-ecdsa-sha2-nistp256@openssh.com AAAA token")
    assert not key_pattern.fullmatch("-----BEGIN OPENSSH PRIVATE KEY-----")
    assert not key_pattern.fullmatch("ssh-ed25519 AAAA\nsecond-line")

    print("guest order contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
