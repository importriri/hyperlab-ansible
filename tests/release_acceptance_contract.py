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
sys.path.insert(0, str(ROOT / "tools"))
import release_acceptance  # noqa: E402

MANIFESTS = {version: ROOT / f"release/acceptance.v{version}.yml" for version in (2, 3)}
ADR = ROOT / "docs/adr/0063-v1-acceptance-campaign.md"
TOOL = ROOT / "tools/release_acceptance.py"
ANSIBLE_SHA = "a" * 40
BOOTSTRAP_SHA = "b" * 40
CAMPAIGN = "nitro-final-20260728"

# Every evidence field of the manifest, classified by hand, gate by gate.
# Booleans are observations a pass must prove true; hashes bind local files;
# descriptive fields are reviewed text such as secure_boot_state or
# destroy_confirmation. Written out here rather than read from the tool, so
# a field dropped from its typing cannot also drop out of these tests.
REVIEWED_EVIDENCE: dict[str, dict[str, tuple[str, ...]]] = {
    "repository-software": {
        "booleans": ("clean_worktrees",),
        "hashes": ("verify_sha256",),
        "descriptive": ("exact_commits",),
    },
    "bootstrap-dry-run": {
        "booleans": ("no_writes_observed",),
        "hashes": ("dry_run_sha256",),
        "descriptive": ("selected_primary_disk", "selected_vm_disk"),
    },
    "bootstrap-clean-install": {
        "booleans": ("booted_linux_hardened_twice", "network_ready"),
        "hashes": ("install_log_sha256",),
        "descriptive": ("secure_boot_state",),
    },
    "storage-handoff": {
        "booleans": ("nocow", "hyperlab_device_match"),
        "hashes": ("contract_sha256",),
        "descriptive": ("topology", "mapper", "fsroot", "fstype"),
    },
    "host-idempotence": {
        "booleans": ("second_apply_changed_zero",),
        "hashes": (
            "check_mode_sha256",
            "first_apply_sha256",
            "second_apply_sha256",
        ),
        "descriptive": (),
    },
    "network-isolation": {
        "booleans": (),
        "hashes": (),
        "descriptive": (
            "persistent_network_hashes",
            "active_networks",
            "cross_domain_refusals",
            "isolated_lab_refusals",
        ),
    },
    "standard-vm-lifecycle": {
        "booleans": (),
        "hashes": (
            "create_sha256",
            "validate_sha256",
            "start_sha256",
            "shutdown_sha256",
        ),
        "descriptive": ("destroy_confirmation",),
    },
    "vfio-trust-lifecycle": {
        "booleans": ("exclusive_owner", "reboot_resets_trust"),
        "hashes": (),
        "descriptive": ("pci_binding", "iommu_group", "downward_trust_transitions"),
    },
    "looking-glass": {
        "booleans": ("spice_socket_private",),
        "hashes": ("visual_proof_sha256",),
        "descriptive": (
            "host_build",
            "guest_build",
            "kvmfr_identity",
            "spice_socket_path",
        ),
    },
    "jellyfin-service": {
        "booleans": (
            "guest_health",
            "lan_http_health",
            "tcp_8096_only",
            "stopped_vm_closes_exposure",
        ),
        "hashes": ("service_receipt_sha256",),
        "descriptive": (),
    },
    "service-recovery": {
        "booleans": ("post_restore_health", "failed_restore_rollback"),
        "hashes": ("backup_receipt_sha256", "restored_disk_sha256"),
        "descriptive": (),
    },
    "sanitized-publication": {
        "booleans": ("no_sensitive_patterns",),
        "hashes": ("publication_bundle_sha256",),
        "descriptive": ("exact_commit_matrix", "known_limits"),
    },
}
REVIEWED_V3_EVIDENCE: dict[str, dict[str, tuple[str, ...]]] = {
    "repository-software": {
        "booleans": ("clean_worktrees",),
        "hashes": ("verify_sha256",),
        "descriptive": ("exact_commits",),
    },
    "bootstrap-dry-run": {
        "booleans": ("no_writes_observed",),
        "hashes": ("dry_run_sha256",),
        "descriptive": (
            "selected_primary_disk",
            "selected_vm_disk",
        ),
    },
    "bootstrap-clean-install": {
        "booleans": (
            "booted_linux_hardened_twice",
            "network_ready",
        ),
        "hashes": ("install_log_sha256",),
        "descriptive": ("secure_boot_state",),
    },
    "storage-handoff": {
        "booleans": (
            "nocow",
            "hyperlab_device_match",
        ),
        "hashes": ("contract_sha256",),
        "descriptive": (
            "topology",
            "mapper",
            "fsroot",
            "fstype",
        ),
    },
    "host-idempotence": {
        "booleans": ("second_apply_changed_zero",),
        "hashes": (
            "check_mode_sha256",
            "first_apply_sha256",
            "second_apply_sha256",
        ),
        "descriptive": (),
    },
    "network-isolation": {
        "booleans": (
            "cross_domain_refused",
            "isolated_lab_refused",
            "dns_control_reached",
            "dev_resolver_refused",
            "host_llmnr_refused",
        ),
        "hashes": (),
        "descriptive": (
            "persistent_network_hashes",
            "active_networks",
            "cross_domain_refusals",
            "isolated_lab_refusals",
        ),
    },
    "standard-vm-lifecycle": {
        "booleans": (),
        "hashes": (
            "create_sha256",
            "validate_sha256",
            "start_sha256",
            "shutdown_sha256",
        ),
        "descriptive": ("destroy_confirmation",),
    },
    "vfio-clean-baseline": {
        "booleans": (
            "clean_gpu_observed",
            "clean_stopped_before_dev",
        ),
        "hashes": ("clean_start_sha256",),
        "descriptive": (
            "pci_binding",
            "iommu_group",
        ),
    },
    "server-ssh": {
        "booleans": (
            "debian_strict_ssh",
            "fedora_strict_ssh",
            "debian_agent_restricted",
            "fedora_agent_restricted",
        ),
        "hashes": (
            "debian_ssh_sha256",
            "fedora_ssh_sha256",
        ),
        "descriptive": (),
    },
    "shell-creation": {
        "booleans": (
            "server_permanent_created_from_shell",
            "workstation_permanent_created_from_shell",
            "server_durable_operation",
            "workstation_durable_operation",
            "operation_survives_window_close",
            "secrets_confined_to_terminal",
            "duplicate_creation_refused",
            "refused_creation_leaves_no_record",
            "withdraw_live_domain_refused",
        ),
        "hashes": ("creation_log_sha256",),
        "descriptive": (),
    },
    "disposable-lifecycle": {
        "booleans": (
            "normal_stop_writes_discarded",
            "normal_stop_overlay_removed",
            "normal_boot_agent_restricted",
            "normal_boot_pin_refreshed",
            "normal_boot_strict_ssh",
            "forced_stop_writes_discarded",
            "forced_stop_overlay_removed",
            "forced_boot_agent_restricted",
            "forced_boot_pin_refreshed",
            "forced_boot_strict_ssh",
            "power_cycle_writes_discarded",
            "power_cycle_overlay_removed",
            "power_cycle_agent_restricted",
            "power_cycle_pin_refreshed",
            "power_cycle_strict_ssh",
            "sealed_base_unchanged",
        ),
        "hashes": ("disposable_log_sha256",),
        "descriptive": (),
    },
    "looking-glass": {
        "booleans": ("spice_socket_private",),
        "hashes": ("visual_proof_sha256",),
        "descriptive": (
            "host_build",
            "guest_build",
            "kvmfr_identity",
            "spice_socket_path",
        ),
    },
    "workstation-access": {
        "booleans": (
            "primary_prelogin_recovery",
            "primary_handoff_to_looking_glass",
            "keyboard_captured",
            "pointer_captured",
            "rightctrl_releases_both",
            "super_isolated",
            "guest_shortcuts_work",
            "guest_lock_unlock",
            "client_reconnect_preserves_session",
            "logout_returns_to_login",
            "host_frame_windowed",
            "host_frame_fullscreen",
        ),
        "hashes": ("input_log_sha256",),
        "descriptive": (),
    },
    "physical-audio": {
        "booleans": (
            "guest_audio_audible",
            "no_clipping",
            "host_volume_capped",
            "no_guest_microphone",
        ),
        "hashes": ("audio_log_sha256",),
        "descriptive": (),
    },
    "gpu-lease": {
        "booleans": (
            "default_boot_without_gpu",
            "first_gpu_run",
            "gpu_less_run",
            "second_gpu_run",
            "lease_runs_same_host_boot",
            "gpu_less_ladder_unchanged",
            "gpu_runs_looking_glass",
            "gpu_less_spice",
            "host_owned_lease",
        ),
        "hashes": ("lease_log_sha256",),
        "descriptive": ("lease_template",),
    },
    "showcase": {
        "booleans": (
            "complete_storyboard",
            "shell_creation_visible",
            "real_lease_visible",
            "looking_glass_desks_visible",
            "host_provenance_visible",
            "manual_frame_privacy_review",
            "captions_match_observations",
        ),
        "hashes": ("recording_sha256",),
        "descriptive": (),
    },
    "vfio-trust-lifecycle": {
        "booleans": (
            "exclusive_owner",
            "clean_after_dev_refused",
            "dev_after_dirty_refused",
            "upward_after_lab_refused",
            "unmapped_pci_refused",
            "reboot_resets_trust",
        ),
        "hashes": (),
        "descriptive": (
            "pci_binding",
            "iommu_group",
            "downward_trust_transitions",
        ),
    },
    "session-recovery": {
        "booleans": (
            "guest_reboot",
            "guest_agent_reconnected",
            "host_reboot",
            "cold_start",
            "encrypted_storage_ready",
            "primary_recovered",
            "input_recovered",
            "audio_recovered",
            "sway_recovery",
            "console_recovery",
            "disposable_crash_writes_discarded",
            "disposable_crash_overlay_not_reused",
            "disposable_crash_agent_restricted",
            "disposable_crash_pin_refreshed",
            "guest_profile_changed_zero",
        ),
        "hashes": ("recovery_log_sha256",),
        "descriptive": (),
    },
    "sanitized-publication": {
        "booleans": ("no_sensitive_patterns",),
        "hashes": ("publication_bundle_sha256",),
        "descriptive": (
            "exact_commit_matrix",
            "known_limits",
        ),
    },
}
REVIEWED_BY_VERSION = {2: REVIEWED_EVIDENCE, 3: REVIEWED_V3_EVIDENCE}
REVIEWED_BOOLEANS = frozenset(
    field
    for oracle in REVIEWED_BY_VERSION.values()
    for classes in oracle.values()
    for field in classes["booleans"]
)
NOT_BOOLEAN = ("true", "false", 0, 1)


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
    version: int = 2,
) -> dict[str, Any]:
    result = run(
        sys.executable,
        str(TOOL),
        "--manifest",
        str(MANIFESTS[version]),
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
    if field in REVIEWED_BOOLEANS:
        return True
    if field == "lease_template":
        return "workstation-dev-standard"
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
        "schema_version": release_plan["schema_version"],
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
            str(MANIFESTS[release_plan["schema_version"]]),
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
        str(MANIFESTS[release_plan["schema_version"]]),
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
        str(MANIFESTS[json.loads(plan_path.read_text())["schema_version"]]),
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


def status_of(
    plan_path: Path,
    evidence_path: Path,
) -> subprocess.CompletedProcess[str]:
    return run(
        sys.executable,
        str(TOOL),
        "--manifest",
        str(MANIFESTS[json.loads(plan_path.read_text())["schema_version"]]),
        "status",
        "--plan",
        str(plan_path),
        "--evidence",
        str(evidence_path),
    )


def seal_file(
    plan_path: Path,
    evidence_path: Path,
    receipt_path: Path,
) -> subprocess.CompletedProcess[str]:
    return run(
        sys.executable,
        str(TOOL),
        "--manifest",
        str(MANIFESTS[json.loads(plan_path.read_text())["schema_version"]]),
        "seal",
        "--plan",
        str(plan_path),
        "--evidence",
        str(evidence_path),
        "--output",
        str(receipt_path),
    )


def valid_payload(gate: dict[str, Any]) -> dict[str, Any]:
    return {field: scalar_for(field) for field in gate["required_evidence"]}


def failed_at(release_plan: dict[str, Any], gate_index: int) -> dict[str, Any]:
    """Evidence whose earlier gates pass, one gate fails, later ones wait."""
    evidence = evidence_for(release_plan)
    evidence["sanitized"] = False
    gate_ids = [gate["id"] for gate in release_plan["gates"]]
    if gate_index <= gate_ids.index("storage-handoff"):
        evidence["storage"] = None
    evidence["gates"][gate_index]["status"] = "fail"
    evidence["gates"][gate_index]["summary"] = "Reviewed failure"
    for later in evidence["gates"][gate_index + 1:]:
        later["status"] = "pending"
        later["summary"] = ""
        later["evidence"] = dict.fromkeys(later["evidence"])
    return evidence


def boolean_cases(
    release_plan: dict[str, Any],
) -> list[tuple[int, dict[str, Any], str]]:
    cases = [
        (index, gate, field)
        for index, gate in enumerate(release_plan["gates"])
        for field in REVIEWED_BY_VERSION[release_plan["schema_version"]][gate["id"]]["booleans"]
    ]
    assert len(cases) == sum(
        len(classes["booleans"])
        for classes in REVIEWED_BY_VERSION[release_plan["schema_version"]].values()
    )
    return cases


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


def test_plan_is_deterministic_and_orders_nitro_before_predator(version: int = 2) -> None:
    first = plan(version=version)
    assert first == plan(version=version)
    assert first["profile_order"] == 1
    assert plan("predator-3070", version=version)["profile_order"] == 2
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
    looking_glass = next(
        gate for gate in first["gates"] if gate["id"] == "looking-glass"
    )
    assert looking_glass["required_evidence"] == [
        "host_build",
        "guest_build",
        "kvmfr_identity",
        "spice_socket_path",
        "spice_socket_private",
        "visual_proof_sha256",
    ]


def test_invalid_profile_commit_and_campaign_are_refused(version: int = 2) -> None:
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
            str(MANIFESTS[version]),
            "plan",
            *arguments,
        )
        assert result.returncode == 2
        assert message in result.stderr


