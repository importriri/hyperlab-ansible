#!/usr/bin/env python3
"""The Workbench: Golden Image candidates, their capture and generalization.

See docs/adr/0015-golden-image-capture.md. A domain enters the Workbench only
through an explicit adopt; `seal` copies its shut-off disk, generalizes the
copy offline, scans it for leftovers, hashes it and renders an image manifest
for the existing `image_factory` local import. The source disk is only read.

Every write is atomic, every transaction holds one lock, and a failed seal
removes its staging so nothing half-made survives.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = 1
NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
SHA_RE = re.compile(r"^[a-f0-9]{64}$")
STATES = ("candidate", "captured")
PROFILE_NETWORK = {"dev": "dev", "gaming-clean": "clean", "gaming-dirty": "dirty"}

# Generalization of the copy. `user-account` removes every non-root account
# and its home; the deletes cover what the default operations do not.
SYSPREP_ARGS = [
    "--operations", "defaults,user-account",
    "--delete", "/home/*",
    "--delete", "/root/.ssh",
    "--delete", "/root/.gnupg",
    "--delete", "/root/.local/share/keyrings",
    "--delete", "/var/lib/cloud/instance",
    "--delete", "/var/lib/cloud/instances",
    "--delete", "/var/lib/cloud/data",
    "--delete", "/etc/sudoers.d/90-cloud-init-users",
    "--delete", "/var/cache/pacman/pkg/*",
]

# Leftover scan: one guestfish script, one marker per probe. A leading `-`
# lets guestfish continue when a path is absent, which is the good case.
SCAN_PROBES = (
    ("home", "-ls /home"),
    ("root", "-ls /root"),
    ("machine-id", "-cat /etc/machine-id"),
    ("ssh-hostkeys", "glob-expand /etc/ssh/ssh_host_*"),
    ("cloud-instances", "-ls /var/lib/cloud/instances"),
    ("sudoers-cloud-init", "-is-file /etc/sudoers.d/90-cloud-init-users"),
    ("passwd", "-cat /etc/passwd"),
)
ROOT_FORBIDDEN = re.compile(r"^(\.ssh|\.gnupg|\.local|\..*_history|\.netrc|\.git-credentials|\.aws|\.kube|\.docker)$")


class WorkbenchError(Exception):
    """A request or a state that must be refused."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise WorkbenchError(message)


# --------------------------------------------------------------------------
# Registry


def registry_dir(root: Path) -> Path:
    return root / "registry"


def record_path(root: Path, domain: str) -> Path:
    require(bool(NAME_RE.fullmatch(domain)), f"invalid domain name: {domain!r}")
    return registry_dir(root) / f"{domain}.json"


