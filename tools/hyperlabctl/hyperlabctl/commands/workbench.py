"""The Workbench of Golden Image candidates, read-only.

Adoption, seal and release are privileged playbooks
(docs/adr/0015-golden-image-capture.md). This command only reads the
root-owned registry, so the shell can show the Workbench without privilege.
A record that does not validate is reported, never shown as a candidate.
"""

import json
import os
import re
from pathlib import Path

from ..render import paint
from .base import Command

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SHA_RE = re.compile(r"^[a-f0-9]{64}$")
STATES = ("candidate", "captured")
PROFILES = ("dev", "gaming-clean", "gaming-dirty")
MAX_RECORD_BYTES = 64 * 1024


def workbench_root():
    return Path(os.environ.get("HYPERLAB_WORKBENCH_ROOT") or "/var/lib/hyperlab-workbench")


def _row(data):
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        raise ValueError("unsupported record")
    for key in ("domain", "image_id", "base_image"):
        if not isinstance(data.get(key), str) or not NAME_RE.fullmatch(data[key]):
            raise ValueError("invalid %s" % key)
    if data.get("state") not in STATES or data.get("profile") not in PROFILES:
        raise ValueError("invalid state or profile")
    captured = data.get("captured") if data["state"] == "captured" else None
    if data["state"] == "captured":
        if not isinstance(captured, dict) or not SHA_RE.fullmatch(str(captured.get("sha256", ""))):
            raise ValueError("captured without a digest")
    return {
        "domain": data["domain"],
        "image_id": data["image_id"],
        "base_image": data["base_image"],
        "profile": data["profile"],
        "state": data["state"],
        "adopted_at": str(data.get("adopted_at", "")),
        "sha256": captured["sha256"] if captured else None,
    }


def read_workbench(root=None):
    directory = (root or workbench_root()) / "registry"
    payload = {"available": directory.is_dir(), "candidates": [], "errors": []}
    if not payload["available"]:
        return payload
    for path in sorted(directory.glob("*.json")):
        try:
            if path.is_symlink() or path.stat().st_size > MAX_RECORD_BYTES:
                raise ValueError("not a plain record")
            row = _row(json.loads(path.read_text()))
            if row["domain"] != path.stem:
                raise ValueError("record does not match its file name")
            payload["candidates"].append(row)
        except (OSError, ValueError) as error:
            payload["errors"].append("%s: %s" % (path.name, error))
    return payload


class WorkbenchCommand(Command):
    name = "workbench"
    help = "Golden Image candidates (read-only)"
    order = 29

    def configure(self, parser):
        sub = parser.add_subparsers(dest="workbench_action", required=True)
        sub.add_parser("list")

    def run(self, args, ctx):
        payload = read_workbench()
        if args.json:
            print(json.dumps(payload, indent=2))
            return 0
        if not payload["available"]:
            print("The Workbench is empty: adopt a domain with playbooks/workbench-adopt.yml")
            return 0
        for row in payload["candidates"]:
            colour = "ok" if row["state"] == "captured" else "warn"
            print("  %-22s %-10s -> %-28s %s" % (
                row["domain"], paint(row["state"], colour, args.color),
                row["image_id"], row["profile"]))
        for error in payload["errors"]:
            print("  refused record  %s" % error)
        return 0
