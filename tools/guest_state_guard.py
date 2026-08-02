#!/usr/bin/env python3
"""Reject singleton, UUID and MAC collisions in committed M3 state records."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml

MAC_RE = re.compile(r"^52:54:00(?::[0-9a-f]{2}){3}$")


class StateError(ValueError):
    """The state registry cannot safely accept the selected plan."""


def load_state(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise StateError(f"state entry is not a regular file: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise StateError(f"cannot parse {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise StateError(f"state root must be a mapping: {path}")
    required = {"schema_version", "name", "uuid", "mac", "image", "instance_policy"}
    missing = sorted(required - set(data))
    if missing:
        raise StateError(f"state entry {path} is missing {', '.join(missing)}")
    if data["schema_version"] != 1:
        raise StateError(f"unsupported state schema in {path}")
    if path.stem != data["name"]:
        raise StateError(f"state filename/name mismatch in {path}")
    if not isinstance(data["mac"], str) or MAC_RE.fullmatch(data["mac"]) is None:
        raise StateError(f"invalid managed MAC in {path}")
    if data["instance_policy"] not in {"multiple", "singleton"}:
        raise StateError(f"invalid instance_policy in {path}")
    return data


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-root", required=True)
    args = parser.parse_args()
    try:
        plan = json.load(sys.stdin)
        if not isinstance(plan, dict):
            raise StateError("plan JSON root must be a mapping")
        required_plan = {"name", "uuid", "mac", "image", "instance_policy"}
        missing_plan = sorted(required_plan - set(plan))
        if missing_plan:
            raise StateError(f"plan is missing {', '.join(missing_plan)}")
        state_root = Path(args.state_root)
        if state_root.is_symlink():
            raise StateError(f"state root must not be a symlink: {state_root}")
        if state_root.exists() and not state_root.is_dir():
            raise StateError(f"state root is not a directory: {state_root}")
        records = [] if not state_root.exists() else [
            load_state(path) for path in sorted(state_root.glob("*.yml"))
        ]

        seen_uuid: dict[str, str] = {}
        seen_mac: dict[str, str] = {}
        singleton_images: dict[str, str] = {}
        for state in records:
            name = str(state["name"])
            uuid_value = str(state["uuid"])
            mac = str(state["mac"])
            image = str(state["image"])
            if uuid_value in seen_uuid and seen_uuid[uuid_value] != name:
                raise StateError(f"UUID collision between {seen_uuid[uuid_value]} and {name}")
            if mac in seen_mac and seen_mac[mac] != name:
                raise StateError(f"MAC collision between {seen_mac[mac]} and {name}")
            seen_uuid[uuid_value] = name
            seen_mac[mac] = name
            if state["instance_policy"] == "singleton":
                if image in singleton_images and singleton_images[image] != name:
                    raise StateError(f"singleton image {image} is already used by {singleton_images[image]}")
                singleton_images[image] = name

        name = str(plan.get("name", ""))
        if name in {state["name"] for state in records}:
            raise StateError(f"state for {name} already exists outside a complete transaction")
        if plan.get("uuid") in seen_uuid:
            raise StateError(f"planned UUID collides with {seen_uuid[str(plan['uuid'])]}")
        if plan.get("mac") in seen_mac:
            raise StateError(f"planned MAC collides with {seen_mac[str(plan['mac'])]}")
        if plan.get("instance_policy") == "singleton" and plan.get("image") in singleton_images:
            raise StateError(
                f"singleton image {plan['image']} is already used by {singleton_images[str(plan['image'])]}"
            )
    except (OSError, json.JSONDecodeError, StateError) as exc:
        print(f"guest state refused: {exc}", file=sys.stderr)
        return 2

    print(json.dumps({"records": len(records), "status": "safe"}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
