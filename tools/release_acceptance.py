#!/usr/bin/env python3
"""Build, execute and seal the reviewed hardware acceptance campaign."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
CAMPAIGN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,63}$")
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
BOOL_FIELDS = {
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
}


class AcceptanceError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AcceptanceError(message)


def load_yaml(path: Path, label: str = "acceptance manifest") -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise AcceptanceError(f"cannot read {label}: {exc}") from exc
    require(isinstance(data, dict), f"{label} root must be a mapping")
    return data


def load_json_stdin(label: str) -> dict[str, Any]:
    try:
        data = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise AcceptanceError(f"{label} is not valid JSON: {exc}") from exc
    require(isinstance(data, dict), f"{label} root must be a mapping")
    return data


def canonical_json(data: Any) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":")) + "\n").encode()


def write_json(path: Path, data: dict[str, Any], *, replace: bool) -> None:
    parent = path.parent
    require(parent.exists() and parent.is_dir(), f"output directory is missing: {parent}")
    if path.exists() or path.is_symlink():
        require(replace, f"output already exists: {path}")
        info = path.lstat()
        require(
            stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"refusing to replace a non-regular output: {path}",
        )
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=parent)
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
        raise


def validate_manifest(manifest: dict[str, Any]) -> None:
    require(manifest.get("schema_version") == 1, "acceptance schema_version must be 1")
    profiles = manifest.get("profiles")
    repositories = manifest.get("repositories")
    gates = manifest.get("gates")
    topologies = manifest.get("allowed_storage_topologies")
    patterns = manifest.get("forbidden_evidence_patterns")
    require(
        isinstance(profiles, dict)
        and set(profiles) == {"nitro-3060", "predator-3070"},
        "acceptance profiles must be the reviewed Nitro and Predator profiles",
    )
    require(
        isinstance(repositories, dict)
        and set(repositories) == {"privatestack_ansible", "arch_bootstrap"},
        "acceptance repositories must name both release repositories",
    )
    require(isinstance(gates, list) and gates, "acceptance gates must be a non-empty list")
    require(
        isinstance(topologies, dict)
        and set(topologies) == {"single-disk", "dedicated-disk"},
        "acceptance storage topologies differ from the bootstrap contract",
    )
    require(isinstance(patterns, list) and patterns, "forbidden evidence patterns are missing")

    orders: list[int] = []
    ids: list[str] = []
    for gate in gates:
        require(isinstance(gate, dict), "every acceptance gate must be a mapping")
        require(
            set(gate) == {"id", "order", "execution", "required_evidence"},
            "acceptance gate keys differ from the schema",
        )
        gate_id = gate.get("id")
        order = gate.get("order")
        execution = gate.get("execution")
        fields = gate.get("required_evidence")
        require(
            isinstance(gate_id, str)
            and re.fullmatch(r"[a-z][a-z0-9-]+", gate_id) is not None,
            "acceptance gate id is invalid",
        )
        require(
            isinstance(order, int) and not isinstance(order, bool),
            f"acceptance gate {gate_id} order must be an integer",
        )
        require(
            execution
            in {"read-only", "operator-apply", "hardware-runtime", "destructive-hardware"},
            f"acceptance gate {gate_id} execution class is invalid",
        )
        require(
            isinstance(fields, list)
            and fields
            and len(fields) == len(set(fields))
            and all(
                isinstance(field, str)
                and re.fullmatch(r"[a-z][a-z0-9_]+", field)
                for field in fields
            ),
            f"acceptance gate {gate_id} evidence fields are invalid",
        )
        orders.append(order)
        ids.append(gate_id)
    require(
        orders == sorted(orders) and len(orders) == len(set(orders)),
        "acceptance gate order must be unique and increasing",
    )
    require(len(ids) == len(set(ids)), "acceptance gate ids must be unique")

    expected_single = {
        "mapper": "/dev/mapper/cryptroot",
        "fsroot": "/@vm",
        "subvolume": "@vm",
    }
    expected_dedicated = {
        "mapper": "/dev/mapper/cryptvm",
        "fsroot": "/",
        "subvolume": None,
    }
    require(
        topologies["single-disk"] == expected_single,
        "single-disk acceptance topology differs from arch-bootstrap",
    )
    require(
        topologies["dedicated-disk"] == expected_dedicated,
        "dedicated-disk acceptance topology differs from arch-bootstrap",
    )
    for repository, contract in repositories.items():
        require(
            isinstance(contract, dict) and set(contract) == {"remote", "required_branch"},
            f"acceptance repository {repository} keys differ from the schema",
        )
        require(
            isinstance(contract["remote"], str) and "/" in contract["remote"],
            f"acceptance repository {repository} remote is invalid",
        )
        require(
            contract["required_branch"] == "main",
            f"acceptance repository {repository} must publish from main",
        )
    for pattern in patterns:
        require(isinstance(pattern, str) and pattern, "forbidden evidence pattern must be text")
        try:
            re.compile(pattern)
        except re.error as exc:
            raise AcceptanceError(
                f"invalid forbidden evidence pattern {pattern!r}: {exc}"
            ) from exc


def build_plan(
    manifest: dict[str, Any],
    profile: str,
    campaign_id: str,
    ansible_sha: str,
    bootstrap_sha: str,
) -> dict[str, Any]:
    validate_manifest(manifest)
    require(profile in manifest["profiles"], f"unknown acceptance profile: {profile}")
    require(
        CAMPAIGN_RE.fullmatch(campaign_id) is not None,
        "campaign id must be 3-64 lowercase letters, digits or hyphens",
    )
    require(
        SHA_RE.fullmatch(ansible_sha) is not None,
        "privatestack SHA must be 40 lowercase hex",
    )
    require(
        SHA_RE.fullmatch(bootstrap_sha) is not None,
        "arch-bootstrap SHA must be 40 lowercase hex",
    )
    gates = [
        {
            "id": gate["id"],
            "order": gate["order"],
            "execution": gate["execution"],
            "required_evidence": gate["required_evidence"],
        }
        for gate in manifest["gates"]
    ]
    return {
        "schema_version": 1,
        "campaign_id": campaign_id,
        "profile": profile,
        "profile_label": manifest["profiles"][profile]["label"],
        "profile_order": manifest["profiles"][profile]["order"],
        "repositories": {
            "privatestack_ansible": {
                **manifest["repositories"]["privatestack_ansible"],
                "expected_sha": ansible_sha,
            },
            "arch_bootstrap": {
                **manifest["repositories"]["arch_bootstrap"],
                "expected_sha": bootstrap_sha,
            },
        },
        "gates": gates,
        "allowed_storage_topologies": manifest["allowed_storage_topologies"],
        "publication_policy": {
            "raw_logs_local_only": True,
            "sanitized_summary_only": True,
            "forbidden_evidence_patterns": manifest["forbidden_evidence_patterns"],
        },
    }


def validate_plan(manifest: dict[str, Any], plan: dict[str, Any]) -> None:
    validate_manifest(manifest)
    require(
        set(plan)
        == {
            "schema_version",
            "campaign_id",
            "profile",
            "profile_label",
            "profile_order",
            "repositories",
            "gates",
            "allowed_storage_topologies",
            "publication_policy",
        },
        "release plan keys differ from the schema",
    )
    repositories = plan.get("repositories")
    require(
        isinstance(repositories, dict)
        and set(repositories) == {"privatestack_ansible", "arch_bootstrap"},
        "release plan repositories differ from the manifest",
    )
    try:
        ansible_sha = repositories["privatestack_ansible"]["expected_sha"]
        bootstrap_sha = repositories["arch_bootstrap"]["expected_sha"]
    except (KeyError, TypeError) as exc:
        raise AcceptanceError("release plan repository identities are incomplete") from exc
    expected = build_plan(
        manifest,
        str(plan.get("profile", "")),
        str(plan.get("campaign_id", "")),
        str(ansible_sha),
        str(bootstrap_sha),
    )
    require(plan == expected, "release plan differs from the canonical manifest projection")


def walk_strings(value: Any, path: str = "$") -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    if isinstance(value, str):
        found.append((path, value))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(walk_strings(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            found.extend(walk_strings(item, f"{path}.{key}"))
    return found


def forbidden_patterns(plan: dict[str, Any]) -> list[re.Pattern[str]]:
    return [
        re.compile(pattern)
        for pattern in plan["publication_policy"]["forbidden_evidence_patterns"]
    ]


def reject_sensitive_strings(plan: dict[str, Any], value: Any) -> None:
    patterns = forbidden_patterns(plan)
    for path, text in walk_strings(value):
        for pattern in patterns:
            require(
                pattern.search(text) is None,
                f"evidence contains forbidden sensitive pattern at {path}",
            )


def scaffold(plan: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "campaign_id": plan["campaign_id"],
        "profile": plan["profile"],
        "repositories": {
            key: value["expected_sha"] for key, value in plan["repositories"].items()
        },
        "storage": None,
        "gates": [
            {
                "id": gate["id"],
                "status": "pending",
                "summary": "",
                "evidence": {field: None for field in gate["required_evidence"]},
            }
            for gate in plan["gates"]
        ],
        "sanitized": False,
    }


def validate_gate_payload(
    planned: dict[str, Any],
    payload: dict[str, Any],
    *,
    complete: bool,
) -> None:
    require(
        isinstance(payload, dict),
        f"evidence gate {planned['id']} data must be a mapping",
    )
    required = set(planned["required_evidence"])
    require(
        set(payload) == required,
        f"evidence gate {planned['id']} fields differ from the plan",
    )
    for field, value in payload.items():
        if value is None:
            require(
                not complete,
                f"evidence gate {planned['id']} field {field} is missing",
            )
            continue
        require(
            not isinstance(value, (dict, list)),
            f"evidence gate {planned['id']} field {field} must be one scalar",
        )
        if field.endswith("sha256"):
            require(
                isinstance(value, str) and HEX64_RE.fullmatch(value) is not None,
                f"evidence gate {planned['id']} field {field} must be SHA-256",
            )
        if field in BOOL_FIELDS:
            require(
                isinstance(value, bool),
                f"evidence gate {planned['id']} field {field} must be boolean",
            )


def validate_storage(plan: dict[str, Any], storage: Any, *, required: bool) -> None:
    if storage is None:
        require(not required, "evidence storage is missing")
        return
    require(isinstance(storage, dict), "evidence storage must be a mapping")
    require(
        set(storage)
        == {
            "topology",
            "mapper",
            "fsroot",
            "subvolume",
            "mountpoint",
            "fstype",
            "nocow",
        },
        "evidence storage keys differ from the schema",
    )
    topology = storage.get("topology")
    require(
        topology in plan["allowed_storage_topologies"],
        "evidence storage topology is unsupported",
    )
    expected = plan["allowed_storage_topologies"][topology]
    require(storage.get("mapper") == expected["mapper"], "evidence storage mapper differs")
    require(storage.get("fsroot") == expected["fsroot"], "evidence storage fsroot differs")
    require(
        storage.get("subvolume") == expected["subvolume"],
        "evidence storage subvolume differs",
    )
    require(
        storage.get("mountpoint") == "/var/lib/libvirt/images",
        "evidence storage mountpoint differs",
    )
    require(storage.get("fstype") == "btrfs", "evidence storage filesystem differs")
    require(storage.get("nocow") is True, "evidence must confirm NOCOW")


def validate_partial_evidence(plan: dict[str, Any], evidence: dict[str, Any]) -> None:
    require(
        set(evidence)
        == {
            "schema_version",
            "campaign_id",
            "profile",
            "repositories",
            "storage",
            "gates",
            "sanitized",
        },
        "evidence keys differ from the schema",
    )
    require(evidence.get("schema_version") == 1, "evidence schema_version must be 1")
    require(evidence.get("campaign_id") == plan["campaign_id"], "evidence campaign id differs")
    require(evidence.get("profile") == plan["profile"], "evidence hardware profile differs")
    require(
        evidence.get("repositories")
        == {key: value["expected_sha"] for key, value in plan["repositories"].items()},
        "evidence repository commits differ from the frozen plan",
    )
    require(
        isinstance(evidence.get("sanitized"), bool),
        "evidence sanitized flag must be boolean",
    )
    validate_storage(plan, evidence.get("storage"), required=False)

    gates = evidence.get("gates")
    require(isinstance(gates, list), "evidence gates must be a list")
    require(len(gates) == len(plan["gates"]), "evidence gate count differs from the plan")
    seen_incomplete = False
    for planned, observed in zip(plan["gates"], gates, strict=True):
        require(isinstance(observed, dict), "every evidence gate must be a mapping")
        require(
            set(observed) == {"id", "status", "evidence", "summary"},
            f"evidence gate {planned['id']} keys differ from the schema",
        )
        require(observed["id"] == planned["id"], "evidence gate order or id differs")
        status_value = observed["status"]
        require(
            status_value in {"pending", "pass", "fail"},
            f"evidence gate {planned['id']} status is invalid",
        )
        if status_value == "pending":
            seen_incomplete = True
            require(
                observed["summary"] == "",
                f"pending evidence gate {planned['id']} summary must be empty",
            )
            validate_gate_payload(planned, observed["evidence"], complete=False)
            require(
                all(value is None for value in observed["evidence"].values()),
                f"pending evidence gate {planned['id']} must contain no values",
            )
        else:
            require(
                isinstance(observed["summary"], str)
                and 1 <= len(observed["summary"]) <= 240,
                f"evidence gate {planned['id']} summary is invalid",
            )
            validate_gate_payload(
                planned,
                observed["evidence"],
                complete=status_value == "pass",
            )
            if status_value == "fail":
                seen_incomplete = True
        if seen_incomplete:
            require(
                status_value != "pass",
                "a later gate cannot pass before every earlier gate passes",
            )
    if evidence["sanitized"]:
        require(
            gates[-1]["id"] == "sanitized-publication"
            and gates[-1]["status"] == "pass",
            "sanitized evidence requires the publication gate to pass",
        )
    reject_sensitive_strings(plan, evidence)


def record_gate(
    plan: dict[str, Any],
    evidence: dict[str, Any],
    gate_id: str,
    status_value: str,
    summary: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    validate_partial_evidence(plan, evidence)
    require(status_value in {"pass", "fail"}, "record status must be pass or fail")
    require(
        isinstance(summary, str) and 1 <= len(summary) <= 240,
        "record summary must contain 1-240 characters",
    )
    gate_index = next(
        (index for index, gate in enumerate(plan["gates"]) if gate["id"] == gate_id),
        None,
    )
    require(gate_index is not None, f"unknown acceptance gate: {gate_id}")
    assert gate_index is not None
    for earlier in evidence["gates"][:gate_index]:
        require(
            earlier["status"] == "pass",
            f"gate {gate_id} cannot be recorded before {earlier['id']} passes",
        )

    planned = plan["gates"][gate_index]
    validate_gate_payload(planned, payload, complete=status_value == "pass")
    existing = evidence["gates"][gate_index]
    if existing["status"] == "pass":
        require(
            existing
            == {
                "id": gate_id,
                "status": status_value,
                "summary": summary,
                "evidence": payload,
            },
            f"passed gate {gate_id} is immutable",
        )
        return evidence

    updated = json.loads(json.dumps(evidence))
    updated["gates"][gate_index] = {
        "id": gate_id,
        "status": status_value,
        "summary": summary,
        "evidence": payload,
    }

    if gate_id == "storage-handoff" and status_value == "pass":
        topology = payload["topology"]
        require(
            topology in plan["allowed_storage_topologies"],
            "storage-handoff topology is unsupported",
        )
        expected = plan["allowed_storage_topologies"][topology]
        require(payload["mapper"] == expected["mapper"], "storage-handoff mapper differs from the plan")
        require(payload["fsroot"] == expected["fsroot"], "storage-handoff fsroot differs from the plan")
        require(payload["fstype"] == "btrfs", "storage-handoff filesystem differs from the plan")
        require(payload["nocow"] is True, "storage-handoff must prove NOCOW")
        updated["storage"] = {
            "topology": topology,
            "mapper": expected["mapper"],
            "fsroot": expected["fsroot"],
            "subvolume": expected["subvolume"],
            "mountpoint": "/var/lib/libvirt/images",
            "fstype": "btrfs",
            "nocow": True,
        }

    if gate_id == "sanitized-publication" and status_value == "pass":
        require(
            payload.get("no_sensitive_patterns") is True,
            "publication gate must confirm no sensitive patterns",
        )
        updated["sanitized"] = True

    validate_partial_evidence(plan, updated)
    return updated


def status_report(plan: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    validate_partial_evidence(plan, evidence)
    passed = [gate["id"] for gate in evidence["gates"] if gate["status"] == "pass"]
    failed = [gate["id"] for gate in evidence["gates"] if gate["status"] == "fail"]
    next_gate = next(
        (gate["id"] for gate in evidence["gates"] if gate["status"] != "pass"),
        None,
    )
    return {
        "campaign_id": plan["campaign_id"],
        "profile": plan["profile"],
        "passed": len(passed),
        "total": len(plan["gates"]),
        "failed_gates": failed,
        "next_gate": next_gate,
        "ready_to_seal": next_gate is None and evidence["sanitized"] is True,
    }


def git_text(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "LC_ALL": "C"},
    )
    require(
        result.returncode == 0,
        f"git {' '.join(args)} failed in {repo}: {result.stderr.strip()}",
    )
    return result.stdout.strip()


def verify_repository(
    name: str,
    repo: Path,
    contract: dict[str, Any],
    log_dir: Path | None,
) -> tuple[str, bytes]:
    require(
        repo.exists() and repo.is_dir() and not repo.is_symlink(),
        f"{name} checkout is missing or redirected: {repo}",
    )
    require((repo / ".git").exists(), f"{name} is not a Git checkout: {repo}")
    head = git_text(repo, "rev-parse", "HEAD")
    branch = git_text(repo, "branch", "--show-current")
    remote = git_text(repo, "remote", "get-url", "origin")
    dirty = git_text(repo, "status", "--porcelain=v1", "--untracked-files=all")
    require(
        head == contract["expected_sha"],
        f"{name} HEAD differs: expected {contract['expected_sha']}, observed {head}",
    )
    require(
        branch == contract["required_branch"],
        f"{name} branch differs: expected {contract['required_branch']}, observed {branch}",
    )
    require(
        contract["remote"] in remote.removesuffix(".git"),
        f"{name} origin differs from {contract['remote']}",
    )
    require(dirty == "", f"{name} worktree is not clean")

    verify_path = repo / "verify.sh"
    require(
        verify_path.is_file() and not verify_path.is_symlink(),
        f"{name} verify.sh is missing or redirected",
    )
    result = subprocess.run(
        ["bash", "verify.sh"],
        cwd=repo,
        text=False,
        capture_output=True,
        check=False,
        env={**os.environ, "LC_ALL": "C"},
    )
    transcript = (
        f"repository={name}\nhead={head}\nbranch={branch}\n".encode()
        + b"\n--- stdout ---\n"
        + result.stdout
        + b"\n--- stderr ---\n"
        + result.stderr
    )
    if log_dir is not None:
        log_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        require(
            log_dir.is_dir() and not log_dir.is_symlink(),
            f"verification log directory is unsafe: {log_dir}",
        )
        log_path = log_dir / f"{name}.verify.log"
        require(
            not log_path.exists() and not log_path.is_symlink(),
            f"verification log already exists: {log_path}",
        )
        log_path.write_bytes(transcript)
        log_path.chmod(0o600)
    if result.returncode != 0:
        sys.stderr.buffer.write(transcript)
        raise AcceptanceError(f"{name} verification failed")
    return head, transcript


def repository_proof(
    plan: dict[str, Any],
    ansible_repo: Path,
    bootstrap_repo: Path,
    log_dir: Path | None,
) -> dict[str, Any]:
    ansible_head, ansible_log = verify_repository(
        "privatestack_ansible",
        ansible_repo,
        plan["repositories"]["privatestack_ansible"],
        log_dir,
    )
    bootstrap_head, bootstrap_log = verify_repository(
        "arch_bootstrap",
        bootstrap_repo,
        plan["repositories"]["arch_bootstrap"],
        log_dir,
    )
    digest = hashlib.sha256(
        b"privatestack_ansible\0"
        + ansible_log
        + b"\0arch_bootstrap\0"
        + bootstrap_log
    ).hexdigest()
    return {
        "verify_sha256": digest,
        "clean_worktrees": True,
        "exact_commits": (
            f"privatestack_ansible={ansible_head};arch_bootstrap={bootstrap_head}"
        ),
    }


def validate_evidence(plan: dict[str, Any], evidence: dict[str, Any]) -> None:
    validate_partial_evidence(plan, evidence)
    require(evidence["sanitized"] is True, "evidence must explicitly be sanitized")
    validate_storage(plan, evidence["storage"], required=True)
    for gate in evidence["gates"]:
        require(gate["status"] == "pass", f"evidence gate {gate['id']} did not pass")


def seal(plan: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    validate_evidence(plan, evidence)
    evidence_hash = hashlib.sha256(canonical_json(evidence)).hexdigest()
    plan_hash = hashlib.sha256(canonical_json(plan)).hexdigest()
    return {
        "schema_version": 1,
        "campaign_id": plan["campaign_id"],
        "profile": plan["profile"],
        "repositories": {
            key: value["expected_sha"] for key, value in plan["repositories"].items()
        },
        "storage_topology": evidence["storage"]["topology"],
        "gate_ids": [gate["id"] for gate in plan["gates"]],
        "gate_count": len(plan["gates"]),
        "plan_sha256": plan_hash,
        "evidence_sha256": evidence_hash,
        "sanitized": True,
        "result": "pass",
    }


def status_hint(data: dict[str, Any]) -> dict[str, Any]:
    hint: dict[str, Any] = {}
    if "campaign_id" in data:
        hint["campaign_id"] = data["campaign_id"]
    if "profile" in data:
        hint["profile"] = data["profile"]
    if "result" in data:
        hint["result"] = data["result"]
    return hint


def emit_or_write(
    data: dict[str, Any], output: str | None, *, replace: bool = False
) -> None:
    if output:
        write_json(Path(output), data, replace=replace)
        print(json.dumps({"output": output, **status_hint(data)}, sort_keys=True, indent=2))
    else:
        print(json.dumps(data, sort_keys=True, indent=2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    plan_parser = subparsers.add_parser("plan")
    plan_parser.add_argument("--profile", required=True)
    plan_parser.add_argument("--campaign-id", required=True)
    plan_parser.add_argument("--ansible-sha", required=True)
    plan_parser.add_argument("--bootstrap-sha", required=True)
    plan_parser.add_argument("--output")

    scaffold_parser = subparsers.add_parser("scaffold")
    scaffold_parser.add_argument("--plan", required=True)
    scaffold_parser.add_argument("--output", required=True)

    proof_parser = subparsers.add_parser("repository-proof")
    proof_parser.add_argument("--plan", required=True)
    proof_parser.add_argument("--ansible-repo", required=True)
    proof_parser.add_argument("--bootstrap-repo", required=True)
    proof_parser.add_argument("--log-dir")

    record_parser = subparsers.add_parser("record")
    record_parser.add_argument("--plan", required=True)
    record_parser.add_argument("--evidence", required=True)
    record_parser.add_argument("--gate", required=True)
    record_parser.add_argument("--status", choices=("pass", "fail"), required=True)
    record_parser.add_argument("--summary", required=True)

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--plan", required=True)
    status_parser.add_argument("--evidence", required=True)

    seal_parser = subparsers.add_parser("seal")
    seal_parser.add_argument("--plan", required=True)
    seal_parser.add_argument("--evidence")
    seal_parser.add_argument("--output")

    args = parser.parse_args()

    try:
        manifest = load_yaml(Path(args.manifest))
        if args.operation == "plan":
            result = build_plan(
                manifest,
                args.profile,
                args.campaign_id,
                args.ansible_sha,
                args.bootstrap_sha,
            )
            emit_or_write(result, args.output)
        else:
            plan = load_yaml(Path(args.plan), "release plan")
            validate_plan(manifest, plan)
            if args.operation == "scaffold":
                result = scaffold(plan)
                write_json(Path(args.output), result, replace=False)
                print(
                    json.dumps(
                        {
                            "campaign_id": plan["campaign_id"],
                            "evidence": args.output,
                            "next_gate": plan["gates"][0]["id"],
                        },
                        sort_keys=True,
                        indent=2,
                    )
                )
            elif args.operation == "repository-proof":
                result = repository_proof(
                    plan,
                    Path(args.ansible_repo).absolute(),
                    Path(args.bootstrap_repo).absolute(),
                    Path(args.log_dir).absolute() if args.log_dir else None,
                )
                print(json.dumps(result, sort_keys=True, indent=2))
            elif args.operation == "record":
                evidence_path = Path(args.evidence)
                evidence = load_yaml(evidence_path, "release evidence")
                payload = load_json_stdin("gate evidence")
                updated = record_gate(
                    plan,
                    evidence,
                    args.gate,
                    args.status,
                    args.summary,
                    payload,
                )
                write_json(evidence_path, updated, replace=True)
                print(json.dumps(status_report(plan, updated), sort_keys=True, indent=2))
            elif args.operation == "status":
                evidence = load_yaml(Path(args.evidence), "release evidence")
                print(json.dumps(status_report(plan, evidence), sort_keys=True, indent=2))
            else:
                evidence = (
                    load_yaml(Path(args.evidence), "release evidence")
                    if args.evidence
                    else load_json_stdin("release evidence")
                )
                result = seal(plan, evidence)
                emit_or_write(result, args.output)
    except (AcceptanceError, OSError) as exc:
        print(f"release acceptance refused: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