def write_json(path: Path, data: dict[str, Any], mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    except BaseException:
        if os.path.exists(name):
            os.unlink(name)
        raise


def validate_record(data: Any) -> dict[str, Any]:
    require(isinstance(data, dict), "record must be an object")
    require(data.get("schema_version") == SCHEMA_VERSION, "unsupported record version")
    for key in ("domain", "image_id", "base_image"):
        require(isinstance(data.get(key), str) and NAME_RE.fullmatch(data[key]), f"record {key} is invalid")
    require(data.get("profile") in PROFILE_NETWORK, "record profile is invalid")
    require(data.get("state") in STATES, "record state is invalid")
    require(isinstance(data.get("adopted_by"), str) and data["adopted_by"], "record adopted_by is invalid")
    require(isinstance(data.get("adopted_at"), str) and data["adopted_at"], "record adopted_at is invalid")
    if data["state"] == "captured":
        captured = data.get("captured")
        require(isinstance(captured, dict), "a captured record needs its capture evidence")
        require(SHA_RE.fullmatch(str(captured.get("sha256", ""))) is not None, "capture digest is invalid")
        require(isinstance(captured.get("virtual_size_bytes"), int), "capture size is invalid")
    return data


def read_record(root: Path, domain: str) -> dict[str, Any]:
    path = record_path(root, domain)
    require(path.is_file() and not path.is_symlink(), f"{domain} is not in the Workbench")
    try:
        return validate_record(json.loads(path.read_text()))
    except ValueError as error:
        raise WorkbenchError(f"{domain} has an unreadable record: {error}") from None


def list_records(root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    records, errors = [], []
    directory = registry_dir(root)
    if not directory.is_dir():
        return records, errors
    for path in sorted(directory.glob("*.json")):
        try:
            records.append(validate_record(json.loads(path.read_text())))
        except (OSError, ValueError, WorkbenchError) as error:
            errors.append(f"{path.name}: {error}")
    return records, errors


class Lock:
    def __init__(self, root: Path) -> None:
        self.path = root / "workbench.lock"

    def __enter__(self) -> Lock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "w")
        try:
            fcntl.flock(self.handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.handle.close()
            raise WorkbenchError("another Workbench transaction is running") from None
        return self

    def __exit__(self, *_: object) -> None:
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()


# --------------------------------------------------------------------------
# Commands


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def cmd_adopt(args: argparse.Namespace) -> dict[str, Any]:
    root, repo = Path(args.root), Path(args.repo)
    require(NAME_RE.fullmatch(args.domain) is not None, "invalid domain name")
    require(NAME_RE.fullmatch(args.image_id) is not None, "invalid image id")
    require(args.profile in PROFILE_NETWORK, f"profile must be one of {', '.join(PROFILE_NETWORK)}")
    base = repo / "images" / f"{args.base_image}.yml"
    require(base.is_file(), f"base image manifest {base.name} does not exist")
    require(not (repo / "images" / f"{args.image_id}.yml").exists(),
            f"images/{args.image_id}.yml already exists; a sealed image is never replaced, pick a new id")
    with Lock(root):
        path = record_path(root, args.domain)
        require(not path.exists(), f"{args.domain} is already in the Workbench")
        records, _ = list_records(root)
        require(all(item["image_id"] != args.image_id for item in records),
                f"image id {args.image_id} is already taken by another candidate")
        record = {
            "schema_version": SCHEMA_VERSION,
            "domain": args.domain,
            "image_id": args.image_id,
            "base_image": args.base_image,
            "profile": args.profile,
            "state": "candidate",
            "adopted_by": args.by,
            "adopted_at": now(),
        }
        write_json(path, validate_record(record))
    return record


def cmd_release(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root)
    with Lock(root):
        record = read_record(root, args.domain)
        staging = root / "staging" / record["image_id"]
        if staging.exists():
            shutil.rmtree(staging)
        record_path(root, args.domain).unlink()
    return {"domain": args.domain, "released": True}


def cmd_list(args: argparse.Namespace) -> dict[str, Any]:
    records, errors = list_records(Path(args.root))
    return {"candidates": records, "errors": errors}


def cmd_show(args: argparse.Namespace) -> dict[str, Any]:
    return read_record(Path(args.root), args.domain)


def run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(argv, capture_output=True, text=True, check=False, **kwargs)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()[-3:]
        raise WorkbenchError(f"{Path(argv[0]).name} failed: " + " | ".join(detail))
    return result


def domain_disk(domain: str) -> Path:
    state = run(["virsh", "-c", "qemu:///system", "domstate", domain]).stdout.strip()
    require(state == "shut off", f"{domain} must be shut off before capture (it is {state!r})")
    listing = run(["virsh", "-c", "qemu:///system", "domblklist", domain, "--details"]).stdout
    disks = []
    for line in listing.splitlines():
        fields = line.split()
        if len(fields) >= 4 and fields[0] == "file" and fields[1] == "disk":
            disks.append(fields[3])
    require(len(disks) == 1, f"{domain} must have exactly one file disk, found {len(disks)}")
    disk = Path(disks[0])
    require(disk.is_absolute() and disk.is_file(), f"{domain} disk {disk} is not a readable file")
    return disk


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def scan_script() -> str:
    lines = []
    for marker, command in SCAN_PROBES:
        lines.append(f"echo @@{marker}")
        lines.append(command)
    return "\n".join(lines) + "\n"


def evaluate_scan(output: str) -> list[str]:
    """Return every leftover the scan output proves; empty means clean."""
    sections: dict[str, list[str]] = {}
    current = None
    for raw in output.splitlines():
        line = raw.strip()
        if line.startswith("@@"):
            current = line[2:]
            sections[current] = []
        elif current is not None and line:
            sections[current].append(line)
    missing = [marker for marker, _ in SCAN_PROBES if marker not in sections]
    if missing:
        return [f"the scan did not run completely (missing {', '.join(missing)})"]

    problems = []
    if sections["home"]:
        problems.append("home directories remain: " + ", ".join(sections["home"]))
    for entry in sections["root"]:
        if ROOT_FORBIDDEN.match(entry):
            problems.append(f"/root/{entry} remains")
    machine_id = [line for line in sections["machine-id"] if line != "uninitialized"]
    if machine_id:
        problems.append("/etc/machine-id is not empty")
    if sections["ssh-hostkeys"]:
        problems.append("SSH host keys remain: " + ", ".join(sections["ssh-hostkeys"]))
    if sections["cloud-instances"]:
        problems.append("cloud-init instance state remains")
    if sections["sudoers-cloud-init"] == ["true"]:
        problems.append("/etc/sudoers.d/90-cloud-init-users remains")
    for entry in sections["passwd"]:
        fields = entry.split(":")
        if len(fields) >= 3 and fields[2].isdigit():
            uid = int(fields[2])
            if 1000 <= uid < 60000:
                problems.append(f"user account {fields[0]} (uid {uid}) remains")
    return problems


def render_manifest(repo: Path, record: dict[str, Any], sha256: str, virtual_size_bytes: int) -> str:
    base = yaml.safe_load((repo / "images" / f"{record['base_image']}.yml").read_text())
    network = PROFILE_NETWORK[record["profile"]]
    size_gib = max(1, math.ceil(virtual_size_bytes / (1024 ** 3)))
    version = record["image_id"].rsplit("-", 1)[-1] if record["image_id"][-8:].isdigit() else now()[:10]
    manifest = {
        "schema_version": 1,
        "id": record["image_id"],
        "display_name": f"HyperLab {record['profile']} workstation",
        "os_family": base["os_family"],
        "os_variant": base["os_variant"],
        "version": version,
        "format": "qcow2",
        "status": "not-built",
        "sha256": None,
        "private": True,
        "contains_personal_data": False,
        "generalized": True,
        "instance_policy": "multiple",
        "source_type": "local",
        "source_url": None,
        "source_checksum_url": None,
        "source_sha256": sha256,
        "filename": f"{record['image_id']}.qcow2",
        "virtual_size_gib": size_gib,
        "minimum_size_gib": size_gib,
        "min_memory_mb": max(int(base.get("min_memory_mb", 2048)), 4096),
        "supports": base["supports"],
        "requires": base["requires"],
        "defaults": {
            "lifecycle": "permanent",
            "device_profile": base["defaults"]["device_profile"],
            "network_profile": network,
        },
        "network_allowlist": [network],
        "licensing": {"redistributable": False},
        "looking_glass_host_build_required": None,
        "looking_glass_host_build_observed": None,
        "notes": (
            f"Captured through the Workbench from {record['domain']} "
            f"({record['profile']} profile) over the {record['base_image']} base. "
            "Generalized offline with virt-sysprep: no user account, home "
            "directory, SSH key, machine identity, history or cloud-init "
            "instance; the leftover scan passed. Machines from this image get "
            "their account from cloud-init and their rice from the profile "
            "playbook."
        ),
    }
    return "---\n" + yaml.safe_dump(manifest, sort_keys=False, default_flow_style=None)


def cmd_seal(args: argparse.Namespace) -> dict[str, Any]:
    root, repo = Path(args.root), Path(args.repo)
    with Lock(root):
        record = read_record(root, args.domain)
        require(record["state"] == "candidate", f"{args.domain} is already captured; release it first")
        source = domain_disk(args.domain)
        staging = root / "staging" / record["image_id"]
        require(not staging.exists(), f"stale staging {staging} exists; release and adopt again")
        staging.mkdir(parents=True, mode=0o700)
        image = staging / f"{record['image_id']}.qcow2"
        try:
            partial = staging / f"{record['image_id']}.qcow2.new"
            run(["qemu-img", "convert", "-O", "qcow2", str(source), str(partial)])
            run(["virt-sysprep", "-a", str(partial), "--format", "qcow2", *SYSPREP_ARGS])
            scan = run(["guestfish", "--ro", "-a", str(partial), "-i"], input=scan_script())
            problems = evaluate_scan(scan.stdout)
            require(not problems, "the generalized image still holds: " + "; ".join(problems))
            run(["qemu-img", "check", str(partial)])
            info = json.loads(run(["qemu-img", "info", "--output=json", str(partial)]).stdout)
            require(info.get("format") == "qcow2" and not info.get("backing-filename"),
                    "the captured image must be a standalone qcow2")
            os.replace(partial, image)
            os.chmod(image, 0o600)
            digest = sha256_file(image)
            size = int(info["virtual-size"])
            manifest = render_manifest(repo, record, digest, size)
            (staging / "manifest.yml").write_text(manifest)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        record["state"] = "captured"
        record["captured"] = {
            "sha256": digest,
            "virtual_size_bytes": size,
            "staged_image": str(image),
            "captured_at": now(),
        }
        write_json(record_path(root, args.domain), validate_record(record))
    return {
        "domain": args.domain,
        "image_id": record["image_id"],
        "staged_image": str(image),
        "sha256": digest,
        "manifest": str(staging / "manifest.yml"),
    }


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="workbench", description=__doc__.splitlines()[0])
    root.add_argument("--root", default="/var/lib/hyperlab-workbench")
    commands = root.add_subparsers(dest="command", required=True)

    adopt = commands.add_parser("adopt")
    adopt.add_argument("--repo", required=True)
    adopt.add_argument("--domain", required=True)
    adopt.add_argument("--image-id", required=True)
    adopt.add_argument("--base-image", required=True)
    adopt.add_argument("--profile", required=True)
    adopt.add_argument("--by", required=True)
    adopt.set_defaults(handler=cmd_adopt)

    seal = commands.add_parser("seal")
    seal.add_argument("--repo", required=True)
    seal.add_argument("--domain", required=True)
    seal.set_defaults(handler=cmd_seal)

    for name, handler in (("release", cmd_release), ("show", cmd_show)):
        sub = commands.add_parser(name)
        sub.add_argument("--domain", required=True)
        sub.set_defaults(handler=handler)

    commands.add_parser("list").set_defaults(handler=cmd_list)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = args.handler(args)
    except (WorkbenchError, OSError, KeyError, ValueError) as error:
        print(f"workbench: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
