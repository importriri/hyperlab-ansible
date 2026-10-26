"""What the shell may offer when it creates a Machine, and how it is provisioned.

The creation plan is computed by the same factory code that writes the
Machine record, so the shell only shows limits the factory enforces. The
provisioning steps are the documented commands of docs/first-machine.md,
derived from one Machine record and its projected VM spec; the reviewed
provisioner runs them, never anything a caller supplies. See ADR 0017.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .errors import ContractError, Unavailable
from .machine_factory import (
    MACHINE_ID_RE,
    _image,
    _repo_root,
    _resource_values,
    custom_limits,
    os_label,
    project_vm_spec,
    read_generated_spec,
    template_catalog,
)
from .machine_registry import read_machine

# The one guest key of this host. Only the public half is ever read.
GUEST_KEY = Path(".ssh/hyperlab_ed25519.pub")
GUEST_KEY_LIMIT = 4096
KEY_RE = re.compile(r"^ssh-ed25519 (AAAAC3NzaC1lZDI1NTE5[A-Za-z0-9+/]+={0,2})(?: [^\r\n]*)?$")
# A key type is named in a refusal only when it looks like one.
KEY_TYPE_RE = re.compile(r"^[a-z0-9][a-z0-9@.-]{0,63}$")

# Reviewed profile playbooks. A Template whose workspace is not a server must
# have one here, or it is not offered for creation.
SERVER_WORKSPACE = "server"
PROFILE_PLAYBOOKS = {
    "workstation-dev": "playbooks/guest-arch-dev-vfio.yml",
    "workstation-dev-standard": "playbooks/guest-arch-dev.yml",
    "gaming-clean": "playbooks/guest-arch-gaming-clean.yml",
    "gaming-dirty": "playbooks/guest-arch-gaming-dirty.yml",
}

# Placeholder for the private hash file; the provisioner substitutes it.
ACCESS_FILE = "{access_file}"


def guest_key(home: Path) -> dict[str, str]:
    """Validate the host's guest key; return its key line and fingerprint.

    Every refusal names what is wrong and never repeats the file's content.
    """
    path = Path(home) / GUEST_KEY
    if path.is_symlink():
        raise Unavailable(f"the guest key ~/{GUEST_KEY} is a symbolic link")
    if not path.is_file():
        raise Unavailable(f"the guest key ~/{GUEST_KEY} is missing")
    data = path.read_bytes()
    if len(data) > GUEST_KEY_LIMIT:
        raise ContractError(f"~/{GUEST_KEY} is too large to be one public key")
    text = data.decode("ascii", "replace")
    if "PRIVATE KEY" in text:
        raise ContractError(f"~/{GUEST_KEY} holds a private key; it must hold the public one")
    # Physical lines, blank ones included; only the final newline is not a line.
    lines = text.removesuffix("\n").split("\n")
    if not text.strip():
        raise ContractError(f"~/{GUEST_KEY} is empty")
    if len(lines) > 1:
        raise ContractError(f"~/{GUEST_KEY} holds {len(lines)} lines; it must hold exactly one public key")
    lines = [lines[0].strip()]
    kind = lines[0].split()[0]
    if kind != "ssh-ed25519":
        named = kind if KEY_TYPE_RE.fullmatch(kind) else "an unknown type"
        raise ContractError(f"~/{GUEST_KEY} is not an ed25519 key ({named})")
    match = KEY_RE.fullmatch(lines[0])
    if match is None:
        raise ContractError(f"~/{GUEST_KEY} is not one ssh-ed25519 public key line")
    try:
        blob = base64.b64decode(match.group(1), validate=True)
    except binascii.Error as exc:
        raise ContractError(f"~/{GUEST_KEY} is not valid base64") from exc
    if len(blob) != 51 or blob[4:15] != b"ssh-ed25519" or blob[15:19] != b"\x00\x00\x00\x20":
        raise ContractError(f"~/{GUEST_KEY} has the wrong ed25519 shape")
    fingerprint = base64.b64encode(hashlib.sha256(blob).digest()).decode().rstrip("=")
    # The comment stays on the host: the guest gets type and key only.
    return {"path": f"~/{GUEST_KEY}", "line": f"ssh-ed25519 {match.group(1)}",
            "fingerprint": f"SHA256:{fingerprint}"}


def _provision(template_id: str, workspace: str) -> dict[str, Any]:
    if workspace == SERVER_WORKSPACE:
        return {"profile_playbook": None, "password": False}
    playbook = PROFILE_PLAYBOOKS.get(template_id)
    if playbook is None:
        return {"profile_playbook": None, "password": False,
                "blocked_reason": "no reviewed profile playbook for this Template"}
    return {"profile_playbook": playbook, "password": True}


def creation_plan(repo_root: Path | str, *, home: Path, cpu_count: int) -> dict[str, Any]:
    root = _repo_root(repo_root)
    if not isinstance(cpu_count, int) or cpu_count < 1:
        raise Unavailable("the host CPU count is unknown")

    try:
        key = guest_key(home)
        key_entry = {"available": True, "path": key["path"], "fingerprint": key["fingerprint"],
                     "reason": ""}
    except (Unavailable, ContractError, OSError) as exc:
        key_entry = {"available": False, "path": f"~/{GUEST_KEY}", "fingerprint": None,
                     "reason": str(exc)}

    templates = []
    for entry in template_catalog(root):
        if not entry["ready"]:
            continue
        image = _image(root, entry["image"]["id"])
        profiles = {}
        for profile in entry["resource_profiles"]:
            if profile != "custom":
                profiles[profile] = _resource_values(image, profile, memory_mb=None,
                                                     vcpus=None, disk_gib=None)
        custom = None
        if "custom" in entry["resource_profiles"]:
            # The same bounds the factory holds a custom request to.
            custom = custom_limits(image, cpu_count=cpu_count)
        provision = _provision(entry["id"], entry["presentation"]["workspace_profile"])
        blocked = provision.pop("blocked_reason", None)
        if blocked is None and not key_entry["available"]:
            blocked = key_entry["reason"]
        templates.append({
            "id": entry["id"],
            "display_name": entry["display_name"],
            "version": entry["version"],
            "image": entry["image"]["id"],
            # The same label the Machine cards show, from the manifest.
            "os": os_label(image),
            "lifecycles": entry["lifecycles"],
            "default_lifecycle": entry["defaults"]["lifecycle"],
            "device_capability": entry["defaults"]["device_capability"],
            "network_profiles": entry["network_profiles"],
            "default_network": entry["defaults"]["network_profile"],
            "resource_profiles": entry["resource_profiles"],
            "default_resource_profile": entry["defaults"]["resource_profile"],
            "profiles": profiles,
            "custom": custom,
            "looking_glass_mode": entry["presentation"]["looking_glass_mode"],
            "provision": provision,
            "creatable": blocked is None,
            "blocked_reason": blocked or "",
        })

    return {
        "schema": 1,
        "machine_id_pattern": MACHINE_ID_RE.pattern,
        "host": {"vcpus": cpu_count},
        "guest_key": key_entry,
        "templates": templates,
    }


def provision_steps(repo_root: Path | str, machine_id: str, *, home: Path,
                    runtime_dir: Path, state_home: Path | None = None) -> dict[str, Any]:
    """The documented commands for one created and projected Machine."""
    root = _repo_root(repo_root)
    if not isinstance(machine_id, str) or MACHINE_ID_RE.fullmatch(machine_id) is None:
        raise ContractError("invalid Machine id")
    record = read_machine(machine_id, state_home=state_home)
    spec = f"vm-specs/.generated/{machine_id}.yml"
    # The record is the authority and the spec only its projection: what
    # stands there must be exactly what the record projects to now. A link,
    # an unreadable or malformed file, or one edited by hand is refused
    # before any step, like a missing one.
    stored = read_generated_spec(root, machine_id)
    if stored is None:
        raise Unavailable(f"{machine_id} is not projected; run hyperlabctl machine project first")
    if stored != project_vm_spec(root, record):
        raise ContractError(f"{spec} differs from the projection of the Machine record {machine_id}")
    provision = _provision(record["template"]["id"], record["presentation"]["workspace_profile"])
    if "blocked_reason" in provision:
        raise ContractError(provision["blocked_reason"])
    key = guest_key(home)
    runtime = Path(runtime_dir)
    if not runtime.is_absolute():
        raise ContractError("the runtime directory must be absolute")
    inventory = str(runtime / f"{machine_id}.ini")

    steps = [
        {"id": "create-domain", "label": "Create and start the domain",
         "password": False,
         "argv": ["ansible-playbook", "playbooks/vm-create.yml", "-K",
                  "-e", f"guest_spec={spec}", "-e", "guest_start_after_create=true",
                  "-e", json.dumps({"guest_cloud_init_ssh_public_keys": [key["line"]]},
                                   separators=(",", ":"))]},
        {"id": "inventory", "label": "Publish the inventory and pin the SSH host key",
         "password": False,
         "argv": ["ansible-playbook", "playbooks/vm-guest-inventory.yml", "-K",
                  "-e", f"guest_spec={spec}"]},
    ]
    playbook = provision["profile_playbook"]
    if playbook is not None:
        profile = ["ansible-playbook", "-i", "inventory.ini", "-i", inventory, playbook]
        steps.append({"id": "profile-first", "label": "Apply the profile and set the password",
                      "password": True, "argv": [*profile, "-e", "@" + ACCESS_FILE]})
        steps.append({"id": "profile-second", "label": "Apply the profile again (expect no changes)",
                      "password": False, "argv": profile})
    # Last, once the host key is pinned and the profile has run: restrict the
    # guest agent, and end passwordless sudo when the account has a password.
    steps.append({"id": "close-access",
                  "label": "Restrict the guest agent and end passwordless sudo",
                  "password": False,
                  "argv": ["ansible-playbook", "-i", "inventory.ini", "-i", inventory,
                           "playbooks/guest-close-access.yml"]})
    return {"schema": 1, "machine": machine_id, "spec": spec, "steps": steps}
