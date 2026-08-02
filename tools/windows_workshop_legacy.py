#!/usr/bin/env python3
"""Validate a Windows workshop evidence bundle and bind it to one qcow2 source."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from pathlib import Path
from typing import Any

import yaml

SHA_RE = re.compile(r"^[a-f0-9]{64}$")
BUILD_RE = re.compile(r"^B[0-9]+-[0-9]+-g[0-9a-f]{10}$")
TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
SECRET_KEYS = ("password", "passwd", "token", "secret", "private_key", "recovery_key")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


class WorkshopError(ValueError):
    """The Windows workshop evidence cannot be trusted for image sealing."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkshopError(message)


def load_yaml(path: Path, label: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkshopError(f"{label} does not exist: {path}") from exc
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise WorkshopError(f"{label} cannot be read as YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkshopError(f"{label} root must be a mapping")
    return data


def load_json(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise WorkshopError(f"{label} does not exist: {path}") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WorkshopError(f"{label} cannot be read as JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkshopError(f"{label} root must be a mapping")
    return data


def regular_file(path: Path, label: str) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise WorkshopError(f"{label} does not exist: {path}") from exc
    except OSError as exc:
        raise WorkshopError(f"{label} cannot be inspected: {exc}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be one regular non-symlink file: {path}")
    require(path.resolve(strict=True) == path.absolute(), f"{label} path is redirected: {path}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def mapping(node: Any, label: str) -> dict[str, Any]:
    require(isinstance(node, dict), f"{label} must be a mapping")
    return node


def reject_sensitive(node: Any, path: str = "evidence") -> None:
    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key).lower()
            require(not any(hint in key_text for hint in SECRET_KEYS),
                    f"{path}.{key} looks like secret material")
            reject_sensitive(value, f"{path}.{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            reject_sensitive(value, f"{path}[{index}]")
    elif isinstance(node, str):
        require(EMAIL_RE.search(node) is None, f"{path} contains an email address")
        require("C:\\Users\\" not in node and "/home/" not in node,
                f"{path} contains a personal filesystem path")


def expected_switch(policy: dict[str, Any], evidence: dict[str, Any], section: str, key: str) -> None:
    policy_section = mapping(policy.get(section), f"policy.{section}")
    evidence_section = mapping(evidence.get(section), f"evidence.{section}")
    require(evidence_section.get(key) is policy_section.get(key),
            f"evidence.{section}.{key}={evidence_section.get(key)!r} != policy {policy_section.get(key)!r}")


def validate(
    root: Path,
    policy_path: Path,
    evidence_path: Path,
    manifest_path: Path,
    source_path: Path,
    expected_source_sha256: str,
    looking_glass_build: str,
    store: Path,
) -> dict[str, Any]:
    root = root.resolve()
    policies_root = (root / "windows-workshops").resolve()
    images_root = (root / "images").resolve()
    store = store.resolve()
    policy_path = policy_path.resolve()
    evidence_path = evidence_path.resolve()
    manifest_path = manifest_path.resolve()
    source_path = source_path.resolve()

    require(within(policy_path, policies_root), "workshop policy must resolve below windows-workshops/")
    require(within(manifest_path, images_root), "image manifest must resolve below images/")
    require(not within(evidence_path, store), "evidence input must remain outside the managed image store")
    require(not within(source_path, store), "Windows qcow2 source must remain outside the managed image store")
    regular_file(policy_path, "workshop policy")
    regular_file(evidence_path, "workshop evidence")
    regular_file(manifest_path, "image manifest")
    regular_file(source_path, "Windows qcow2 source")

    require(SHA_RE.fullmatch(expected_source_sha256) is not None,
            "expected source SHA-256 must be 64 lowercase hexadecimal characters")
    actual_source_sha256 = sha256_file(source_path)
    require(actual_source_sha256 == expected_source_sha256,
            "Windows qcow2 source SHA-256 differs from the independently supplied value")
    require(BUILD_RE.fullmatch(looking_glass_build) is not None,
            "shared Looking Glass build is invalid")

    policy = load_yaml(policy_path, "workshop policy")
    evidence = load_json(evidence_path, "workshop evidence")
    manifest = load_yaml(manifest_path, "image manifest")
    reject_sensitive(evidence)

    image_id = policy.get("id")
    require(policy.get("schema_version") == 1, "workshop policy schema_version must be 1")
    require(isinstance(image_id, str) and policy_path.name == f"{image_id}.yml",
            "workshop policy filename must equal policy.id")
    require(policy.get("image") == image_id, "workshop policy image must equal policy.id")
    require(manifest.get("id") == image_id and manifest_path.name == f"{image_id}.yml",
            "workshop policy and image manifest identity differ")
    require(manifest.get("status") == "not-built",
            "Windows workshop validation must precede image sealing")
    require(manifest.get("os_family") == "windows", "workshop image must be Windows")
    require(manifest.get("source_type") == "local", "Windows workshop output must use local import")
    require(manifest.get("private") is True, "Windows workshop artefacts must remain private")
    require(manifest.get("licensing", {}).get("redistributable") is False,
            "Windows workshop artefacts cannot be redistributable")
    require(manifest.get("supports", {}).get("vfio") is True,
            "Windows workshop image must support VFIO")
    require(manifest.get("supports", {}).get("qemu_guest_agent") is True,
            "Windows workshop image must support QEMU Guest Agent")
    require(manifest.get("requires", {}).get("uefi") is True,
            "Windows workshop image must require UEFI")
    require(manifest.get("requires", {}).get("secure_boot") is True,
            "Windows workshop image must require Secure Boot")
    require(manifest.get("requires", {}).get("tpm2") is True,
            "Windows workshop image must require TPM2")

    require(evidence.get("schema_version") == 1, "workshop evidence schema_version must be 1")
    require(evidence.get("image") == image_id, "workshop evidence image differs from policy")
    collected_at = evidence.get("collected_at_utc")
    require(isinstance(collected_at, str) and TIME_RE.fullmatch(collected_at) is not None,
            "workshop evidence collected_at_utc must be an ISO-8601 UTC timestamp")

    identity_policy = mapping(policy.get("identity"), "policy.identity") if "identity" in policy else {
        "mode": policy.get("identity_mode"),
        "generalized": policy.get("generalized"),
        "microsoft_account": policy.get("microsoft_account"),
        "local_lab_account": policy.get("local_lab_account"),
        "credential_reuse": policy.get("credential_reuse"),
        "setup_image_state": policy.get("setup_image_state"),
    }
    identity = mapping(evidence.get("identity"), "evidence.identity")
    require(identity.get("mode") == identity_policy.get("mode"), "identity mode differs from policy")
    require(identity.get("generalized") is identity_policy.get("generalized"),
            "generalization evidence differs from policy")
    microsoft_present = identity.get("microsoft_account_present")
    local_present = identity.get("local_lab_account_present")
    require(isinstance(microsoft_present, bool), "microsoft_account_present must be boolean")
    require(isinstance(local_present, bool), "local_lab_account_present must be boolean")
    if identity_policy.get("microsoft_account") == "required":
        require(microsoft_present, "personal clean image requires Microsoft-account presence evidence")
    elif identity_policy.get("microsoft_account") == "forbidden":
        require(not microsoft_present, "generalized dirty template forbids Microsoft accounts")
    else:
        raise WorkshopError("unsupported microsoft_account policy")
    if identity_policy.get("local_lab_account") == "required":
        require(local_present, "dirty template requires a local lab account")
    elif identity_policy.get("local_lab_account") not in {"optional", "forbidden"}:
        raise WorkshopError("unsupported local_lab_account policy")
    if identity_policy.get("local_lab_account") == "forbidden":
        require(not local_present, "policy forbids a local lab account")
    require(identity_policy.get("credential_reuse") == "forbidden",
            "workshop policy must forbid credential reuse")
    require(identity.get("credential_reuse") is False,
            "evidence must attest that no credential was reused")

    setup_image_state = identity.get("setup_image_state")
    expected_setup_image_state = identity_policy.get("setup_image_state")
    require(isinstance(setup_image_state, str) and setup_image_state,
            "evidence.identity.setup_image_state must be a documented Windows Setup state")
    require(setup_image_state == expected_setup_image_state,
            f"Windows Setup state differs from policy: expected {expected_setup_image_state!r}, observed {setup_image_state!r}")
    if identity_policy.get("generalized") is True:
        require(setup_image_state == "IMAGE_STATE_GENERALIZE_RESEAL_TO_OOBE",
                "generalized Windows template must be resealed to OOBE")
    else:
        require(setup_image_state == "IMAGE_STATE_COMPLETE",
                "personal singleton must remain a completed specialized installation")

    for section, keys in {
        "firmware": ["secure_boot", "tpm2_present", "tpm2_ready"],
        "drivers": ["nvidia_gpu", "virtio_gpu_recovery", "virtio_input", "ivshmem"],
        "virtual_display": ["present", "active"],
        "hygiene": ["reboot_pending", "update_reboot_pending"],
    }.items():
        for key in keys:
            expected_switch(policy, evidence, section, key)

    services_policy = mapping(policy.get("services"), "policy.services")
    services = mapping(evidence.get("services"), "evidence.services")
    for key in ("qemu_guest_agent", "looking_glass_host"):
        require(services.get(key) == services_policy.get(key) == "running",
                f"evidence.services.{key} must be running")

    lg_policy = mapping(policy.get("looking_glass"), "policy.looking_glass")
    lg = mapping(evidence.get("looking_glass"), "evidence.looking_glass")
    require(lg_policy.get("build") == looking_glass_build,
            "workshop policy Looking Glass build differs from shared host contract")
    require(manifest.get("looking_glass_host_build_required") == looking_glass_build,
            "image manifest Looking Glass build differs from shared host contract")
    require(lg.get("build") == looking_glass_build, "evidence Looking Glass build differs from policy")
    require(lg.get("capture_started") is lg_policy.get("capture_started") is True,
            "Looking Glass capture did not reach Capture Start")
    require(lg.get("capture_interface") == lg_policy.get("capture_interface") == "D12",
            "Looking Glass capture interface must be D12")

    display_policy = mapping(policy.get("virtual_display"), "policy.virtual_display")
    display = mapping(evidence.get("virtual_display"), "evidence.virtual_display")
    require(display.get("width") == display_policy.get("width") == 1920,
            "virtual display width must be 1920")
    require(display.get("height") == display_policy.get("height") == 1080,
            "virtual display height must be 1080")

    handoff = mapping(policy.get("handoff"), "policy.handoff")
    defaults = mapping(manifest.get("defaults"), "manifest.defaults")
    require(handoff.get("source_type") == manifest.get("source_type") == "local",
            "workshop handoff must be a local import")
    require(handoff.get("private") is manifest.get("private") is True,
            "workshop handoff must remain private")
    require(handoff.get("instance_policy") == manifest.get("instance_policy"),
            "workshop instance policy differs from image manifest")
    require(handoff.get("lifecycle") == defaults.get("lifecycle"),
            "workshop lifecycle differs from image defaults")
    require(handoff.get("network_profile") == defaults.get("network_profile"),
            "workshop network differs from image defaults")
    require(handoff.get("network_profile") in manifest.get("network_allowlist", []),
            "workshop network is outside the image allowlist")

    return {
        "schema_version": 1,
        "id": image_id,
        "image": image_id,
        "policy_sha256": canonical_hash(policy),
        "evidence_sha256": sha256_file(evidence_path),
        "source_sha256": actual_source_sha256,
        "identity_mode": identity.get("mode"),
        "generalized": identity.get("generalized"),
        "setup_image_state": setup_image_state,
        "looking_glass_build": looking_glass_build,
        "capture_interface": lg.get("capture_interface"),
        "virtual_display": {"width": display.get("width"), "height": display.get("height")},
        "collected_at_utc": collected_at,
        "private": True,
        "ready": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--policy", required=True)
    parser.add_argument("--evidence", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--looking-glass-build", required=True)
    parser.add_argument("--store", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = validate(
            Path(args.root),
            Path(args.policy),
            Path(args.evidence),
            Path(args.manifest),
            Path(args.source),
            args.source_sha256,
            args.looking_glass_build,
            Path(args.store),
        )
    except (OSError, WorkshopError) as exc:
        print(f"Windows workshop refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
