#!/usr/bin/env python3
"""Static contract for the measured transactional host Gaming Mode."""

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/host_gaming_mode"


def text(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def load(relative: str):
    return yaml.safe_load(text(relative))


def main() -> None:
    defaults = load("roles/host_gaming_mode/defaults/main.yml")
    tasks = text("roles/host_gaming_mode/tasks/main.yml")
    template = text(
        "roles/host_gaming_mode/templates/host-gaming-mode.json.j2"
    )
    client = text(
        "roles/host_gaming_mode/files/hyperlab-gaming-mode.py"
    )
    root_helper = text(
        "roles/host_gaming_mode/files/hyperlab-gaming-mode-root.py"
    )
    graph = load("group_vars/all/bricks.yml")
    play = load("playbooks/host-gaming-mode.yml")[0]
    contract = text("docs/performance-security-contract.md")
    catalog = text("docs/brick-catalog.md")
    playbooks = text("docs/playbooks.md")

    assert defaults["host_gaming_mode_expected_host_profile"] == "nitro-3060"
    assert defaults["host_gaming_mode_epp"] == "performance"
    assert defaults["host_gaming_mode_allowed_cpus"] == "0,1,4,5"
    assert defaults["host_gaming_mode_system_effective_cpus"] == "0-1,4-5"
    assert defaults["host_gaming_mode_user_effective_cpus"] == "0-1,4-5"
    assert defaults["host_gaming_mode_machine_effective_cpus"] == "0-7"
    assert defaults["host_gaming_mode_expected_epp_cpu_count"] == 8
    assert defaults["host_gaming_mode_vcpu_pins"] == {
        "0": "2",
        "1": "6",
        "2": "3",
        "3": "7",
    }
    assert defaults["host_gaming_mode_emulator_pin"] == "0,4"
    assert defaults["host_gaming_mode_iothread_pin"] == "1,5"

    assert "'hypervisor' in group_names" in tasks
    assert "'workstations' not in group_names" in tasks
    assert "host_gaming_mode_profile_report_data.host_profile" in tasks
    assert "hyperlab-gaming-mode-root.py" in tasks
    assert "hyperlab-gaming-mode.py" in tasks
    assert "brick_guard_brick: host_gaming_mode" in tasks
    assert tasks.count("when: not ansible_check_mode") >= 3

    assert '"epp": {{ host_gaming_mode_epp | to_json }}' in template
    assert '"allowed_cpus":' in template
    assert '"vcpu_pins":' in template
    assert '"emulator_pin":' in template
    assert '"iothread_pin":' in template

    for token in (
        "energy_performance_preference",
        "AllowedCPUs=",
        "system.slice",
        "user.slice",
        "machine.slice",
        "qemu:///system",
        "virsh",
        "SUDO_UID",
        "fcntl.flock",
        "signal.SIGTERM",
        "sys.stdin.buffer.read()",
        "restore_state",
        "stale-recovery",
        "allow_unsafe_interrupts",
        "randomize_va_space",
    ):
        assert token in root_helper, token

    for forbidden in (
        "shell=True",
        "os.system(",
        "mitigations=off",
        "allow_unsafe_interrupts=1",
        "vfio_iommu_type1.allow_unsafe_interrupts=1",
    ):
        assert forbidden not in root_helper, forbidden

    assert '["sudo", "-v"]' in client
    assert '["sudo", "-n", ROOT_HELPER, "guard"]' in client
    assert '"runtime-only"' in client
    assert "run_workload" in client
    assert "recover" in client
    assert "status" in client
    assert "shell=True" not in client
    assert "os.system(" not in client

    assert graph["brick_requires"]["host_gaming_mode"] == [
        "hardware_probe",
        "kvm_host",
    ]
    assert (
        graph["brick_playbooks"]["host_gaming_mode"]
        == "playbooks/host-gaming-mode.yml"
    )

    assert play["hosts"] == "hypervisor"
    assert play["become"] is True
    assert play["roles"][0] == {
        "role": "brick_guard",
        "vars": {"brick_guard_brick": "host_gaming_mode"},
    }
    assert play["roles"][1] == "host_gaming_mode"

    assert "measured combined policy" in contract
    assert "runtime-only" in contract
    assert "3.164%" in contract
    assert "`host_gaming_mode`" in catalog
    assert "`host-gaming-mode.yml`" in playbooks
    assert "hyperlab-gaming-mode run --" in playbooks

    print("host gaming mode contract: OK")


if __name__ == "__main__":
    main()
