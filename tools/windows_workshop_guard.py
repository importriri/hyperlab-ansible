#!/usr/bin/env python3
"""Verify a committed Windows workshop receipt against current policy and source."""
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


class GuardError(ValueError):
    """The Windows workshop receipt is missing, unsafe or stale."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise GuardError(message)


def regular_file(path: Path, label: str) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError as exc:
        raise GuardError(f"{label} does not exist: {path}") from exc
    except OSError as exc:
        raise GuardError(f"{label} cannot be inspected: {exc}") from exc
    require(stat.S_ISREG(info.st_mode) and not stat.S_ISLNK(info.st_mode),
            f"{label} must be one regular non-symlink file: {path}")
    require(path.resolve(strict=True) == path.absolute(), f"{label} path is redirected: {path}")


def load_yaml(path: Path, label: str) -> dict[str, Any]:
    regular_file(path, label)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise GuardError(f"{label} cannot be read as YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise GuardError(f"{label} root must be a mapping")
    return data


def canonical_hash(value: dict[str, Any]) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify(
    policy_path: Path,
    receipt_path: Path,
    image_id: str,
    source_sha256: str,
    looking_glass_build: str,
) -> dict[str, Any]:
    require(SHA_RE.fullmatch(source_sha256) is not None, "source SHA-256 is invalid")
    require(BUILD_RE.fullmatch(looking_glass_build) is not None, "Looking Glass build is invalid")
    policy = load_yaml(policy_path, "Windows workshop policy")
    receipt = load_yaml(receipt_path, "Windows workshop receipt")
    require(policy.get("id") == image_id and policy.get("image") == image_id,
            "Windows workshop policy identity differs from the image")
    require(receipt.get("schema_version") == 1, "unsupported Windows workshop receipt schema")
    require(receipt.get("id") == image_id and receipt.get("image") == image_id,
            "Windows workshop receipt identity differs from the image")
    require(receipt.get("policy_sha256") == canonical_hash(policy),
            "Windows workshop receipt policy hash is stale")
    require(receipt.get("source_sha256") == source_sha256,
            "Windows workshop receipt source checksum differs from the selected qcow2")
    require(receipt.get("looking_glass_build") == looking_glass_build,
            "Windows workshop receipt Looking Glass build differs from the host contract")
    require(receipt.get("private") is True, "Windows workshop receipt must remain private")
    require(receipt.get("ready") is True, "Windows workshop receipt is not ready for sealing")
    require(receipt.get("capture_interface") == "D12",
            "Windows workshop receipt did not validate the D12 capture path")
    expected_setup_state = policy.get("setup_image_state")
    require(receipt.get("setup_image_state") == expected_setup_state,
            "Windows workshop receipt setup state differs from current policy")
    display = receipt.get("virtual_display")
    require(isinstance(display, dict) and display.get("width") == 1920 and display.get("height") == 1080,
            "Windows workshop receipt virtual display differs from 1920x1080")
    forbidden = {"local_source", "source_path", "evidence_path", "username", "email"}
    require(not (forbidden & set(receipt)),
            f"Windows workshop receipt contains forbidden private fields: {sorted(forbidden & set(receipt))}")
    return {
        "id": image_id,
        "policy_sha256": receipt.get("policy_sha256"),
        "receipt_sha256": sha256_file(receipt_path),
        "source_sha256": source_sha256,
        "looking_glass_build": looking_glass_build,
        "ready": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--looking-glass-build", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = verify(
            Path(args.policy),
            Path(args.receipt),
            args.image,
            args.source_sha256,
            args.looking_glass_build,
        )
    except (OSError, GuardError) as exc:
        print(f"Windows workshop guard refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
