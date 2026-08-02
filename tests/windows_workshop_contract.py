#!/usr/bin/env python3
"""Host-independent contracts for the M6 Windows workshop chain."""
from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools/windows_workshop.py"
GUARD = ROOT / "tools/windows_workshop_guard.py"
LG_BUILD = "B7-263-g0140a3f6fb"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, text=True, capture_output=True, check=False)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def evidence(image: str) -> dict[str, Any]:
    clean = image == "win11clean"
    return {
        "schema_version": 1,
        "image": image,
        "collected_at_utc": "2026-07-27T22:00:00.0000000Z",
        "collector": {"version": 1, "powershell": "5.1"},
        "windows": {"product": "Windows 11", "version": "10.0", "build": "26100"},
        "identity": {
            "mode": "personal-singleton" if clean else "generalized-local-template",
            "generalized": not clean,
            "microsoft_account_present": clean,
            "local_lab_account_present": not clean,
            "credential_reuse": False,
            "sysprep_generalization_state": 7 if not clean else 3,
            "setup_image_state": (
                "IMAGE_STATE_COMPLETE"
                if clean
                else "IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE"
            ),
        },
        "firmware": {
            "secure_boot": True,
            "tpm2_present": True,
            "tpm2_ready": True,
            "tpm_spec_version": "2.0",
        },
        "drivers": {
            "nvidia_gpu": True,
            "emulated_gpu_recovery": True,
            "virtio_input": True,
            "ivshmem": True,
        },
        "services": {
            "qemu_guest_agent": "running",
            "looking_glass_host": "running",
        },
        "looking_glass": {
            "build": LG_BUILD,
            "capture_started": True,
            "capture_interface": "D12",
            "log_basename": "looking-glass-host.log",
        },
        "virtual_display": {
            "present": True,
            "active": True,
            "width": 1920,
            "height": 1080,
        },
        "hygiene": {"reboot_pending": False, "update_reboot_pending": False},
    }


def validate(image: str, source: Path, evidence_path: Path, store: Path) -> subprocess.CompletedProcess[str]:
    return run(
        sys.executable,
        str(VALIDATOR),
        "--root",
        str(ROOT),
        "--policy",
        str(ROOT / f"windows-workshops/{image}.yml"),
        "--evidence",
        str(evidence_path),
        "--manifest",
        str(ROOT / f"images/{image}.yml"),
        "--source",
        str(source),
        "--source-sha256",
        sha256(source),
        "--looking-glass-build",
        LG_BUILD,
        "--store",
        str(store),
    )


def test_clean_and_dirty_receipts() -> None:
    for image in ("win11clean", "win11dirty"):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            source = temp / f"{image}.qcow2"
            source.write_bytes(f"{image} workshop fixture".encode())
            evidence_path = temp / f"{image}.json"
            write_json(evidence_path, evidence(image))
            store = temp / "store"
            result = validate(image, source, evidence_path, store)
            assert result.returncode == 0, result.stderr
            receipt = json.loads(result.stdout)
            assert receipt["id"] == image
            assert receipt["source_sha256"] == sha256(source)
            assert receipt["looking_glass_build"] == LG_BUILD
            assert receipt["capture_interface"] == "D12"
            assert receipt["private"] is True and receipt["ready"] is True
            receipt_path = temp / f"{image}.yml"
            write_yaml(receipt_path, receipt)
            guarded = run(
                sys.executable,
                str(GUARD),
                "--policy",
                str(ROOT / f"windows-workshops/{image}.yml"),
                "--receipt",
                str(receipt_path),
                "--image",
                image,
                "--source-sha256",
                sha256(source),
                "--looking-glass-build",
                LG_BUILD,
            )
            assert guarded.returncode == 0, guarded.stderr
            guard_result = json.loads(guarded.stdout)
            assert guard_result["receipt_sha256"] == sha256(receipt_path)


def test_privacy_and_identity_mutations() -> None:
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        source = temp / "win11clean.qcow2"
        source.write_bytes(b"clean")
        store = temp / "store"
        base = evidence("win11clean")

        leaked = copy.deepcopy(base)
        leaked["windows"]["owner"] = "sid@example.com"
        evidence_path = temp / "leaked.json"
        write_json(evidence_path, leaked)
        refused = validate("win11clean", source, evidence_path, store)
        assert refused.returncode == 2 and "email address" in refused.stderr

        wrong_identity = copy.deepcopy(base)
        wrong_identity["identity"]["microsoft_account_present"] = False
        write_json(evidence_path, wrong_identity)
        refused = validate("win11clean", source, evidence_path, store)
        assert refused.returncode == 2 and "Microsoft-account" in refused.stderr

        reused = copy.deepcopy(base)
        reused["identity"]["credential_reuse"] = True
        write_json(evidence_path, reused)
        refused = validate("win11clean", source, evidence_path, store)
        assert refused.returncode == 2 and "no credential" in refused.stderr

        dirty = evidence("win11dirty")
        dirty["identity"]["microsoft_account_present"] = True
        write_json(evidence_path, dirty)
        refused = validate("win11dirty", source, evidence_path, store)
        assert refused.returncode == 2 and "forbids Microsoft accounts" in refused.stderr

        dirty = evidence("win11dirty")
        dirty["identity"]["setup_image_state"] = "IMAGE_STATE_COMPLETE"
        write_json(evidence_path, dirty)
        refused = validate("win11dirty", source, evidence_path, store)
        assert refused.returncode == 2 and "Setup state differs" in refused.stderr


