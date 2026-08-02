#!/usr/bin/env python3
"""Host-independent M7/M8 service registration and recovery contracts."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
SERVICE_PLAN = ROOT / "tools/service_plan.py"
RECEIPT_GUARD = ROOT / "tools/service_receipt_guard.py"
NETWORK_GUARD = ROOT / "tools/service_network_guard.py"
RESERVATIONS = ROOT / "tools/service_reservations.py"
MEMORY = ROOT / "tools/guest_memory.py"
RECOVERY_PLAN = ROOT / "tools/service_recovery_plan.py"
BACKUP_GUARD = ROOT / "tools/service_backup_guard.py"


def run(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=stdin, text=True, capture_output=True, check=False)


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def fixture(root: Path) -> None:
    shutil.copytree(ROOT / "service-specs", root / "service-specs")
    shutil.copytree(ROOT / "vm-specs", root / "vm-specs")
    (root / "group_vars/all").mkdir(parents=True)
    for name in ("services.yml", "networks.yml"):
        shutil.copy2(ROOT / "group_vars/all" / name, root / "group_vars/all" / name)


def plan(root: Path, store: Path) -> subprocess.CompletedProcess[str]:
    return run(
        sys.executable,
        str(SERVICE_PLAN),
        "--root",
        str(root),
        "--spec",
        str(root / "service-specs/svc-jellyfin.yml"),
        "--store",
        str(store),
    )


def receipt_for(service_plan: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "id",
        "vm",
        "spec_sha256",
        "vm_spec_sha256",
        "network_profile",
        "memory_reservation_mb",
        "dhcp",
        "exposures",
        "backup_policy",
        "restore_policy",
        "disk_path",
    )
    receipt = {key: service_plan[key] for key in keys}
    receipt.update(schema_version=1, registered=True)
    return receipt


def test_service_plan_and_refusals() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        store = Path(td) / "store"
        fixture(root)
        result = plan(root, store)
        assert result.returncode == 0, result.stderr
        data = json.loads(result.stdout)
        assert data["id"] == "svc-jellyfin"
        assert data["dhcp"] == {"mac": "52:54:00:66:29:6e", "ip": "10.10.5.10"}
        assert data["memory_reservation_mb"] == 4096
        assert data["exposures"] == ["tcp/8096"]

        vm_path = root / "vm-specs/svc-jellyfin.yml"
        vm = yaml.safe_load(vm_path.read_text())
        vm["resources"]["memory_mb"] = 2048
        write_yaml(vm_path, vm)
        refused = plan(root, store)
        assert refused.returncode == 2 and "reservation must equal" in refused.stderr

        lease_root = Path(td) / "lease"
        fixture(lease_root)
        services_path = lease_root / "group_vars/all/services.yml"
        services = yaml.safe_load(services_path.read_text())
        services["service_dhcp_leases"][0]["ip"] = "10.10.5.100"
        write_yaml(services_path, services)
        spec_path = lease_root / "service-specs/svc-jellyfin.yml"
        spec = yaml.safe_load(spec_path.read_text())
        spec["dhcp"]["ip"] = "10.10.5.100"
        write_yaml(spec_path, spec)
        refused = plan(lease_root, store)
        assert refused.returncode == 2 and "dynamic DHCP range" in refused.stderr

        exposure_root = Path(td) / "exposure"
        fixture(exposure_root)
        spec_path = exposure_root / "service-specs/svc-jellyfin.yml"
        spec = yaml.safe_load(spec_path.read_text())
        spec["exposures"] = ["tcp/8920"]
        write_yaml(spec_path, spec)
        refused = plan(exposure_root, store)
        assert refused.returncode == 2 and "not reviewed" in refused.stderr


def test_receipt_and_network_guards() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        store = Path(td) / "store"
        fixture(root)
        service_plan = json.loads(plan(root, store).stdout)
        receipt = Path(service_plan["receipt_path"])
        write_yaml(receipt, receipt_for(service_plan))
        result = run(
            sys.executable,
            str(RECEIPT_GUARD),
            "--receipt",
            str(receipt),
            stdin=json.dumps(service_plan),
        )
        assert result.returncode == 0, result.stderr
        changed = receipt_for(service_plan)
        changed["exposures"] = []
        write_yaml(receipt, changed)
        refused = run(
            sys.executable,
            str(RECEIPT_GUARD),
            "--receipt",
            str(receipt),
            stdin=json.dumps(service_plan),
        )
        assert refused.returncode == 2 and "exposures" in refused.stderr

        xml = """<network><name>services</name><ip><dhcp>
        <host name='svc-jellyfin' mac='52:54:00:66:29:6e' ip='10.10.5.10'/>
        </dhcp></ip></network>"""
        ok = run(
            sys.executable,
            str(NETWORK_GUARD),
            "--name", "svc-jellyfin",
            "--mac", "52:54:00:66:29:6e",
            "--ip", "10.10.5.10",
            stdin=xml,
        )
        assert ok.returncode == 0, ok.stderr
        collision = xml.replace(
            "</dhcp>",
            "<host name='other' mac='52:54:00:aa:bb:cc' ip='10.10.5.10'/></dhcp>",
        )
        refused = run(
            sys.executable,
            str(NETWORK_GUARD),
            "--name", "svc-jellyfin",
            "--mac", "52:54:00:66:29:6e",
            "--ip", "10.10.5.10",
            stdin=collision,
        )
        assert refused.returncode == 2 and "assigned to another" in refused.stderr


def test_inactive_service_memory_reservations() -> None:
    with tempfile.TemporaryDirectory() as td:
        receipts = Path(td) / "receipts"
        write_yaml(receipts / "svc-jellyfin.yml", {
            "schema_version": 1,
            "id": "svc-jellyfin",
            "vm": "svc-jellyfin",
            "memory_reservation_mb": 4096,
            "registered": True,
        })
        idle = run(
            sys.executable,
            str(RESERVATIONS),
            "--receipt-root", str(receipts),
        )
        assert json.loads(idle.stdout)["reserved_mb"] == 4096
        active = run(
            sys.executable,
            str(RESERVATIONS),
            "--receipt-root", str(receipts),
            stdin="Domain: 'svc-jellyfin'\n  balloon.maximum=4194304\n",
        )
        assert json.loads(active.stdout)["reserved_mb"] == 0
        sentinel = "# hyperlab-domstats-eof\n"
        empty_live_set = run(
            sys.executable,
            str(RESERVATIONS),
            "--receipt-root", str(receipts),
            stdin=sentinel,
        )
        assert empty_live_set.returncode == 0, empty_live_set.stderr
        assert json.loads(empty_live_set.stdout)["reserved_mb"] == 4096
        candidate = run(
            sys.executable,
            str(RESERVATIONS),
            "--receipt-root", str(receipts),
            "--candidate-name", "svc-jellyfin",
        )
        assert json.loads(candidate.stdout)["reserved_mb"] == 0

        profile = {
            "host_reserved_mb": 2048,
            "qemu_overhead_per_domain_mb": 512,
            "services_reserved_mb": 0,
            "vfio_fixed_overhead_mb": 256,
            "max_auto_memory_mb": 8192,
            "standard_overcommit_ratio": 1.0,
        }
        budget = run(
            sys.executable,
            str(MEMORY),
            "--profile-json", json.dumps(profile),
            "--memtotal-mb", "16384",
            "--request", "4096",
            "--floor-mb", "2048",
            "--overcommit", "false",
            "--device-profile", "standard",
            "--service-reservations-json", idle.stdout.strip(),
            "--candidate-name", "debian-dev",
            stdin=sentinel,
        )
        assert budget.returncode == 0, budget.stderr
        evidence = json.loads(budget.stdout)
        assert evidence["dynamic_services_reserved_mb"] == 4096
        assert evidence["base_pool_mb"] == 9728

        memory_tasks = (ROOT / "roles/guest/tasks/memory.yml").read_text(encoding="utf-8")
        assert memory_tasks.count("# hyperlab-domstats-eof") == 2
        memory_play = yaml.safe_load(memory_tasks)
        read_only_tasks = {
            task["name"]: task
            for task in memory_play
            if task["name"] in {
                "Read live libvirt memory commitments",
                "Resolve inactive registered service reservations",
                "Resolve the candidate memory from the live budget",
            }
        }
        assert len(read_only_tasks) == 3
        assert all(task.get("check_mode") is False for task in read_only_tasks.values())


def fake_qemu_img(root: Path) -> Path:
    script = root / "qemu-img"
    script.write_text(
        """#!/usr/bin/env python3
