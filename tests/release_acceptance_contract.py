#!/usr/bin/env python3
"""Host-independent M9 campaign runner and sanitized-evidence contracts."""
from __future__ import annotations

import copy
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
MANIFEST = ROOT / "release/acceptance.v2.yml"
TOOL = ROOT / "tools/release_acceptance.py"
ANSIBLE_SHA = "a" * 40
BOOTSTRAP_SHA = "b" * 40
CAMPAIGN = "nitro-final-20260728"


def run(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        input=stdin,
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PYTHONNOUSERSITE": "1"},
    )


def plan(
    profile: str = "nitro-3060",
    ansible_sha: str = ANSIBLE_SHA,
    bootstrap_sha: str = BOOTSTRAP_SHA,
) -> dict[str, Any]:
    result = run(
        sys.executable,
        str(TOOL),
        "--manifest",
        str(MANIFEST),
        "plan",
        "--profile",
        profile,
        "--campaign-id",
        CAMPAIGN,
        "--ansible-sha",
        ansible_sha,
        "--bootstrap-sha",
        bootstrap_sha,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def scalar_for(field: str) -> Any:
    if field.endswith("sha256"):
        return hashlib.sha256(field.encode()).hexdigest()
    if field in {
        "clean_worktrees",
        "no_writes_observed",
        "booted_linux_hardened_twice",
        "network_ready",
        "nocow",
        "hyperlab_device_match",
        "second_apply_changed_zero",
        "exclusive_owner",
        "reboot_resets_trust",
        "loopback_spice",
        "guest_health",
        "lan_http_health",
        "tcp_8096_only",
        "stopped_vm_closes_exposure",
        "post_restore_health",
        "failed_restore_rollback",
        "no_sensitive_patterns",
    }:
        return True
    if field == "topology":
        return "dedicated-disk"
    if field == "mapper":
        return "/dev/mapper/cryptvm"
    if field == "fsroot":
        return "/"
    if field == "fstype":
        return "btrfs"
    return f"verified-{field.replace('_', '-')}"


def evidence_for(release_plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "campaign_id": release_plan["campaign_id"],
        "profile": release_plan["profile"],
        "repositories": {
            key: value["expected_sha"]
            for key, value in release_plan["repositories"].items()
        },
        "storage": {
            "topology": "dedicated-disk",
            "mapper": "/dev/mapper/cryptvm",
            "fsroot": "/",
            "subvolume": None,
            "mountpoint": "/var/lib/libvirt/images",
            "fstype": "btrfs",
            "nocow": True,
        },
        "gates": [
            {
                "id": gate["id"],
                "status": "pass",
                "summary": f"Reviewed pass for {gate['id']}",
                "evidence": {
                    field: scalar_for(field)
                    for field in gate["required_evidence"]
                },
            }
            for gate in release_plan["gates"]
        ],
        "sanitized": True,
    }


def write_plan(path: Path, release_plan: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(release_plan, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def seal(
    release_plan: dict[str, Any],
    evidence: dict[str, Any],
) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "plan.json"
        write_plan(path, release_plan)
        return run(
            sys.executable,
            str(TOOL),
            "--manifest",
            str(MANIFEST),
            "seal",
            "--plan",
            str(path),
            stdin=json.dumps(evidence),
        )


def scaffold_files(
    directory: Path,
    release_plan: dict[str, Any],
) -> tuple[Path, Path]:
    plan_path = directory / "plan.json"
    evidence_path = directory / "evidence.json"
    write_plan(plan_path, release_plan)
    result = run(
        sys.executable,
        str(TOOL),
        "--manifest",
        str(MANIFEST),
        "scaffold",
        "--plan",
        str(plan_path),
        "--output",
        str(evidence_path),
    )
    assert result.returncode == 0, result.stderr
    return plan_path, evidence_path


def record(
    plan_path: Path,
    evidence_path: Path,
    gate: dict[str, Any],
    *,
    status: str = "pass",
    payload: dict[str, Any] | None = None,
) -> subprocess.CompletedProcess[str]:
    values = payload or {
        field: scalar_for(field) for field in gate["required_evidence"]
    }
    return run(
        sys.executable,
        str(TOOL),
        "--manifest",
        str(MANIFEST),
        "record",
        "--plan",
        str(plan_path),
        "--evidence",
        str(evidence_path),
        "--gate",
        gate["id"],
        "--status",
        status,
        "--summary",
        f"Reviewed {status} for {gate['id']}",
        stdin=json.dumps(values),
    )


def init_fake_repo(
    path: Path,
    branch: str,
    remote: str,
    verify_text: str = "verification pass",
) -> str:
    path.mkdir()
    subprocess.run(["git", "init", "-q", "-b", branch], cwd=path, check=True)
    subprocess.run(
        ["git", "config", "user.name", "M9 Contract"],
        cwd=path,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "m9-contract@example.invalid"],
        cwd=path,
        check=True,
    )
    (path / "verify.sh").write_text(
        f"#!/usr/bin/env bash\nset -eu\nprintf '%s\\n' '{verify_text}'\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "verify.sh"], cwd=path, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "fixture"],
        cwd=path,
        check=True,
    )
    subprocess.run(
        ["git", "remote", "add", "origin", remote],
        cwd=path,
        check=True,
    )
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=path,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()


def test_plan_is_deterministic_and_orders_nitro_before_predator() -> None:
    first = plan()
    assert first == plan()
    assert first["profile_order"] == 1
    assert plan("predator-3070")["profile_order"] == 2
    orders = [gate["order"] for gate in first["gates"]]
    assert orders == sorted(orders)
    assert len(orders) == len(set(orders))
    assert (
        first["repositories"]["hyperlab_ansible"]["expected_sha"]
        == ANSIBLE_SHA
    )
    assert (
        first["repositories"]["arch_bootstrap"]["expected_sha"]
        == BOOTSTRAP_SHA
    )
    assert first["allowed_storage_topologies"]["dedicated-disk"] == {
        "mapper": "/dev/mapper/cryptvm",
        "fsroot": "/",
        "subvolume": None,
    }


def test_invalid_profile_commit_and_campaign_are_refused() -> None:
    cases = [
        (
            [
                "--profile",
                "unknown",
                "--campaign-id",
                CAMPAIGN,
                "--ansible-sha",
                ANSIBLE_SHA,
                "--bootstrap-sha",
                BOOTSTRAP_SHA,
            ],
            "unknown acceptance profile",
        ),
        (
            [
                "--profile",
                "nitro-3060",
                "--campaign-id",
                CAMPAIGN,
                "--ansible-sha",
                "main",
                "--bootstrap-sha",
                BOOTSTRAP_SHA,
            ],
            "40 lowercase hex",
        ),
        (
            [
                "--profile",
                "nitro-3060",
                "--campaign-id",
                "Bad ID",
                "--ansible-sha",
                ANSIBLE_SHA,
                "--bootstrap-sha",
                BOOTSTRAP_SHA,
            ],
            "campaign id",
        ),
    ]
    for arguments, message in cases:
        result = run(
            sys.executable,
            str(TOOL),
            "--manifest",
            str(MANIFEST),
            "plan",
            *arguments,
        )
        assert result.returncode == 2
        assert message in result.stderr


def test_scaffold_and_record_enforce_gate_order() -> None:
    release_plan = plan()
    with tempfile.TemporaryDirectory() as td:
        plan_path, evidence_path = scaffold_files(Path(td), release_plan)
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert evidence["storage"] is None
        assert evidence["gates"][0]["status"] == "pending"
        assert evidence_path.stat().st_mode & 0o777 == 0o600

        skipped = record(plan_path, evidence_path, release_plan["gates"][1])
        assert skipped.returncode == 2
        assert "cannot be recorded before repository-software passes" in skipped.stderr

        first = record(plan_path, evidence_path, release_plan["gates"][0])
        assert first.returncode == 0, first.stderr
        status = json.loads(first.stdout)
        assert status["next_gate"] == "bootstrap-dry-run"
        assert status["passed"] == 1


def test_storage_record_derives_the_top_level_contract() -> None:
    release_plan = plan()
    with tempfile.TemporaryDirectory() as td:
        plan_path, evidence_path = scaffold_files(Path(td), release_plan)
        for gate in release_plan["gates"][:4]:
            result = record(plan_path, evidence_path, gate)
            assert result.returncode == 0, result.stderr
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert evidence["storage"] == {
            "topology": "dedicated-disk",
            "mapper": "/dev/mapper/cryptvm",
            "fsroot": "/",
            "subvolume": None,
            "mountpoint": "/var/lib/libvirt/images",
            "fstype": "btrfs",
            "nocow": True,
        }


def test_repository_proof_binds_clean_exact_checkouts_and_hashes_logs() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        ansible = root / "ansible"
        bootstrap = root / "bootstrap"
        ansible_sha = init_fake_repo(
            ansible,
            "main",
            "https://github.com/importriri/hyperlab-ansible.git",
            "ansible verification pass",
        )
        bootstrap_sha = init_fake_repo(
            bootstrap,
            "main",
            "git@github.com:importriri/arch-bootstrap.git",
            "bootstrap verification pass",
        )
        release_plan = plan(
            ansible_sha=ansible_sha,
            bootstrap_sha=bootstrap_sha,
        )
        plan_path = root / "plan.json"
        write_plan(plan_path, release_plan)
        logs = root / "logs"
        proof = run(
            sys.executable,
            str(TOOL),
            "--manifest",
            str(MANIFEST),
            "repository-proof",
            "--plan",
            str(plan_path),
            "--ansible-repo",
            str(ansible),
            "--bootstrap-repo",
            str(bootstrap),
            "--log-dir",
            str(logs),
        )
        assert proof.returncode == 0, proof.stderr
        payload = json.loads(proof.stdout)
        assert len(payload["verify_sha256"]) == 64
        assert payload["clean_worktrees"] is True
        assert ansible_sha in payload["exact_commits"]
        assert bootstrap_sha in payload["exact_commits"]
        assert (
            (logs / "hyperlab_ansible.verify.log").stat().st_mode & 0o777
            == 0o600
        )
        assert (
            (logs / "arch_bootstrap.verify.log").stat().st_mode & 0o777
            == 0o600
        )

        (ansible / "dirty.txt").write_text("drift", encoding="utf-8")
        dirty = run(
            sys.executable,
            str(TOOL),
            "--manifest",
            str(MANIFEST),
            "repository-proof",
            "--plan",
            str(plan_path),
            "--ansible-repo",
            str(ansible),
            "--bootstrap-repo",
            str(bootstrap),
        )
        assert dirty.returncode == 2
        assert "worktree is not clean" in dirty.stderr


def test_complete_sanitized_evidence_seals_to_stable_hashes() -> None:
    release_plan = plan()
    evidence = evidence_for(release_plan)
    first = seal(release_plan, evidence)
    second = seal(release_plan, evidence)
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout) == json.loads(second.stdout)
    receipt = json.loads(first.stdout)
    assert receipt["result"] == "pass"
    assert receipt["gate_count"] == len(release_plan["gates"])
    assert receipt["storage_topology"] == "dedicated-disk"
    assert len(receipt["plan_sha256"]) == 64
    assert len(receipt["evidence_sha256"]) == 64


def test_tampered_plan_is_refused_before_evidence_is_read() -> None:
    release_plan = plan()
    release_plan["repositories"]["arch_bootstrap"]["required_branch"] = (
        "review/old-release-line"
    )
    result = seal(release_plan, evidence_for(plan()))
    assert result.returncode == 2
    assert "canonical manifest projection" in result.stderr


def test_gate_failures_missing_fields_and_commit_drift_are_refused() -> None:
    release_plan = plan()
    baseline = evidence_for(release_plan)
    mutations: list[tuple[dict[str, Any], str]] = []

    failed = copy.deepcopy(baseline)
    failed["gates"][3]["status"] = "fail"
    mutations.append((failed, "later gate cannot pass"))

    missing = copy.deepcopy(baseline)
    missing["gates"][0]["evidence"].pop("verify_sha256")
    mutations.append((missing, "fields differ"))

    drift = copy.deepcopy(baseline)
    drift["repositories"]["arch_bootstrap"] = "c" * 40
    mutations.append((drift, "commits differ"))

    wrong_mapper = copy.deepcopy(baseline)
    wrong_mapper["storage"]["mapper"] = "/dev/mapper/cryptroot"
    mutations.append((wrong_mapper, "storage mapper differs"))

    for evidence, message in mutations:
        result = seal(release_plan, evidence)
        assert result.returncode == 2
        assert message in result.stderr


def test_sensitive_patterns_and_raw_nested_evidence_are_refused() -> None:
    release_plan = plan()
    baseline = evidence_for(release_plan)

    secret = copy.deepcopy(baseline)
    secret["gates"][0]["summary"] = "password=do-not-publish"
    assert "forbidden sensitive pattern" in seal(release_plan, secret).stderr

    home = copy.deepcopy(baseline)
    home["gates"][0]["summary"] = "log copied from /home/sid/private"
    assert "forbidden sensitive pattern" in seal(release_plan, home).stderr

    nested = copy.deepcopy(baseline)
    nested["gates"][0]["evidence"]["clean_worktrees"] = {"raw": "log"}
    result = seal(release_plan, nested)
    assert result.returncode == 2
    assert "must be one scalar" in result.stderr


def test_manifest_covers_every_required_final_boundary() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    gate_ids = [gate["id"] for gate in manifest["gates"]]
    assert gate_ids == [
        "repository-software",
        "bootstrap-dry-run",
        "bootstrap-clean-install",
        "storage-handoff",
        "host-idempotence",
        "network-isolation",
        "standard-vm-lifecycle",
        "vfio-trust-lifecycle",
        "looking-glass",
        "jellyfin-service",
        "service-recovery",
        "sanitized-publication",
    ]
    assert (
        manifest["profiles"]["nitro-3060"]["order"]
        < manifest["profiles"]["predator-3070"]["order"]
    )
    assert (
        manifest["repositories"]["arch_bootstrap"]["required_branch"]
        == "main"
    )
    assert (
        manifest["repositories"]["hyperlab_ansible"]["required_branch"]
        == "main"
    )


def main() -> int:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        test()
        print(f"ok: {test.__name__}")
    print(f"release acceptance contract: OK ({len(tests)} tests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
