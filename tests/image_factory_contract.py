#!/usr/bin/env python3
"""Host-independent contracts for M5 acquisition, receipts and guest provenance."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
IMAGE_PLAN = ROOT / "tools/image_plan.py"
IMAGE_INSPECT = ROOT / "tools/image_inspect.py"
RECEIPT_GUARD = ROOT / "tools/image_receipt_guard.py"
LG_BUILD = "B7-263-g0140a3f6fb"
GIB = 1024 * 1024 * 1024


def run(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=stdin, text=True, capture_output=True, check=False)


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fake_qemu_img(root: Path) -> Path:
    script = root / "qemu-img"
    script.write_text(
        """#!/usr/bin/env python3
import json
import pathlib
import sys

command = sys.argv[1]
path = pathlib.Path(sys.argv[-1])
if command == "info":
    size = 128 if "win11" in path.name else 20
    payload = {"format": "qcow2", "virtual-size": size * 1024 * 1024 * 1024}
    if "backed" in path.name:
        payload["backing-filename"] = "/unsafe/base.qcow2"
    if "wrong-size" in path.name:
        payload["virtual-size"] = 1
    print(json.dumps(payload))
    raise SystemExit(0)
if command == "check":
    raise SystemExit(1 if "broken" in path.name else 0)
raise SystemExit(2)
""",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return script


def base_manifest(image_id: str, *, windows: bool) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": image_id,
        "display_name": image_id,
        "os_family": "windows" if windows else "linux",
        "os_variant": "win11" if windows else "debian12",
        "version": "fixture",
        "format": "qcow2",
        "status": "not-built",
        "sha256": None,
        "private": windows,
        "contains_personal_data": windows,
        "generalized": not windows,
        "instance_policy": "singleton" if windows else "multiple",
        "source_type": "local" if windows else "official-cloud",
        "source_url": None,
        "source_checksum_url": None,
        "filename": f"{image_id}.qcow2",
        "virtual_size_gib": 128 if windows else 20,
        "minimum_size_gib": 80 if windows else 8,
        "min_memory_mb": 6144 if windows else 2048,
        "supports": {
            "standard": True,
            "vfio": windows,
            "cloud_init": not windows,
            "qemu_guest_agent": True,
        },
        "requires": {"uefi": True, "secure_boot": windows, "tpm2": windows},
        "defaults": {
            "lifecycle": "permanent",
            "device_profile": "vfio" if windows else "standard",
            "network_profile": "clean" if windows else "dev",
        },
        "network_allowlist": ["clean"] if windows else ["dev", "lab"],
        "licensing": {"redistributable": not windows},
        "looking_glass_host_build_required": LG_BUILD if windows else None,
        "looking_glass_host_build_observed": None,
    }


def image_plan(
    root: Path,
    manifest: Path,
    store: Path,
    operation: str,
    *,
    source_url: str = "",
    source_sha256: str = "",
    local_source: str = "",
    observed_build: str = "",
) -> subprocess.CompletedProcess[str]:
    return run(
        sys.executable,
        str(IMAGE_PLAN),
        "--root",
        str(root),
        "--manifest",
        str(manifest),
        "--store",
        str(store),
        "--operation",
        operation,
        "--source-url",
        source_url,
        "--source-sha256",
        source_sha256,
        "--local-source",
        local_source,
        "--looking-glass-observed-build",
        observed_build,
    )


def receipt_for(plan: dict[str, Any], artifact_sha: str, source_basename: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "id": plan["id"],
        "policy_sha256": plan["policy_sha256"],
        "base_path": plan["base_path"],
        "artifact_sha256": artifact_sha,
        "format": plan["format"],
        "virtual_size_bytes": plan["virtual_size_gib"] * GIB,
        "source_type": plan["source_type"],
        "source_url": None if plan["private"] else plan["source_url"],
        "source_basename": source_basename,
        "source_sha256": plan["source_sha256"],
        "private": plan["private"],
        "looking_glass_host_build_required": plan["looking_glass_host_build_required"],
        "looking_glass_host_build_observed": plan["looking_glass_host_build_observed"],
        "qemu_img_check": "pass",
    }


def test_official_cloud_policy_stability() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "images").mkdir()
        store = root / "store"
        manifest_path = root / "images/debian.yml"
        manifest = base_manifest("debian", windows=False)
        write_yaml(manifest_path, manifest)
        source = root / "debian.qcow2"
        source.write_bytes(b"official fixture")
        source_hash = sha256(source)
        url = "https://downloads.example.invalid/debian.qcow2"

        prepared = image_plan(
            root,
            manifest_path,
            store,
            "prepare",
            source_url=url,
            source_sha256=source_hash,
        )
        assert prepared.returncode == 0, prepared.stderr
        plan = json.loads(prepared.stdout)
        assert plan["source_url"] == url
        assert plan["source_basename"] == "debian.qcow2"
        assert plan["local_source"] is None

        manifest["status"] = "sealed"
        manifest["sha256"] = source_hash
        manifest["source_url"] = url
        manifest["source_sha256"] = source_hash
        write_yaml(manifest_path, manifest)
        validated = image_plan(root, manifest_path, store, "validate")
        assert validated.returncode == 0, validated.stderr
        sealed_plan = json.loads(validated.stdout)
        assert sealed_plan["policy_sha256"] == plan["policy_sha256"]

        insecure = image_plan(
            root,
            manifest_path,
            store,
            "prepare",
            source_url="http://downloads.example.invalid/debian.qcow2",
            source_sha256=source_hash,
        )
        assert insecure.returncode == 2 and "HTTPS" in insecure.stderr


def test_private_local_policy_and_receipt() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "images").mkdir()
        store = root / "store"
        manifest_path = root / "images/win11clean.yml"
        manifest = base_manifest("win11clean", windows=True)
        write_yaml(manifest_path, manifest)
        source = root / "private-workshop-output.qcow2"
        source.write_bytes(b"private Windows fixture")
        source_hash = sha256(source)
        qemu_img = fake_qemu_img(root)

        prepared = image_plan(
            root,
            manifest_path,
            store,
            "prepare",
            source_sha256=source_hash,
            local_source=str(source),
            observed_build=LG_BUILD,
        )
        assert prepared.returncode == 0, prepared.stderr
        plan = json.loads(prepared.stdout)
        assert plan["private"] is True
        assert plan["local_source"] == str(source)

        base = Path(plan["base_path"])
        base.parent.mkdir(parents=True)
        base.write_bytes(source.read_bytes())
        receipt_path = Path(plan["receipt_path"])
        write_yaml(receipt_path, receipt_for(plan, source_hash, source.name))

        prepared_guard = run(
            sys.executable,
            str(RECEIPT_GUARD),
            "--receipt",
            str(receipt_path),
            "--base",
            str(base),
            "--qemu-img",
            str(qemu_img),
            "--mode",
            "prepared",
            stdin=json.dumps(plan),
        )
        assert prepared_guard.returncode == 0, prepared_guard.stderr

        manifest["status"] = "sealed"
        manifest["sha256"] = source_hash
        manifest["source_sha256"] = source_hash
        manifest["looking_glass_host_build_observed"] = LG_BUILD
        write_yaml(manifest_path, manifest)
        validated = image_plan(root, manifest_path, store, "validate")
        assert validated.returncode == 0, validated.stderr
        sealed_plan = json.loads(validated.stdout)
        assert sealed_plan["policy_sha256"] == plan["policy_sha256"]
        assert sealed_plan["local_source"] is None

        sealed_guard = run(
            sys.executable,
            str(RECEIPT_GUARD),
            "--receipt",
            str(receipt_path),
            "--base",
            str(base),
            "--qemu-img",
            str(qemu_img),
            "--mode",
            "sealed",
            stdin=json.dumps(sealed_plan),
        )
        assert sealed_guard.returncode == 0, sealed_guard.stderr

        leaked = receipt_for(plan, source_hash, source.name)
        leaked["local_source"] = str(source)
        write_yaml(receipt_path, leaked)
        refused = run(
            sys.executable,
            str(RECEIPT_GUARD),
            "--receipt",
            str(receipt_path),
            "--base",
            str(base),
            "--qemu-img",
            str(qemu_img),
            "--mode",
            "prepared",
            stdin=json.dumps(plan),
        )
        assert refused.returncode == 2 and "host-local source path" in refused.stderr


def test_plan_refusals() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        (root / "images").mkdir()
        store = root / "store"
        source = root / "candidate.qcow2"
        source.write_bytes(b"fixture")
        source_hash = sha256(source)
        manifest_path = root / "images/win11clean.yml"
        manifest = base_manifest("win11clean", windows=True)
        write_yaml(manifest_path, manifest)

        missing_build = image_plan(
            root,
            manifest_path,
            store,
            "prepare",
            source_sha256=source_hash,
            local_source=str(source),
        )
        assert missing_build.returncode == 2 and "host-build evidence" in missing_build.stderr

        inside_store = store / "candidate.qcow2"
        inside_store.parent.mkdir(parents=True)
        inside_store.write_bytes(b"fixture")
        refused = image_plan(
            root,
            manifest_path,
            store,
            "prepare",
            source_sha256=sha256(inside_store),
            local_source=str(inside_store),
            observed_build=LG_BUILD,
        )
        assert refused.returncode == 2 and "outside the managed image store" in refused.stderr

        validate_with_path = image_plan(
            root,
            manifest_path,
            store,
            "validate",
            source_sha256=source_hash,
            local_source=str(source),
            observed_build=LG_BUILD,
        )
        assert validate_with_path.returncode == 2 and "must not depend" in validate_with_path.stderr

        manifest["source_type"] = "official-iso"
        write_yaml(manifest_path, manifest)
        refused = image_plan(
            root,
            manifest_path,
            store,
            "prepare",
            source_sha256=source_hash,
            local_source=str(source),
            observed_build=LG_BUILD,
        )
        assert refused.returncode == 2 and "workshop input" in refused.stderr

        outside_manifest = root / "outside.yml"
        write_yaml(outside_manifest, manifest)
        refused = image_plan(
            root,
            outside_manifest,
            store,
            "prepare",
            source_sha256=source_hash,
            local_source=str(source),
            observed_build=LG_BUILD,
        )
        assert refused.returncode == 2 and "below images" in refused.stderr


def test_qcow2_inspection() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        qemu_img = fake_qemu_img(root)
        good = root / "debian.qcow2"
        good.write_bytes(b"fixture")
        result = run(
            sys.executable,
            str(IMAGE_INSPECT),
            "--path",
            str(good),
            "--qemu-img",
            str(qemu_img),
            "--expected-format",
            "qcow2",
            "--expected-size-gib",
            "20",
        )
        assert result.returncode == 0, result.stderr
        evidence = json.loads(result.stdout)
        assert evidence["sha256"] == sha256(good)
        assert evidence["qemu_img_check"] == "pass"

        backed = root / "backed.qcow2"
        backed.write_bytes(b"fixture")
        refused = run(
            sys.executable,
            str(IMAGE_INSPECT),
            "--path",
            str(backed),
            "--qemu-img",
            str(qemu_img),
            "--expected-format",
            "qcow2",
            "--expected-size-gib",
            "20",
        )
        assert refused.returncode == 2 and "backing file" in refused.stderr

        symlink = root / "redirect.qcow2"
        symlink.symlink_to(good)
        refused = run(
            sys.executable,
            str(IMAGE_INSPECT),
            "--path",
            str(symlink),
            "--qemu-img",
            str(qemu_img),
            "--expected-format",
            "qcow2",
            "--expected-size-gib",
            "20",
        )
        assert refused.returncode == 2 and "non-symlink" in refused.stderr


def test_role_structure() -> None:
    role = ROOT / "roles/image_factory"
    main = (role / "tasks/main.yml").read_text(encoding="utf-8")
    prepare = (role / "tasks/prepare.yml").read_text(encoding="utf-8")
    validate = (role / "tasks/validate.yml").read_text(encoding="utf-8")
    receipt = (role / "templates/receipt.yml.j2").read_text(encoding="utf-8")
    guest_main = (ROOT / "roles/guest/tasks/main.yml").read_text(encoding="utf-8")
    guest_base = (ROOT / "roles/guest/tasks/verify-base.yml").read_text(encoding="utf-8")
    bricks = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text(encoding="utf-8"))

    parrot = yaml.safe_load((ROOT / "images/parrot.yml").read_text(encoding="utf-8"))

    assert main.index("Build the deterministic image factory plan without side effects") < main.index(
        "Inspect committed and transient image transaction paths"
    )
    assert main.index("Refuse a partial image transaction") < main.index("Prepare the selected image transaction")
    assert "--operation" in main
    assert "checksum: \"sha256:{{ image_factory_plan.source_sha256 }}\"" in prepare
    assert "remote_src: true" in prepare
    assert "Validate an already-prepared image instead of replacing it" in prepare
    assert prepare.index("Acquire the per-image factory lock") < prepare.index("Download the pinned official cloud image")
    assert "image_factory_plan.base_path" in prepare
    assert "failed new image transaction" in prepare
    assert "local_source" not in receipt
    assert "source_sha256" in receipt
    assert parrot["source_type"] == "local"
    assert parrot["source_url"] is None
    assert "ISO itself is never" in parrot["notes"]
    assert "image_factory_plan.manifest_status" in validate
    assert "source_sha256={{ image_factory_plan.source_sha256 }}" in validate

    assert bricks["brick_requires"]["image_factory"] == ["image_store"]
    assert bricks["brick_requires"]["guest"] == ["image_factory", "network_domains"]
    assert "Verify the sealed base before any operation that depends on it" in guest_main
    assert guest_main.index("Verify the sealed base before any operation that depends on it") < guest_main.index(
        "Install lifecycle dependencies after every read-only gate"
    )
    assert "guest_image_receipt_guard_tool" in guest_base
    assert "--mode\n      - sealed" in guest_base
    assert guest_base.index("Rebuild the immutable image provenance plan") < guest_base.index(
        "Refuse a mutable, misplaced or changed sealed base"
    )

    guest_base_tasks = yaml.safe_load(guest_base)
    read_only_commands = {
        task["name"]: task
        for task in guest_base_tasks
        if "ansible.builtin.command" in task
    }
    for task_name in (
        "Rebuild the immutable image provenance plan",
        "Verify the Windows workshop receipt before guest operations",
        "Resolve the sealed base path as the kernel would",
        "Verify the committed base against its M5 provenance receipt",
        "Inspect sealed qcow2 metadata independently",
    ):
        assert read_only_commands[task_name]["check_mode"] is False


def main() -> int:
    tests = [
        test_official_cloud_policy_stability,
        test_private_local_policy_and_receipt,
        test_plan_refusals,
        test_qcow2_inspection,
        test_role_structure,
    ]
    for test in tests:
        test()
    print("image factory contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