import json
import sys
if sys.argv[1] == 'info':
    print(json.dumps({'format': 'qcow2', 'virtual-size': 68719476736}))
    raise SystemExit(0)
if sys.argv[1] == 'check':
    raise SystemExit(0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def test_recovery_plan_and_backup_guard() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        store = Path(td) / "store"
        fixture(root)
        service_plan = json.loads(plan(root, store).stdout)
        recovery = run(
            sys.executable,
            str(RECOVERY_PLAN),
            "--operation", "backup",
            "--backup-id", "20260728T050000Z",
            stdin=json.dumps(service_plan),
        )
        assert recovery.returncode == 0, recovery.stderr
        recovery_plan = json.loads(recovery.stdout)
        assert recovery_plan["confirmation"] == "svc-jellyfin:20260728T050000Z"
        invalid = run(
            sys.executable,
            str(RECOVERY_PLAN),
            "--operation", "backup",
            "--backup-id", "../escape",
            stdin=json.dumps(service_plan),
        )
        assert invalid.returncode == 2

        backup_dir = Path(recovery_plan["backup_dir"])
        disk = backup_dir / "disk.qcow2"
        disk.parent.mkdir(parents=True)
        disk.write_bytes(b"independent backup fixture")
        context = dict(service_plan)
        context.update(recovery_plan)
        context["service_receipt_sha256"] = hashlib.sha256(b"service receipt").hexdigest()
        receipt = {
            "schema_version": 1,
            "service_id": service_plan["id"],
            "vm": service_plan["vm"],
            "backup_id": recovery_plan["backup_id"],
            "service_spec_sha256": service_plan["spec_sha256"],
            "service_vm_spec_sha256": service_plan["vm_spec_sha256"],
            "service_receipt_sha256": context["service_receipt_sha256"],
            "source_disk_path": service_plan["disk_path"],
            "disk_sha256": hashlib.sha256(disk.read_bytes()).hexdigest(),
            "virtual_size_bytes": 68719476736,
            "qemu_img_check": "pass",
        }
        write_yaml(backup_dir / "receipt.yml", receipt)
        qemu_img = fake_qemu_img(Path(td))
        verified = run(
            sys.executable,
            str(BACKUP_GUARD),
            "--receipt", str(backup_dir / "receipt.yml"),
            "--disk", str(disk),
            "--qemu-img", str(qemu_img),
            stdin=json.dumps(context),
        )
        assert verified.returncode == 0, verified.stderr
        receipt["disk_sha256"] = "0" * 64
        write_yaml(backup_dir / "receipt.yml", receipt)
        refused = run(
            sys.executable,
            str(BACKUP_GUARD),
            "--receipt", str(backup_dir / "receipt.yml"),
            "--disk", str(disk),
            "--qemu-img", str(qemu_img),
            stdin=json.dumps(context),
        )
        assert refused.returncode == 2 and "disk_sha256" in refused.stderr


def test_ansible_order_and_network_contracts() -> None:
    register = (ROOT / "roles/service_registry/tasks/register.yml").read_text()
    backup = (ROOT / "roles/service_registry/tasks/backup.yml").read_text()
    restore = (ROOT / "roles/service_registry/tasks/restore.yml").read_text()
    main = (ROOT / "roles/service_registry/tasks/main.yml").read_text()
    network_template = (ROOT / "roles/network_domains/templates/net.xml.j2").read_text()
    comparator = (ROOT / "roles/network_domains/files/network_xml_equivalent.py").read_text()
    bricks = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text())
    assert register.index("Verify the staged service registration receipt") < register.index(
        "Commit the service registration receipt atomically"
    )
    rescue = register.split("rescue:", 1)[1]
    assert "receipt_new_path" in rescue and "receipt_path }}\"\n            state: absent" not in rescue
    assert backup.index("Verify the complete staged service backup") < backup.index(
        "Commit the verified backup directory atomically"
    )
    assert restore.index("Check the committed restored service disk") < restore.index(
        "Remove rollback only after committed restore validation"
    )
    assert "service_dhcp_leases" in network_template and "<host" in network_template
    assert "dhcp_hosts" in comparator and "service_registry" in main
    assert bricks["brick_requires"]["service_registry"] == ["image_store", "network_domains"]


def main() -> int:
    tests = [value for name, value in sorted(globals().items()) if name.startswith("test_") and callable(value)]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"service contract: OK ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