def test_capture_hygiene_and_checksum_mutations() -> None:
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        source = temp / "win11dirty.qcow2"
        source.write_bytes(b"dirty")
        evidence_path = temp / "dirty.json"
        store = temp / "store"
        data = evidence("win11dirty")

        data["looking_glass"]["capture_interface"] = "DXGI"
        write_json(evidence_path, data)
        refused = validate("win11dirty", source, evidence_path, store)
        assert refused.returncode == 2 and "D12" in refused.stderr

        data = evidence("win11dirty")
        data["hygiene"]["reboot_pending"] = True
        write_json(evidence_path, data)
        refused = validate("win11dirty", source, evidence_path, store)
        assert refused.returncode == 2 and "reboot_pending" in refused.stderr

        write_json(evidence_path, evidence("win11dirty"))
        wrong_hash = run(
            sys.executable,
            str(VALIDATOR),
            "--root",
            str(ROOT),
            "--policy",
            str(ROOT / "windows-workshops/win11dirty.yml"),
            "--evidence",
            str(evidence_path),
            "--manifest",
            str(ROOT / "images/win11dirty.yml"),
            "--source",
            str(source),
            "--source-sha256",
            "0" * 64,
            "--looking-glass-build",
            LG_BUILD,
            "--store",
            str(store),
        )
        assert wrong_hash.returncode == 2 and "differs" in wrong_hash.stderr


def test_stale_receipt_guard() -> None:
    with tempfile.TemporaryDirectory() as td:
        temp = Path(td)
        source = temp / "win11clean.qcow2"
        source.write_bytes(b"clean")
        evidence_path = temp / "clean.json"
        write_json(evidence_path, evidence("win11clean"))
        result = validate("win11clean", source, evidence_path, temp / "store")
        assert result.returncode == 0, result.stderr
        receipt = json.loads(result.stdout)
        receipt_path = temp / "receipt.yml"
        write_yaml(receipt_path, receipt)
        stale_policy = yaml.safe_load((ROOT / "windows-workshops/win11clean.yml").read_text())
        stale_policy["virtual_display"]["width"] = 2560
        stale_policy_path = temp / "stale.yml"
        write_yaml(stale_policy_path, stale_policy)
        refused = run(
            sys.executable,
            str(GUARD),
            "--policy",
            str(stale_policy_path),
            "--receipt",
            str(receipt_path),
            "--image",
            "win11clean",
            "--source-sha256",
            sha256(source),
            "--looking-glass-build",
            LG_BUILD,
        )
        assert refused.returncode == 2 and "policy hash is stale" in refused.stderr


def test_repository_structure() -> None:
    clean_policy = yaml.safe_load((ROOT / "windows-workshops/win11clean.yml").read_text())
    dirty_policy = yaml.safe_load((ROOT / "windows-workshops/win11dirty.yml").read_text())
    collector = (ROOT / "windows/collect-hyperlab-evidence.ps1").read_text(encoding="utf-8")
    validator = VALIDATOR.read_text(encoding="utf-8")
    legacy_validator = (ROOT / "tools/windows_workshop_legacy.py").read_text(encoding="utf-8")
    role = (ROOT / "roles/windows_workshop/tasks/main.yml").read_text(encoding="utf-8")
    factory = (ROOT / "roles/image_factory/tasks/main.yml").read_text(encoding="utf-8")
    guest = (ROOT / "roles/guest/tasks/verify-base.yml").read_text(encoding="utf-8")
    receipt_template = (ROOT / "roles/windows_workshop/templates/receipt.yml.j2").read_text(encoding="utf-8")
    image_receipt = (ROOT / "roles/image_factory/templates/receipt.yml.j2").read_text(encoding="utf-8")
    bricks = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text())
    dirty_manifest = yaml.safe_load((ROOT / "images/win11dirty.yml").read_text())

    for policy in (clean_policy, dirty_policy):
        assert policy["drivers"]["emulated_gpu_recovery"] is True
        assert policy["setup_image_state"] in {
            "IMAGE_STATE_COMPLETE",
            "IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE",
        }
        assert policy["looking_glass"]["capture_interface"] == "D12"
        assert policy["virtual_display"] == {
            "present": True,
            "active": True,
            "width": 1920,
            "height": 1080,
        }
    assert "emulated_gpu_recovery" in collector
    assert "emulated_gpu_recovery" in validator
    assert "virtio_gpu_recovery" not in collector
    assert "virtio_gpu_recovery" not in validator
    assert "Get-LocalUser" not in collector
    assert "ConvertTo-Json" in collector
    assert "IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE" in collector
    assert "setup_image_state" in legacy_validator
    assert "setup_image_state" in receipt_template
    assert "C:\\Users\\" not in receipt_template
    assert "local_source" not in receipt_template
    assert dirty_manifest["private"] is True

    assert bricks["brick_requires"]["windows_workshop"] == ["image_store", "looking_glass"]
    assert role.index("Acquire the per-workshop receipt lock") < role.index(
        "Reinspect receipt paths after lock acquisition"
    )
    assert role.index("Reinspect receipt paths after lock acquisition") < role.index(
        "Render the private-safe workshop receipt to staging"
    )
    assert "Remove a failed newly-owned committed workshop receipt" not in role
    assert factory.index("Verify the Windows workshop receipt before image operations") < factory.index(
        "Inspect committed and transient image transaction paths"
    )
    assert guest.index("Verify the Windows workshop receipt before guest operations") < guest.index(
        "Verify the committed base against its M5 provenance receipt"
    )
    assert "windows_workshop_policy_sha256" in image_receipt
    assert "windows_workshop_receipt_sha256" in image_receipt


def main() -> int:
    for test in (
        test_clean_and_dirty_receipts,
        test_privacy_and_identity_mutations,
        test_capture_hygiene_and_checksum_mutations,
        test_stale_receipt_guard,
        test_repository_structure,
    ):
        test()
    print("Windows workshop contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