def test_scaffold_and_record_enforce_gate_order(version: int = 2) -> None:
    release_plan = plan(version=version)
    with tempfile.TemporaryDirectory() as td:
        plan_path, evidence_path = scaffold_files(Path(td), release_plan)
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
        assert evidence["schema_version"] == version
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


def test_storage_record_derives_the_top_level_contract(version: int = 2) -> None:
    release_plan = plan(version=version)
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


def test_repository_proof_binds_clean_exact_checkouts_and_hashes_logs(version: int = 2) -> None:
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
            version=version,
        )
        plan_path = root / "plan.json"
        write_plan(plan_path, release_plan)
        logs = root / "logs"
        proof = run(
            sys.executable,
            str(TOOL),
            "--manifest",
            str(MANIFESTS[version]),
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
            str(MANIFESTS[version]),
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


def test_complete_sanitized_evidence_seals_to_stable_hashes(version: int = 2) -> None:
    release_plan = plan(version=version)
    evidence = evidence_for(release_plan)
    first = seal(release_plan, evidence)
    second = seal(release_plan, evidence)
    assert first.returncode == 0, first.stderr
    assert json.loads(first.stdout) == json.loads(second.stdout)
    receipt = json.loads(first.stdout)
    assert receipt["schema_version"] == version
    assert receipt["result"] == "pass"
    assert receipt["gate_count"] == len(release_plan["gates"])
    assert receipt["storage_topology"] == "dedicated-disk"
    assert len(receipt["plan_sha256"]) == 64
    assert len(receipt["evidence_sha256"]) == 64


def test_tampered_plan_is_refused_before_evidence_is_read(version: int = 2) -> None:
    release_plan = plan(version=version)
    release_plan["repositories"]["arch_bootstrap"]["required_branch"] = (
        "review/old-release-line"
    )
    result = seal(release_plan, evidence_for(plan(version=version)))
    assert result.returncode == 2
    assert "canonical manifest projection" in result.stderr


def test_gate_failures_missing_fields_and_commit_drift_are_refused(version: int = 2) -> None:
    release_plan = plan(version=version)
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


def test_sensitive_patterns_and_raw_nested_evidence_are_refused(version: int = 2) -> None:
    release_plan = plan(version=version)
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


def test_manifest_covers_every_required_final_boundary(version: int = 2) -> None:
    manifest = yaml.safe_load(MANIFESTS[version].read_text(encoding="utf-8"))
    gate_ids = [gate["id"] for gate in manifest["gates"]]
    assert gate_ids == list(REVIEWED_BY_VERSION[version])
    if version == 3:
        return
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


def test_reviewed_evidence_classes_match_the_manifest_and_tool_typing(version: int = 2) -> None:
    manifest = yaml.safe_load(MANIFESTS[version].read_text(encoding="utf-8"))
    assert [gate["id"] for gate in manifest["gates"]] == list(REVIEWED_BY_VERSION[version])
    for gate in manifest["gates"]:
        classes = REVIEWED_BY_VERSION[version][gate["id"]]
        listed = [field for fields in classes.values() for field in fields]
        assert len(listed) == len(set(listed)), f"{gate['id']}: a field has two classes"
        assert set(listed) == set(gate["required_evidence"]), (
            f"{gate['id']}: reviewed classes {sorted(listed)} differ from the "
            f"manifest {sorted(gate['required_evidence'])}"
        )
        hashes = {
            field for field in gate["required_evidence"] if field.endswith("sha256")
        }
        assert hashes == set(classes["hashes"]), f"{gate['id']}: hash typing differs"
        assert not set(classes["descriptive"]) & release_acceptance.BOOL_FIELDS, (
            f"{gate['id']}: a descriptive field is typed as a boolean"
        )
    assert release_acceptance.BOOL_FIELDS == REVIEWED_BOOLEANS, (
        "tool booleans differ from the reviewed manifest booleans: "
        f"missing={sorted(REVIEWED_BOOLEANS - release_acceptance.BOOL_FIELDS)} "
        f"extra={sorted(release_acceptance.BOOL_FIELDS - REVIEWED_BOOLEANS)}"
    )
    assert "loopback_spice" not in release_acceptance.BOOL_FIELDS


def test_record_refuses_a_false_pass_and_keeps_a_false_failure(version: int = 2) -> None:
    release_plan = plan(version=version)
    cases = boolean_cases(release_plan)
    with tempfile.TemporaryDirectory() as td:
        plan_path, evidence_path = scaffold_files(Path(td), release_plan)
        for gate in release_plan["gates"]:
            for _, _, field in (case for case in cases if case[1] is gate):
                payload = valid_payload(gate)
                payload[field] = False
                before = evidence_path.read_bytes()
                refused = record(plan_path, evidence_path, gate, payload=payload)
                assert refused.returncode == 2, (
                    f"{gate['id']}.{field}=false was recorded as a pass"
                )
                assert f"gate {gate['id']} field {field} must be true" in refused.stderr, (
                    refused.stderr
                )
                assert evidence_path.read_bytes() == before, (
                    f"{gate['id']}.{field}: a refused record changed the evidence"
                )

                failed = record(
                    plan_path, evidence_path, gate, status="fail", payload=payload
                )
                assert failed.returncode == 0, (
                    f"{gate['id']}.{field}=false refused in a failed gate: "
                    f"{failed.stderr}"
                )
                report = json.loads(failed.stdout)
                assert report["failed_gates"] == [gate["id"]]
                assert report["next_gate"] == gate["id"]
                assert report["ready_to_seal"] is False, (
                    f"a campaign failed at {gate['id']} is ready to seal"
                )
                recorded = json.loads(evidence_path.read_text(encoding="utf-8"))
                assert recorded["gates"][release_plan["gates"].index(gate)][
                    "evidence"
                ][field] is False

            passed = record(plan_path, evidence_path, gate)
            assert passed.returncode == 0, passed.stderr

        final = status_of(plan_path, evidence_path)
        assert final.returncode == 0, final.stderr
        assert json.loads(final.stdout)["ready_to_seal"] is True
        first = seal_file(plan_path, evidence_path, Path(td) / "first.json")
        second = seal_file(plan_path, evidence_path, Path(td) / "second.json")
        assert first.returncode == 0, first.stderr
        assert second.returncode == 0, second.stderr
        assert (Path(td) / "first.json").read_bytes() == (
            Path(td) / "second.json"
        ).read_bytes()


def test_status_and_seal_refuse_an_edited_false_pass(version: int = 2) -> None:
    release_plan = plan(version=version)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plan_path = root / "plan.json"
        write_plan(plan_path, release_plan)
        for index, gate, field in boolean_cases(release_plan):
            evidence = evidence_for(release_plan)
            evidence["gates"][index]["evidence"][field] = False
            evidence_path = root / f"{field}.evidence.json"
            evidence_path.write_text(json.dumps(evidence), encoding="utf-8")
            before = evidence_path.read_bytes()
            message = f"gate {gate['id']} field {field} must be true"

            status = status_of(plan_path, evidence_path)
            assert status.returncode == 2, (
                f"status accepted an edited pass with {gate['id']}.{field}=false"
            )
            assert message in status.stderr, status.stderr

            receipt = root / f"{field}.receipt.json"
            sealed = seal_file(plan_path, evidence_path, receipt)
            assert sealed.returncode == 2, (
                f"seal accepted an edited pass with {gate['id']}.{field}=false"
            )
            assert message in sealed.stderr, sealed.stderr
            assert not receipt.exists(), "a refused seal wrote a receipt"
            assert evidence_path.read_bytes() == before


def test_pending_and_failed_campaigns_are_never_ready_to_seal(version: int = 2) -> None:
    release_plan = plan(version=version)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plan_path, evidence_path = scaffold_files(root, release_plan)
        pending = status_of(plan_path, evidence_path)
        assert pending.returncode == 0, pending.stderr
        report = json.loads(pending.stdout)
        assert report["ready_to_seal"] is False, "a pending campaign is ready to seal"
        assert report["next_gate"] == "repository-software"
        receipt = root / "pending.receipt.json"
        assert seal_file(plan_path, evidence_path, receipt).returncode == 2
        assert not receipt.exists()

        for index, gate, field in boolean_cases(release_plan):
            evidence = failed_at(release_plan, index)
            evidence["gates"][index]["evidence"][field] = False
            failed_path = root / f"{field}.failed.json"
            failed_path.write_text(json.dumps(evidence), encoding="utf-8")
            status = status_of(plan_path, failed_path)
            assert status.returncode == 0, (
                f"a failed gate cannot hold {gate['id']}.{field}=false: "
                f"{status.stderr}"
            )
            report = json.loads(status.stdout)
            assert report["ready_to_seal"] is False, (
                f"a campaign failed at {gate['id']} is ready to seal"
            )
            assert report["failed_gates"] == [gate["id"]]
            receipt = root / f"{field}.receipt.json"
            sealed = seal_file(plan_path, failed_path, receipt)
            assert sealed.returncode == 2
            assert not receipt.exists(), "a refused seal wrote a receipt"


def test_boolean_fields_refuse_text_and_integers_in_pass_and_fail(version: int = 2) -> None:
    release_plan = plan(version=version)
    for index, gate, field in boolean_cases(release_plan):
        for value in NOT_BOOLEAN:
            for status_value in ("pass", "fail"):
                evidence = (
                    evidence_for(release_plan)
                    if status_value == "pass"
                    else failed_at(release_plan, index)
                )
                evidence["gates"][index]["evidence"][field] = value
                try:
                    release_acceptance.status_report(release_plan, evidence)
                except release_acceptance.AcceptanceError as exc:
                    assert (
                        f"gate {gate['id']} field {field} must be boolean" in str(exc)
                    ), f"{status_value} {field}={value!r}: {exc}"
                else:
                    raise AssertionError(
                        f"{status_value} gate {gate['id']} accepted {field}={value!r}"
                    )


def test_scope_adr_plan_and_complete_storage_mapping(version: int = 2) -> None:
    manifest = yaml.safe_load(MANIFESTS[version].read_text(encoding="utf-8"))
    expected_storage = {
        "single-disk": {"mapper": "/dev/mapper/cryptroot", "fsroot": "/@vm", "subvolume": "@vm"},
        "dedicated-disk": {"mapper": "/dev/mapper/cryptvm", "fsroot": "/", "subvolume": None},
    }
    assert manifest["allowed_storage_topologies"] == expected_storage
    assert manifest["allowed_storage_topologies"] == yaml.safe_load(
        MANIFESTS[5 - version].read_text(encoding="utf-8")
    )["allowed_storage_topologies"]
    release_plan = plan(version=version)
    assert release_plan["schema_version"] == version
    assert [gate["id"] for gate in release_plan["gates"]] == list(REVIEWED_BY_VERSION[version])
    assert release_plan["gates"] == manifest["gates"]
    assert hashlib.sha256(MANIFESTS[2].read_bytes()).hexdigest() == (
        "e35e177a17bbd07a7647fec501e95d848c93752cd189284d040cfcf376f92351"
    ), "the historical v2 manifest changed"
    if version == 3:
        rows = [line.split("|")[1:-1] for line in ADR.read_text().splitlines() if line.startswith("| ")]
        gates = [(int(row[0].strip()), row[1].strip().strip("`"))
                 for row in rows if row[0].strip().isdigit()]
        assert gates == [(10 * (index + 1), gate) for index, gate in enumerate(REVIEWED_V3_EVIDENCE)]
        assert "Status: Proposed" in ADR.read_text().splitlines()[2:3]


def test_record_cli_boolean_types_are_strict_and_refusals_preserve_bytes(version: int = 2) -> None:
    release_plan = plan(version=version)
    with tempfile.TemporaryDirectory() as td:
        plan_path, evidence_path = scaffold_files(Path(td), release_plan)
        for gate in release_plan["gates"]:
            for field in REVIEWED_BY_VERSION[version][gate["id"]]["booleans"]:
                for value in NOT_BOOLEAN:
                    for status_value in ("pass", "fail"):
                        payload = valid_payload(gate)
                        payload[field] = value
                        before = evidence_path.read_bytes()
                        refused = record(plan_path, evidence_path, gate, status=status_value, payload=payload)
                        assert refused.returncode == 2, (
                            f"record {status_value} coerced {gate['id']}.{field}={value!r}"
                        )
                        assert f"field {field} must be boolean" in refused.stderr, refused.stderr
                        assert evidence_path.read_bytes() == before
            assert record(plan_path, evidence_path, gate).returncode == 0


def test_both_profiles_record_all_gates_and_seal_deterministically(version: int = 2) -> None:
    for profile in ("nitro-3060", "predator-3070"):
        release_plan = plan(profile, version=version)
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            plan_path, evidence_path = scaffold_files(root, release_plan)
            pending = json.loads(evidence_path.read_text())
            assert pending["schema_version"] == version
            assert all(gate["status"] == "pending" for gate in pending["gates"])
            assert all(value is None for gate in pending["gates"] for value in gate["evidence"].values())
            for gate in release_plan["gates"]:
                passed = record(plan_path, evidence_path, gate)
                assert passed.returncode == 0, passed.stderr
            report = json.loads(status_of(plan_path, evidence_path).stdout)
            assert report["passed"] == report["total"] == len(REVIEWED_BY_VERSION[version])
            assert report["ready_to_seal"] is True
            for filename in ("first.json", "second.json"):
                sealed = seal_file(plan_path, evidence_path, root / filename)
                assert sealed.returncode == 0, sealed.stderr
            receipt = json.loads((root / "first.json").read_text())
            assert receipt["schema_version"] == version
            assert receipt["gate_ids"] == list(REVIEWED_BY_VERSION[version])
            assert (root / "first.json").read_bytes() == (root / "second.json").read_bytes()
            before = evidence_path.read_bytes()
            changed = record(plan_path, evidence_path, release_plan["gates"][0], status="fail")
            assert changed.returncode == 2 and "immutable" in changed.stderr
            assert evidence_path.read_bytes() == before


def test_mixed_versions_refuse_without_rewriting_or_receipts(version: int = 2) -> None:
    release_plan = plan(version=version)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plan_path, evidence_path = scaffold_files(root, release_plan)
        plan_bytes, evidence_bytes = plan_path.read_bytes(), evidence_path.read_bytes()
        for operation in ("scaffold", "repository-proof", "record", "status", "seal"):
            output = root / f"{operation}.json"
            options = {
                "scaffold": ["--output", str(output)],
                "repository-proof": ["--ansible-repo", str(root), "--bootstrap-repo", str(root)],
                "record": ["--evidence", str(evidence_path), "--gate", "repository-software",
                           "--status", "pass", "--summary", "Synthetic"],
                "status": ["--evidence", str(evidence_path)],
                "seal": ["--evidence", str(evidence_path), "--output", str(output)],
            }[operation]
            result = run(sys.executable, str(TOOL), "--manifest", str(MANIFESTS[5 - version]),
                         operation, "--plan", str(plan_path), *options, stdin="{}")
            assert result.returncode == 2, result.stderr
            assert "schema_version" in result.stderr or "canonical manifest projection" in result.stderr
            assert not output.exists()
            assert plan_path.read_bytes() == plan_bytes
            assert evidence_path.read_bytes() == evidence_bytes
        # Even a plan-shaped evidence file with only its version changed is refused.
        for invalid in (5 - version, 0, 1, 4, float(version), True):
            evidence = evidence_for(release_plan)
            evidence["schema_version"] = invalid
            evidence_path.write_text(json.dumps(evidence))
            before = evidence_path.read_bytes()
            assert status_of(plan_path, evidence_path).returncode == 2
            output = root / "mixed.receipt.json"
            refused = seal_file(plan_path, evidence_path, output)
            assert refused.returncode == 2 and "schema_version" in refused.stderr
            assert not output.exists() and evidence_path.read_bytes() == before
        for invalid in (5 - version, 0, 1, 4, float(version), True):
            invalid_plan = copy.deepcopy(release_plan)
            invalid_plan["schema_version"] = invalid
            write_plan(plan_path, invalid_plan)
            before = plan_path.read_bytes()
            output = root / "invalid-scaffold.json"
            refused = run(sys.executable, str(TOOL), "--manifest", str(MANIFESTS[version]),
                          "scaffold", "--plan", str(plan_path), "--output", str(output))
            assert refused.returncode == 2 and "schema_version" in refused.stderr
            assert not output.exists() and plan_path.read_bytes() == before


def test_unsupported_versions_refuse_before_creating_a_plan(version: int = 2) -> None:
    manifest = yaml.safe_load(MANIFESTS[version].read_text())
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        for invalid in (0, 1, 4, "3", float(version), True, None):
            manifest["schema_version"] = invalid
            path = root / "manifest.yml"
            path.write_text(yaml.safe_dump(manifest))
            output = root / "plan.json"
            before = path.read_bytes()
            refused = run(sys.executable, str(TOOL), "--manifest", str(path), "plan",
                          "--profile", "nitro-3060", "--campaign-id", "synthetic-version",
                          "--ansible-sha", ANSIBLE_SHA, "--bootstrap-sha", BOOTSTRAP_SHA,
                          "--output", str(output))
            assert refused.returncode == 2 and "schema_version" in refused.stderr
            assert not output.exists() and path.read_bytes() == before

        historical = yaml.safe_load(MANIFESTS[2].read_text())
        historical["schema_version"] = 3
        path.write_text(yaml.safe_dump(historical))
        before = path.read_bytes()
        refused = run(sys.executable, str(TOOL), "--manifest", str(path), "plan",
                      "--profile", "nitro-3060", "--campaign-id", "synthetic-version",
                      "--ansible-sha", ANSIBLE_SHA, "--bootstrap-sha", BOOTSTRAP_SHA,
                      "--output", str(output))
        assert refused.returncode == 2, "relabeled v2 gates were accepted as schema_version 3"
        assert "schema_version 3 requires the reviewed v1 gate order" in refused.stderr
        assert not output.exists() and path.read_bytes() == before


def test_descriptive_fields_keep_the_versioned_text_contract(version: int = 2) -> None:
    release_plan = plan(version=version)
    for index, gate in enumerate(release_plan["gates"]):
        for field in REVIEWED_BY_VERSION[version][gate["id"]]["descriptive"]:
            if field == "lease_template":
                continue  # Its exact Template identity has a separate contract.
            for value in (False, True, "", 0, 1, 1.5, "x" * 241, "x" * 240):
                evidence = failed_at(release_plan, index)
                evidence["gates"][index]["evidence"][field] = value
                for status_value in ("pass", "fail"):
                    evidence["gates"][index]["status"] = status_value
                    try:
                        release_acceptance.validate_partial_evidence(release_plan, evidence)
                    except release_acceptance.AcceptanceError as exc:
                        assert version == 3 and value != "x" * 240, str(exc)
                        assert f"field {field} must contain 1-240 characters of text" in str(exc)
                    else:
                        assert version == 2 or value == "x" * 240, (
                            f"v3 {status_value} accepted description {gate['id']}.{field}={value!r}"
                        )


def test_record_status_and_seal_refuse_invalid_v3_descriptions(version: int = 2) -> None:
    if version == 2:
        return  # The preceding matrix preserves historical scalar behavior.
    release_plan = plan(version=version)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plan_path, evidence_path = scaffold_files(root, release_plan)
        for index, gate in enumerate(release_plan["gates"]):
            field = {"vfio-trust-lifecycle": "downward_trust_transitions",
                     "sanitized-publication": "known_limits"}.get(gate["id"])
            if field is None:
                continue
            for value in (False, "", 0, "x" * 241):
                payload = valid_payload(gate)
                payload[field] = value
                evidence = failed_at(release_plan, index)
                evidence_path.write_text(json.dumps(evidence))
                before = evidence_path.read_bytes()
                for status_value in ("pass", "fail"):
                    refused = record(plan_path, evidence_path, gate, status=status_value, payload=payload)
                    assert refused.returncode == 2, f"record accepted {field}={value!r}"
                    assert f"field {field} must contain 1-240 characters of text" in refused.stderr
                    assert evidence_path.read_bytes() == before

                edited = evidence_for(release_plan)
                edited["gates"][index]["evidence"][field] = value
                evidence_path.write_text(json.dumps(edited))
                before = evidence_path.read_bytes()
                receipt = root / "must-not-exist.json"
                for refused in (status_of(plan_path, evidence_path), seal_file(plan_path, evidence_path, receipt)):
                    assert refused.returncode == 2, f"read path accepted {field}={value!r}"
                    assert f"field {field} must contain 1-240 characters of text" in refused.stderr
                    assert not receipt.exists() and evidence_path.read_bytes() == before


def test_campaign_inputs_refuse_duplicates_and_redirection(version: int = 2) -> None:
    release_plan = plan(version=version)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        plan_path, evidence_path = scaffold_files(root, release_plan)
        before = evidence_path.read_bytes()
        duplicate = '{"clean_worktrees":false,"clean_worktrees":true,"verify_sha256":"' + "a" * 64 + '","exact_commits":"synthetic"}'
        refused = run(sys.executable, str(TOOL), "--manifest", str(MANIFESTS[version]), "record",
                      "--plan", str(plan_path), "--evidence", str(evidence_path),
                      "--gate", "repository-software", "--status", "pass", "--summary", "Synthetic",
                      stdin=duplicate)
        assert refused.returncode == 2 and "duplicate" in refused.stderr
        assert evidence_path.read_bytes() == before
        original = plan_path.read_bytes()
        for bad in (original.decode().replace(f'"schema_version": {version}',
                    f'"schema_version": {version}, "schema_version": {version}'),):
            plan_path.write_text(bad)
            output = root / "duplicate.json"
            refused = run(sys.executable, str(TOOL), "--manifest", str(MANIFESTS[version]),
                          "scaffold", "--plan", str(plan_path), "--output", str(output))
            assert refused.returncode == 2 and "duplicate" in refused.stderr
            assert not output.exists()
        plan_path.write_bytes(original)
        link = root / "link.json"
        link.symlink_to(plan_path)
        redirected = root / "redirected"
        redirected.symlink_to(root, target_is_directory=True)
        for input_path in (link, redirected / "plan.json"):
            output = root / "redirected.json"
            refused = run(sys.executable, str(TOOL), "--manifest", str(MANIFESTS[version]),
                          "scaffold", "--plan", str(input_path), "--output", str(output))
            assert refused.returncode == 2 and "redirected" in refused.stderr
            assert not output.exists()
        fifo = root / "plan.fifo"
        os.mkfifo(fifo)
        output = root / "fifo.json"
        refused = run(sys.executable, str(TOOL), "--manifest", str(MANIFESTS[version]),
                      "scaffold", "--plan", str(fifo), "--output", str(output))
        assert refused.returncode == 2 and "must be regular" in refused.stderr, refused.stderr
        assert not output.exists()
        assert plan_path.read_bytes() == original and evidence_path.read_bytes() == before


def test_lease_template_is_the_selected_initial_template(version: int = 2) -> None:
    if version == 2:
        return
    release_plan = plan(version=version)
    evidence = evidence_for(release_plan)
    gate = next(gate for gate in evidence["gates"] if gate["id"] == "gpu-lease")
    gate["evidence"]["lease_template"] = "workstation-dev"
    refused = seal(release_plan, evidence)
    assert refused.returncode == 2 and "workstation-dev-standard" in refused.stderr


def main() -> int:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    for test in tests:
        for version in (2, 3):
            test(version)
            print(f"ok: v{version} {test.__name__}")
    print(f"release acceptance contract: OK ({len(tests)} tests, both versions)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
