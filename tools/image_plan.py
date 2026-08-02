#!/usr/bin/env python3
"""Build a deterministic, side-effect-free image acquisition/sealing plan."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yaml

ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
SHA_RE = re.compile(r"^[a-f0-9]{64}$")
LG_BUILD_RE = re.compile(r"^B[0-9]+-[0-9]+-g[0-9a-f]{10}$")
MUTABLE_EVIDENCE_FIELDS = {"status", "sha256", "looking_glass_host_build_observed"}


class PlanError(ValueError):
    """The selected image policy cannot become a safe factory plan."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PlanError(message)


def load_mapping(path: Path, label: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PlanError(f"{label} does not exist: {path}") from exc
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise PlanError(f"{label} cannot be read as YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise PlanError(f"{label} root must be a mapping")
    return data


def within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def select_string(override: str, manifest_value: Any) -> str:
    if override:
        return override
    return manifest_value if isinstance(manifest_value, str) else ""


def policy_sha256(manifest: dict[str, Any]) -> str:
    policy = {key: value for key, value in manifest.items() if key not in MUTABLE_EVIDENCE_FIELDS}
    canonical = json.dumps(policy, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_plan(
    root: Path,
    manifest_arg: str,
    store: Path,
    operation: str,
    source_url_override: str,
    source_sha_override: str,
    local_source_arg: str,
    looking_glass_observed_override: str,
) -> dict[str, Any]:
    require(operation in {"prepare", "validate"}, "operation must be prepare or validate")
    root = root.resolve()
    images_root = (root / "images").resolve()
    workshops_root = (root / "windows-workshops").resolve()
    store = store.resolve()
    manifest_path = Path(manifest_arg)
    manifest_path = (root / manifest_path).resolve() if not manifest_path.is_absolute() else manifest_path.resolve()
    require(within(manifest_path, images_root), "image_factory_manifest must resolve below images/")

    manifest = load_mapping(manifest_path, "image manifest")
    require(manifest.get("schema_version") == 1, "image manifest schema_version must be 1")
    image_id = manifest.get("id")
    require(isinstance(image_id, str) and ID_RE.fullmatch(image_id) is not None, "image id is invalid")
    require(manifest_path.name == f"{image_id}.yml", "image manifest filename must equal manifest.id")
    require(manifest.get("status") in {"not-built", "sealed"}, "unsupported image status")
    require(manifest.get("format") == "qcow2", "M5 seals qcow2 bases only")
    filename = manifest.get("filename")
    require(
        isinstance(filename, str) and filename == Path(filename).name and filename.endswith(".qcow2"),
        "image filename must be one qcow2 basename",
    )
    os_family = manifest.get("os_family")
    require(os_family in {"linux", "windows"}, "unsupported os_family")
    source_type = manifest.get("source_type")
    require(source_type in {"official-cloud", "official-iso", "local"}, "unsupported source_type")
    require(
        source_type != "official-iso",
        "official ISO media is workshop input, not a sealable base; import the workshop qcow2 as local",
    )
    if os_family == "windows":
        require(source_type == "local", "Windows workshop outputs must use local import")
        require(manifest.get("private") is True, "Windows image artefacts must remain private")
        require(
            manifest.get("licensing", {}).get("redistributable") is False,
            "Windows image artefacts cannot be redistributable",
        )

    virtual_size_gib = manifest.get("virtual_size_gib")
    require(
        isinstance(virtual_size_gib, int)
        and not isinstance(virtual_size_gib, bool)
        and virtual_size_gib > 0,
        "virtual_size_gib must be positive",
    )

    source_url = ""
    local_source = ""
    source_sha256 = select_string(source_sha_override, manifest.get("source_sha256"))
    require(
        SHA_RE.fullmatch(source_sha256) is not None,
        "image policy requires a lowercase source SHA-256 in the manifest or image_factory_source_sha256",
    )
    if source_type == "official-cloud":
        require(
            manifest.get("licensing", {}).get("redistributable") is True,
            "automatic acquisition is limited to redistributable official cloud images",
        )
        source_url = select_string(source_url_override, manifest.get("source_url"))
        parsed = urlparse(source_url)
        require(
            parsed.scheme == "https"
            and bool(parsed.netloc)
            and not parsed.username
            and not parsed.password,
            "official-cloud policy requires a credential-free HTTPS source URL",
        )
        require(not parsed.fragment, "source URL fragments are not allowed")
    else:
        require(source_type == "local", "unexpected source type")
        if operation == "prepare":
            local_source_path = Path(local_source_arg)
            require(local_source_path.is_absolute(), "local import requires an absolute image_factory_local_source")
            local_source = str(local_source_path.resolve(strict=False))
            require(not within(Path(local_source), store), "local source must remain outside the managed image store")
        else:
            require(local_source_arg == "", "validation must not depend on or retain a local source path")

    required_lg = manifest.get("looking_glass_host_build_required")
    observed_lg = select_string(
        looking_glass_observed_override,
        manifest.get("looking_glass_host_build_observed"),
    )
    if required_lg is not None:
        require(
            isinstance(required_lg, str) and LG_BUILD_RE.fullmatch(required_lg) is not None,
            "Looking Glass required build is invalid",
        )
        require(
            observed_lg == required_lg,
            "sealing or validating this image requires matching Looking Glass host-build evidence",
        )
    else:
        require(observed_lg == "", "non-Looking-Glass images must not claim observed host-build evidence")

    effective_policy = dict(manifest)
    effective_policy["source_sha256"] = source_sha256
    if source_type == "official-cloud":
        effective_policy["source_url"] = source_url

    manifest_sha256 = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    cache_path = store / "cache" / f"{image_id}.source"
    base_path = store / "bases" / ("windows" if os_family == "windows" else "linux") / filename
    receipt_path = store / "state" / "images" / f"{image_id}.yml"
    lock_path = store / "state" / "locks" / f"image-{image_id}.lock"
    workshop_policy_path = workshops_root / f"{image_id}.yml" if os_family == "windows" else None
    workshop_receipt_path = (
        store / "state" / "windows-workshops" / f"{image_id}.yml"
        if os_family == "windows"
        else None
    )

    return {
        "schema_version": 1,
        "operation": operation,
        "id": image_id,
        "display_name": manifest.get("display_name"),
        "manifest_path": str(manifest_path),
        "manifest_sha256": manifest_sha256,
        "policy_sha256": policy_sha256(effective_policy),
        "manifest_status": manifest.get("status"),
        "manifest_artifact_sha256": manifest.get("sha256"),
        "os_family": os_family,
        "format": "qcow2",
        "virtual_size_gib": virtual_size_gib,
        "source_type": source_type,
        "source_url": source_url or None,
        "source_basename": Path(urlparse(source_url).path).name if source_url else Path(local_source).name,
        "source_sha256": source_sha256,
        "local_source": local_source or None,
        "private": manifest.get("private") is True,
        "redistributable": manifest.get("licensing", {}).get("redistributable") is True,
        "looking_glass_host_build_required": required_lg,
        "looking_glass_host_build_observed": observed_lg or None,
        "windows_workshop_policy_path": str(workshop_policy_path) if workshop_policy_path else None,
        "windows_workshop_receipt_path": str(workshop_receipt_path) if workshop_receipt_path else None,
        "windows_workshop_policy_sha256": None,
        "windows_workshop_receipt_sha256": None,
        "cache_path": str(cache_path),
        "cache_new_path": str(cache_path) + ".new",
        "base_path": str(base_path),
        "base_new_path": str(base_path) + ".new",
        "receipt_path": str(receipt_path),
        "receipt_new_path": str(receipt_path) + ".new",
        "lock_path": str(lock_path),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--store", required=True)
    parser.add_argument("--operation", choices=["prepare", "validate"], required=True)
    parser.add_argument("--source-url", default="")
    parser.add_argument("--source-sha256", default="")
    parser.add_argument("--local-source", default="")
    parser.add_argument("--looking-glass-observed-build", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = build_plan(
            Path(args.root),
            args.manifest,
            Path(args.store),
            args.operation,
            args.source_url,
            args.source_sha256,
            args.local_source,
            args.looking_glass_observed_build,
        )
    except PlanError as exc:
        print(f"image plan refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(plan, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
