#!/usr/bin/env python3
"""The creation plan agrees with the factory, and a refused creation leaves nothing (ADR 0017).

The shell offers what `hyperlabctl machine create-plan` reports and submits
it through `privatestack-machine-actions create`. This contract holds both
halves to the factory that writes the Machine record:

  * every profile value in the plan equals the resources of the record that
    `machine create` writes for it, and every custom limit is exactly where
    the factory starts refusing;
  * the guest key is one public ed25519 line, refused with a named reason
    otherwise, and the private key beside it is never opened;
  * the real bridge over the real CLI records and projects a Machine in one
    staged `machine create --project`, and every refusal (a name in use, a
    stale spec, a link or a directory where the spec goes, an unreadable
    libvirt list) leaves the registry and the generated specs as they were;
  * a failure at the real publication or after it (the directory sync,
    the read-back, the digest, a digest of other bytes, a cancellation
    right after os.link, at the inspection or at the sync) undoes the
    record and then the spec under
    the lock, and an undo that cannot finish says so and keeps what is not
    this creation's, and the spec while the record stays;
  * `machine withdraw` removes only the record whose digest it is given, and
    keeps it while its projection exists, while a libvirt domain has its
    name or the domain list cannot be read, while the registry is locked,
    and while the spec where its projection goes cannot be read as one YAML
    mapping.

The plan's shape and the provisioning steps are held by
`c10_machine_creation_plan_contract.py`. Everything here runs in a temporary
checkout, HOME and XDG_STATE_HOME; the operation runner is a recorder and
virsh a stub.
"""

from __future__ import annotations

import base64
import fcntl
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/hyperlabctl/bin/hyperlabctl"
BRIDGE = ROOT / "roles/host_desktop_common/files/privatestack-machine-actions.py"
sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))

from hyperlabctl.errors import ContractError, Unavailable  # noqa: E402
from hyperlabctl.machine_factory import template_catalog  # noqa: E402
from hyperlabctl.machine_provision import creation_plan, guest_key  # noqa: E402

KEY_RAW = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(32))
KEY_BLOB = base64.b64encode(KEY_RAW).decode()
# What `ssh-keygen -lf` prints for this key, computed here and never by
# the helper under test: unpadded base64 of the SHA-256 of the blob.
KEY_FINGERPRINT = "SHA256:" + base64.b64encode(hashlib.sha256(KEY_RAW).digest()).decode().rstrip("=")
KEY_LINE = f"ssh-ed25519 {KEY_BLOB} sid@nitro"
PRIVATE = "-----BEGIN OPENSSH PRIVATE KEY-----\nb3BlbnNzaC1rZXktdjEAAAAA\n-----END OPENSSH PRIVATE KEY-----\n"


# Installed in the CLI's own process by the wrapper while fault.json exists.
# Every fault strikes the real code at a real system call or at the call
# after it; nothing replaces the publication itself. The log records what
# the fault saw, so a case proves the record had been published by the real
# os.link before the failure, and that every removal ran under the lock.
FAULTS = """
import errno, fcntl, json, os, pathlib

from hyperlabctl import machine_registry
from hyperlabctl.commands import machine as command
from hyperlabctl.errors import Unavailable


def install(config_path):
    config = json.loads(config_path.read_text())
    faults = set(config["faults"])
    registry = pathlib.Path(config["registry"])
    specs = pathlib.Path(config["specs"])
    record = registry / (config["name"] + ".yml")
    spec = specs / (config["name"] + ".yml")
    log = pathlib.Path(config["log"])
    fired = set()

    def note(event):
        with log.open("a") as handle:
            handle.write(event + "\\n")

    def once(fault):
        if fault in faults and fault not in fired:
            fired.add(fault)
            note(fault + (" with the record published" if record.is_file() else " with no record"))
            return True
        return False

    def lock_held():
        try:
            descriptor = os.open(registry / ".lock", os.O_RDWR | os.O_CLOEXEC)
        except FileNotFoundError:
            return False
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        finally:
            os.close(descriptor)
        return False

    def replace(path, data=b"replaced: true\\n"):
        other = path.with_name(".replacement")
        other.write_bytes(data)
        other.chmod(0o600)
        os.replace(other, path)

    real_fsync = machine_registry._fsync_directory

    def fsync(directory):
        if record.is_file() and once("interrupt-fsync"):
            raise KeyboardInterrupt
        if record.is_file() and once("fsync"):
            if once("replace-record"):
                replace(record)
            if once("rewrite-record"):
                # The same file, its bytes changed in place.
                record.write_bytes(b"rewritten: true\\n")
            if once("copy-record"):
                # Another file with the very same bytes is still not this one.
                replace(record, record.read_bytes())
            if once("replace-spec"):
                replace(spec)
            raise OSError(errno.EIO, "injected directory fsync failure")
        if fired and once("fsync-again"):
            raise OSError(errno.EIO, "injected second directory fsync failure")
        return real_fsync(directory)

    machine_registry._fsync_directory = fsync

    real_inspect = machine_registry._inspect_record_file

    def inspect(path, *args, **kwargs):
        if pathlib.Path(path) == record and record.is_file() and once("interrupt-inspect"):
            raise KeyboardInterrupt
        return real_inspect(path, *args, **kwargs)

    machine_registry._inspect_record_file = inspect

    real_read = command.read_machine

    def read(*args, **kwargs):
        if record.is_file() and once("read"):
            raise Unavailable("injected record read failure")
        return real_read(*args, **kwargs)

    command.read_machine = read

    real_digest = command.record_sha256

    def digest(*args, **kwargs):
        if record.is_file() and once("digest"):
            raise Unavailable("injected record digest failure")
        if record.is_file() and once("wrong-digest"):
            # A well-formed digest of other bytes.
            return "0" * 64
        return real_digest(*args, **kwargs)

    command.record_sha256 = digest

    real_link = os.link

    def link(source, destination, *args, **kwargs):
        if pathlib.Path(destination) == record and once("link"):
            raise OSError(errno.EIO, "injected link failure")
        if pathlib.Path(destination) == record and "interrupt-after-link" in faults:
            real_link(source, destination, *args, **kwargs)
            once("interrupt-after-link")
            raise KeyboardInterrupt
        return real_link(source, destination, *args, **kwargs)

    os.link = link

    real_unlink = os.unlink

    def unlink(path, *args, **kwargs):
        target = pathlib.Path(os.fsdecode(path))
        if target.parent in (registry, specs):
            if not lock_held():
                note("unlink without the lock: " + target.name)
            if target == record and once("unlink-record"):
                raise OSError(errno.EACCES, "injected record unlink failure")
            if target == spec and once("unlink-spec"):
                raise OSError(errno.EACCES, "injected spec unlink failure")
        return real_unlink(path, *args, **kwargs)

    os.unlink = unlink
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class Lab:
    """A temporary checkout, home and state home, with the real CLI over them."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.repo = root / "repo"
        for name in ("images", "templates"):
            shutil.copytree(ROOT / name, self.repo / name)
        for path in (self.repo / "templates").glob("*.md"):
            path.unlink()
        (self.repo / "vm-specs").mkdir()
        self.home = root / "home"
        (self.home / ".ssh").mkdir(parents=True)
        (self.home / ".ssh/hyperlab_ed25519.pub").write_text(KEY_LINE + "\n")
        (self.home / ".ssh/hyperlab_ed25519").write_text(PRIVATE)
        self.state = root / "state"
        self.env = {**os.environ, "HOME": str(self.home), "XDG_STATE_HOME": str(self.state),
                    "PYTHONDONTWRITEBYTECODE": "1"}
        # The CLI's virsh is a stub that lists the names in `domains`, or
        # fails while `virsh-fails` exists; the host's libvirt is never asked.
        self.domains = root / "domains"
        self.domains.write_text("")
        self.virsh_fails = root / "virsh-fails"
        virsh = root / "virsh"
        virsh.write_text(
            f"#!{sys.executable}\n"
            "import pathlib, sys\n"
            f"if pathlib.Path({str(self.virsh_fails)!r}).exists():\n"
            "    sys.exit('error: failed to connect to the hypervisor')\n"
            "if sys.argv[1:] != ['-c', 'qemu:///system', '-q', 'list', '--all', '--name']:\n"
            "    sys.exit('unexpected virsh call: %r' % sys.argv[1:])\n"
            f"sys.stdout.write(pathlib.Path({str(self.domains)!r}).read_text())\n")
        virsh.chmod(0o700)
        config = self.home / ".config/hyperlabctl"
        config.mkdir(parents=True)
        (config / "config.yml").write_text(json.dumps({"virsh_bin": str(virsh),
                                                        "libvirt_uri": "qemu:///system"}))

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CLI), "--repo", str(self.repo), "--json", *args],
                              text=True, capture_output=True, check=False, env=self.env)

    def ok(self, *args: str) -> Any:
        result = self.cli(*args)
        require(result.returncode == 0, f"hyperlabctl {' '.join(args)} failed: {result.stderr}")
        return json.loads(result.stdout)

    def wrapper(self) -> Path:
        """An executable that stands where the bridge expects hyperlabctl.

        It runs the real CLI in its own process; while `fault.json` exists it
        first installs the faults that file names (FAULTS below).
        """
        path = self.root / "bin/hyperlabctl"
        if path.exists():
            return path
        path.parent.mkdir()
        (self.root / "faults.py").write_text(FAULTS)
        path.write_text(
            f"#!{sys.executable}\n"
            "import os, pathlib, sys\n"
            f"os.environ.update({{'HOME': {str(self.home)!r}, 'XDG_STATE_HOME': {str(self.state)!r},"
            " 'PYTHONDONTWRITEBYTECODE': '1'})\n"
            "sys.dont_write_bytecode = True\n"
            f"sys.path.insert(0, {str(ROOT / 'tools/hyperlabctl')!r})\n"
            f"config = pathlib.Path({str(self.root / 'fault.json')!r})\n"
            "if config.exists():\n"
            f"    sys.path.insert(0, {str(self.root)!r})\n"
            "    import faults\n"
            "    faults.install(config)\n"
            "from hyperlabctl.cli import main\n"
            f"sys.exit(main(['--repo', {str(self.repo)!r}, *sys.argv[1:]]))\n")
        path.chmod(0o700)
        return path

    def faulty(self, faults: list[str], name: str, *args: str) -> subprocess.CompletedProcess:
        """The real CLI with `faults` installed for Machine `name`."""
        self.arm(faults, name)
        try:
            return subprocess.run([str(self.wrapper()), "--json", *args], text=True,
                                  capture_output=True, check=False, env=self.env)
        finally:
            self.disarm()

    def arm(self, faults: list[str], name: str) -> None:
        self.wrapper()
        self.fault_log.write_text("")
        (self.root / "fault.json").write_text(json.dumps({
            "faults": faults, "name": name, "log": str(self.fault_log),
            "registry": str(self.state / "hyperlab/machines"),
            "specs": str(self.repo / "vm-specs/.generated")}))

    def disarm(self) -> None:
        (self.root / "fault.json").unlink()

    @property
    def fault_log(self) -> Path:
        return self.root / "fault.log"

    def events(self) -> list[str]:
        return self.fault_log.read_text().splitlines()

    def snapshot(self) -> dict[str, Any]:
        """Every path below the state home and the generated specs, with mode and bytes."""
        tree: dict[str, Any] = {}
        for base in (self.state, self.repo / "vm-specs"):
            if not base.exists():
                continue
            for path in sorted(base.rglob("*")):
                info = path.lstat()
                content = None
                if path.is_file() and not path.is_symlink():
                    # A file made unreadable on purpose is held by its size.
                    content = path.read_bytes() if info.st_mode & 0o400 else info.st_size
                tree[str(path.relative_to(self.root))] = (info.st_mode, content)
        return tree

    def records(self) -> list[str]:
        return [row["id"] for row in self.ok("machine", "list")["machines"]]


def check_plan_matches_factory(lab: Lab) -> None:
    plan = lab.ok("machine", "create-plan")
    require(plan["guest_key"]["available"] is True and plan["guest_key"]["fingerprint"] == KEY_FINGERPRINT,
            f"the plan does not report the guest key's fingerprint: {plan['guest_key']}")
    ready = sorted(entry["id"] for entry in template_catalog(lab.repo) if entry["ready"])
    offered = {entry["id"]: entry for entry in plan["templates"]}
    require(sorted(offered) == ready and ready, f"the plan offers {sorted(offered)}, the factory has {ready} ready")

    serial = 0
    for template_id, entry in offered.items():
        named = [profile for profile in entry["resource_profiles"] if profile != "custom"]
        require(sorted(entry["profiles"]) == sorted(named),
                f"{template_id}: the plan resolves {sorted(entry['profiles'])}, the Template allows {named}")
        for profile in named:
            serial += 1
            created = lab.ok("machine", "create", template_id, f"plan-{serial:02d}",
                             "--resource-profile", profile)
            require(entry["profiles"][profile] == created["machine"]["resources"],
                    f"{template_id}/{profile}: the plan differs from the record create writes: "
                    f"{entry['profiles'][profile]} != {created['machine']['resources']}")

        limits = entry["custom"]
        if "custom" not in entry["resource_profiles"]:
            require(limits is None, f"{template_id}: custom limits without the custom profile")
            continue
        low = {"memory_mb": limits["memory_mb_min"], "vcpus": limits["vcpus_min"],
               "disk_gib": limits["disk_gib_min"]}
        for values in (low, {**low, "vcpus": limits["vcpus_max"]}):
            serial += 1
            created = lab.ok("machine", "create", template_id, f"plan-{serial:02d}", "--resource-profile",
                             "custom", "--memory-mb", str(values["memory_mb"]), "--vcpus",
                             str(values["vcpus"]), "--disk-gib", str(values["disk_gib"]))
            require(created["machine"]["resources"] == values,
                    f"{template_id}: the factory changed a custom request at the limits: {created['machine']}")
        for field, below in (("memory_mb", low["memory_mb"] - 1), ("vcpus", low["vcpus"] - 1),
                             ("disk_gib", low["disk_gib"] - 1)):
            values = {**low, field: below}
            before = lab.snapshot()
            result = lab.cli("machine", "create", template_id, "plan-below", "--resource-profile", "custom",
                             "--memory-mb", str(values["memory_mb"]), "--vcpus", str(values["vcpus"]),
                             "--disk-gib", str(values["disk_gib"]))
            require(result.returncode != 0,
                    f"{template_id}: the factory accepted {field}={below}, below the plan's limit")
            require(lab.snapshot() == before, f"{template_id}: a refused create changed the registry")


KEY_CASES: dict[str, tuple[str | None, str]] = {
    "missing": (None, "is missing"),
    "empty": ("", "is empty"),
    "blank": ("\n \n", "is empty"),
    "two keys": (KEY_LINE + "\n" + KEY_LINE + "\n", "holds 2 lines"),
    "leading blank": ("\n" + KEY_LINE + "\n", "holds 2 lines"),
    "trailing blank": (KEY_LINE + "\n\n", "holds 2 lines"),
    "no final newline": (KEY_LINE + "\n" + KEY_LINE, "holds 2 lines"),
    "rsa": ("ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ== x\n", "not an ed25519 key (ssh-rsa)"),
    "security key": ("sk-ssh-ed25519@openssh.com AAAAGnNrLXNzaC1lZDI1NTE5QG9wZW5zc2guY29t x\n",
                     "not an ed25519 key (sk-ssh-ed25519@openssh.com)"),
    "private": (PRIVATE, "holds a private key"),
    "short": ("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIA== x\n", "wrong ed25519 shape"),
    "garbage": ("ssh-ed25519 not*base64\n", "not one ssh-ed25519 public key line"),
    "huge": ("ssh-ed25519 " + "A" * 5000 + "\n", "too large"),
}


def check_key_refusals(lab: Lab) -> None:
    opened: list[str] = []
    watching = [False]

    def audit(event: str, args: tuple) -> None:
        if watching[0] and event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            opened.append(os.fsdecode(args[0]))

    def watched(call):
        watching[0] = True
        try:
            return call()
        finally:
            watching[0] = False

    sys.addaudithook(audit)
    try:
        key = watched(lambda: guest_key(lab.home))
        require(key["fingerprint"] == KEY_FINGERPRINT and key["line"] == f"ssh-ed25519 {KEY_BLOB}",
                f"a valid guest key was not accepted: {key}")
        bare = lab.root / "key-without-newline"
        (bare / ".ssh").mkdir(parents=True)
        (bare / ".ssh/hyperlab_ed25519.pub").write_text(KEY_LINE)
        require(watched(lambda: guest_key(bare)) == key, "a key line without its final newline was refused")
        for label, (content, reason) in KEY_CASES.items():
            home = lab.root / ("key-" + label.replace(" ", "-"))
            (home / ".ssh").mkdir(parents=True)
            (home / ".ssh/hyperlab_ed25519").write_text(PRIVATE)
            if content is not None:
                (home / ".ssh/hyperlab_ed25519.pub").write_text(content)
            try:
                watched(lambda home=home: guest_key(home))
            except (ContractError, Unavailable) as exc:
                require(reason in str(exc), f"{label} key refused for the wrong reason: {exc}")
                require("PRIVATE" not in str(exc) and KEY_BLOB not in str(exc),
                        f"{label} key: the refusal repeats key material: {exc}")
            else:
                raise AssertionError(f"{label} key accepted")
            plan = watched(lambda home=home: creation_plan(lab.repo, home=home, cpu_count=4))
            require(plan["guest_key"]["available"] is False and reason in plan["guest_key"]["reason"],
                    f"{label} key: the plan does not name the reason: {plan['guest_key']}")
            require(all(not entry["creatable"] and entry["blocked_reason"] for entry in plan["templates"]),
                    f"{label} key: a Template stayed creatable")
        linked = lab.root / "key-link"
        (linked / ".ssh").mkdir(parents=True)
        (linked / ".ssh/hyperlab_ed25519.pub").symlink_to(lab.home / ".ssh/hyperlab_ed25519.pub")
        try:
            watched(lambda: guest_key(linked))
        except Unavailable as exc:
            require("symbolic link" in str(exc), f"a linked key refused for the wrong reason: {exc}")
        else:
            raise AssertionError("a symlinked guest key was accepted")
    finally:
        watching[0] = False
    private = [path for path in opened if path.endswith("/hyperlab_ed25519")]
    require(not private, f"the private guest key was opened: {private}")
    require(any(path.endswith("/hyperlab_ed25519.pub") for path in opened),
            "fixture: the audit hook saw no public key being read")


def load_bridge(lab: Lab):
    spec = importlib.util.spec_from_file_location("hyperlab_machine_bridge_create", BRIDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.HYPERLABCTL = str(lab.wrapper())
    return module


def check_bridge(lab: Lab) -> None:
    bridge = load_bridge(lab)
    launched: list[tuple[str, str]] = []
    calls: list[tuple[str, ...]] = []
    real_cli = bridge.cli_json

    def recording_cli(*args: str, **kwargs: Any) -> Any:
        calls.append(args)
        return real_cli(*args, **kwargs)

    bridge.cli_json = recording_cli
    bridge.privileged = lambda action, name: launched.append((action, name))

    def attempt(*args: str) -> str:
        calls.clear()
        launched.clear()
        try:
            bridge.create(list(args))
        except bridge.Refused as exc:
            return "refused: " + str(exc)
        return "launched"

    spec = lab.repo / "vm-specs/.generated"

    # A first creation on an empty state home leaves no record when the
    # projection is refused. The registry directory and its lock may appear;
    # no record does.
    spec.mkdir(mode=0o700)
    (spec / "srv-01.yml").write_text("stale: true\n")
    result = attempt("server-arch", "srv-01", "permanent", "dev", "balanced")
    require(result.startswith("refused") and "already exists" in result,
            f"a refused projection on a fresh registry: {result}")
    records = sorted(path.name for path in (lab.state / "hyperlab/machines").glob("*"))
    require(records in ([], [".lock"]) and lab.records() == [] and not launched,
            f"a refused projection left a record on a fresh registry: {records}")
    require((spec / "srv-01.yml").read_text() == "stale: true\n", "a stale spec was changed")
    (spec / "srv-01.yml").unlink()

    result = attempt("server-arch", "srv-02", "permanent", "dev", "balanced")
    require(result == "launched" and launched == [("machine.provision", "srv-02")],
            f"a valid request was not recorded, projected and handed to the runner: {result} {launched}")
    require(calls[1:] == [("machine", "create", "server-arch", "srv-02", "--lifecycle", "permanent",
                           "--network-profile", "dev", "--resource-profile", "balanced", "--project")],
            f"the bridge did not create and project in one staged call: {calls}")
    shown = lab.ok("machine", "show", "srv-02")
    require(shown["id"] == "srv-02" and (spec / "srv-02.yml").is_file(),
            "the Machine record or its projected spec is missing")

    # Refused by create: the name exists.
    before = lab.snapshot()
    result = attempt("server-arch", "srv-02", "permanent", "dev", "balanced")
    require(result.startswith("refused") and "already exists" in result, f"duplicate name: {result}")
    require(lab.snapshot() == before and not launched, "a refusal by create changed the registry")

    # Refused at the projection, whatever stands where the spec goes, and
    # whether or not libvirt answers.
    (spec / "srv-03.yml").write_text("stale: true\n")
    (spec / "srv-09.yml").symlink_to(lab.root / "elsewhere.yml")
    (spec / "srv-10.yml").mkdir()
    for name, reason, virsh_down in (("srv-03", "already exists", False), ("srv-09", "symlink", False),
                                     ("srv-10", "already exists", False), ("srv-03", "already exists", True)):
        if virsh_down:
            lab.virsh_fails.write_text("")
        before = lab.snapshot()
        try:
            result = attempt("server-arch", name, "permanent", "dev", "balanced")
        finally:
            if lab.virsh_fails.exists():
                lab.virsh_fails.unlink()
        require(any(call[:2] == ("machine", "create") for call in calls),
                f"fixture: {name} did not reach the factory: {calls}")
        require(result.startswith("refused") and reason in result,
                f"{name}: a refused projection was not reported with its reason: {result}")
        require(lab.snapshot() == before and name not in lab.records(),
                f"{name}: a refused projection left the registry or the specs changed")
        require(not launched, f"{name}: a refused projection reached the runner")
    require(not (lab.root / "elsewhere.yml").exists(), "a projection followed the link at srv-09")

    # Refused by the bridge before anything runs.
    before = lab.snapshot()
    for args in (("server-arch", "srv-04", "-p", "dev", "balanced"),
                 ("server-arch", "srv-04", "permanent", "dev", "custom", "2048", "--vcpus=9", "20")):
        result = attempt(*args)
        require(result.startswith("refused") and not calls, f"{args} was not refused before use: {calls}")
    require(lab.snapshot() == before, "a refused request changed the registry")


def bridge_with_recorder(lab: Lab):
    """The real bridge over the wrapper; the runner is a recorder."""
    bridge = load_bridge(lab)
    launched: list[tuple[str, str]] = []
    bridge.privileged = lambda action, name: launched.append((action, name))

    def attempt(*args: str) -> str:
        launched.clear()
        try:
            bridge.create(list(args))
        except bridge.Refused as exc:
            return "refused: " + str(exc)
        return "launched"

    return attempt, launched


# A fault, where it strikes, and what the refusal must say.
UNDONE = (
    (["link"], "with no record", "cannot publish Machine record"),
    (["fsync"], "with the record published", "durability is uncertain"),
    (["read"], "with the record published", "injected record read failure"),
    (["digest"], "with the record published", "injected record digest failure"),
    (["wrong-digest"], "with the record published", "is not the one this creation published"),
    # A handled cancellation is undone like any failure, record first.
    (["interrupt-after-link"], "with the record published", "interrupted"),
    (["interrupt-inspect"], "with the record published", "interrupted"),
    (["interrupt-fsync"], "with the record published", "interrupted"),
)


def check_publication_faults(lab: Lab) -> None:
    """A creation that fails after its record was published undoes it (ADR 0053).

    The bridge runs over the real CLI; each fault strikes after the real
    os.link published the record (or, for "link", at it). Where the undo
    succeeds, the registry and the generated specs equal their snapshot and
    nothing reaches the runner. Where it cannot finish, the refusal says so,
    bytes that are not this creation's stay, and the spec stays while the
    record does.
    """
    attempt, launched = bridge_with_recorder(lab)
    spec = lab.repo / "vm-specs/.generated"
    registry = lab.state / "hyperlab/machines"

    def struck(faults: list[str], name: str) -> str:
        lab.arm(faults, name)
        try:
            return attempt("server-arch", name, "permanent", "dev", "balanced")
        finally:
            lab.disarm()

    for serial, (faults, when, reason) in enumerate(UNDONE):
        name = f"pub-{serial:02d}"
        before = lab.snapshot()
        result = struck(faults, name)
        events = lab.events()
        require(not [event for event in events if "without the lock" in event],
                f"{faults}: a removal ran without the registry lock: {events}")
        require(events[:1] == [f"{faults[0]} {when}"], f"fixture: {faults} struck as {events}")
        after = lab.snapshot()
        require(after == before and not launched,
                f"{faults}: a creation refused {when} left a record or spec behind "
                f"(record kept: {(registry / (name + '.yml')).exists()}, "
                f"spec kept: {(spec / (name + '.yml')).exists()}): {result}")
        require(result.startswith("refused") and reason in result and "incomplete" not in result,
                f"{faults}: the refusal does not name the failure: {result}")

    # Without --project the record alone is undone, on the manual path too.
    before = lab.snapshot()
    result = lab.faulty(["fsync"], "pub-10", "machine", "create", "server-arch", "pub-10")
    require(result.returncode != 0 and "durability is uncertain" in result.stderr
            and lab.events()[:1] == ["fsync with the record published"] and lab.snapshot() == before,
            f"a plain create that failed after publication kept its record: {result.stderr}")

    # The undo cannot finish. Each case names what stays.
    record = registry / "pub-20.yml"
    staged = spec / "pub-20.yml"
    replaced = b"replaced: true\n"
    for faults, then, record_left, spec_left in (
        (["fsync", "unlink-record"], "with the record published", "published", "staged"),
        (["fsync", "replace-record"], "with the record published", replaced, "staged"),
        (["fsync", "copy-record"], "with the record published", "copy", "staged"),
        (["fsync", "rewrite-record"], "with the record published", b"rewritten: true\n", "staged"),
        (["fsync", "fsync-again"], "with no record", None, "staged"),
        (["fsync", "replace-spec"], "with the record published", None, replaced),
        (["fsync", "unlink-spec"], "with no record", None, "staged"),
        (["interrupt-fsync", "unlink-record"], "with the record published", "published", "staged"),
        (["interrupt-inspect", "fsync-again"], "with no record", None, "staged"),
    ):
        before = lab.snapshot()
        result = struck(faults, "pub-20")
        events = lab.events()
        expected = [f"{faults[0]} with the record published", f"{faults[1]} {then}"]
        require(sorted(events) == sorted(expected), f"fixture: {faults} struck as {events}")
        require(result.startswith("refused") and "cleanup incomplete" in result and not launched,
                f"{faults}: an unfinished undo was not reported as such: {result}")
        if record_left is None:
            require(not record.exists() and "pub-20" not in lab.records(),
                    f"{faults}: the record this creation published stayed: {result}")
        elif record_left == "copy":
            require(record.is_file() and lab.ok("machine", "show", "pub-20")["id"] == "pub-20"
                    and "not the file this creation wrote" in result,
                    f"{faults}: a copy of the record was taken for it: {result}")
        elif record_left == "published":
            require(record.is_file() and lab.ok("machine", "show", "pub-20")["id"] == "pub-20",
                    f"{faults}: the record that could not be removed is gone: {result}")
        else:
            require(record.read_bytes() == record_left, f"{faults}: bytes this creation did not write were removed")
        require(staged.is_file() and not staged.is_symlink(), f"{faults}: the spec was removed: {result}")
        if spec_left == replaced:
            require(staged.read_bytes() == replaced, f"{faults}: a replaced spec was not kept as it was")
        else:
            require(staged.read_bytes().startswith(b"---\nschema_version: 1\nname: pub-20\n"),
                    f"{faults}: the staged spec changed: {staged.read_bytes()[:80]!r}")
        # The fixture clears what the refusal named and the tree is as before.
        for path in (record, staged):
            if path.exists():
                path.unlink()
        require(lab.snapshot() == before, f"{faults}: something besides the named files changed")

    # A fresh state home: the registry directories and the lock may appear,
    # nothing else.
    fresh = Lab(lab.root / "fresh")
    attempt, launched = bridge_with_recorder(fresh)
    fresh.arm(["fsync"], "pub-30")
    try:
        result = attempt("server-arch", "pub-30", "permanent", "dev", "balanced")
    finally:
        fresh.disarm()
    created = sorted(path.relative_to(fresh.state).as_posix() for path in fresh.state.rglob("*"))
    require(result.startswith("refused") and fresh.events()[:1] == ["fsync with the record published"]
            and created == ["hyperlab", "hyperlab/machines", "hyperlab/machines/.lock"]
            and not list((fresh.repo / "vm-specs").rglob("*.yml")) and not launched,
            f"a refused first creation left more than the registry and its lock: {created} {result}")


def check_withdraw(lab: Lab) -> None:
    created = lab.ok("machine", "create", "server-fedora", "srv-05")
    digest = created["record_sha256"]
    record = Path(created["record_path"])
    require(len(digest) == 64 and digest == hashlib.sha256(record.read_bytes()).hexdigest(),
            f"create did not report the digest of the record it wrote: {created}")
    for value, reason in (("0" * 64, "not the record"), ("ABC", "64 lowercase hex"),
                          (digest.upper(), "64 lowercase hex")):
        result = lab.cli("machine", "withdraw", "srv-05", "--record-sha256", value)
        require(result.returncode != 0 and reason in result.stderr,
                f"withdraw with digest {value!r}: {result.returncode} {result.stderr}")
        require(record.is_file(), "withdraw removed a record it did not write")
    result = lab.cli("machine", "withdraw", "srv-06", "--record-sha256", digest)
    require(result.returncode != 0 and record.is_file(), "withdraw of an unknown Machine")

    projected = lab.ok("machine", "create", "server-fedora", "srv-07")
    lab.ok("machine", "project", "srv-07")
    result = lab.cli("machine", "withdraw", "srv-07", "--record-sha256", projected["record_sha256"])
    require(result.returncode != 0 and "projected" in result.stderr and "srv-07" in lab.records(),
            f"withdraw removed a projected Machine: {result.stderr}")

    # No generated spec, but a domain with its name: the spec was removed or
    # never needed, and the record still answers for the domain.
    hand = lab.ok("machine", "create", "server-fedora", "srv-08")
    lab.domains.write_text("arch-dev-vfio\nsrv-08\n")
    result = lab.cli("machine", "withdraw", "srv-08", "--record-sha256", hand["record_sha256"])
    require(result.returncode != 0 and "libvirt domain named srv-08" in result.stderr
            and "srv-08" in lab.records(), f"withdraw removed a record whose domain exists: {result.stderr}")
    lab.domains.write_text("")
    lab.virsh_fails.write_text("")
    result = lab.cli("machine", "withdraw", "srv-08", "--record-sha256", hand["record_sha256"])
    require(result.returncode != 0 and "virsh could not list" in result.stderr and "srv-08" in lab.records(),
            f"withdraw went on without the libvirt domain list: {result.stderr}")
    lab.virsh_fails.unlink()

    # While another process holds the registry lock, neither withdraw nor
    # project goes on.
    lock = os.open(lab.state / "hyperlab/machines/.lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = lab.cli("machine", "withdraw", "srv-08", "--record-sha256", hand["record_sha256"])
        require(result.returncode != 0 and "busy" in result.stderr and "srv-08" in lab.records(),
                f"withdraw did not wait for the registry lock: {result.stderr}")
        result = lab.cli("machine", "project", "srv-08")
        require(result.returncode != 0 and "busy" in result.stderr
                and not (lab.repo / "vm-specs/.generated/srv-08.yml").exists(),
                f"project did not wait for the registry lock: {result.stderr}")
        before = lab.snapshot()
        result = lab.cli("machine", "create", "server-fedora", "srv-12", "--project")
        require(result.returncode != 0 and "busy" in result.stderr and lab.snapshot() == before,
                f"a staged creation did not wait for the registry lock: {result.stderr}")
    finally:
        os.close(lock)
    lab.ok("machine", "withdraw", "srv-08", "--record-sha256", hand["record_sha256"])

    answer = lab.ok("machine", "withdraw", "srv-05", "--record-sha256", digest)
    require(answer == {"machine": "srv-05", "withdrawn": True} and answer["withdrawn"] is True
            and not record.exists()
            and "srv-05" not in lab.records(), f"an unprojected record was not withdrawn: {answer}")


def check_withdraw_reads_the_spec(lab: Lab) -> None:
    """A spec withdraw cannot read as one YAML mapping is a refusal, never "no spec"."""
    created = lab.ok("machine", "create", "server-fedora", "srv-13")
    digest = created["record_sha256"]
    generated = lab.repo / "vm-specs/.generated"
    path = generated / "srv-13.yml"
    other = lab.root / "other-spec.yml"
    other.write_text("name: elsewhere\n")

    def fifo(target: Path) -> None:
        os.mkfifo(target, 0o600)

    cases: list[tuple[str, Any, str]] = [
        ("malformed", "name: [srv-13\n", "not one valid YAML document"),
        ("two documents", "---\nname: srv-13\n---\nname: srv-13\n", "single document"),
        ("duplicate key", "name: srv-13\nimage: server-fedora\nname: srv-13\n", "duplicate key 'name'"),
        ("not UTF-8", b"name: \xff\xfe\n", "not one valid YAML document"),
        ("not a mapping", "- srv-13\n", "not a YAML mapping"),
        ("empty", "", "not a YAML mapping"),
        ("too large", "name: srv-13\n" + "# padding\n" * 8000, "exceeds"),
        ("symlink", lambda target: target.symlink_to(other), "cannot be read"),
        ("directory", lambda target: target.mkdir(), "not a regular file"),
        ("fifo", fifo, "not a regular file"),
    ]
    if os.geteuid() != 0:
        # root reads a mode-000 file; the other cases hold for root too.
        cases.append(("unreadable", lambda target: (target.write_text("name: srv-13\n"), target.chmod(0)), "cannot be read"))
    for label, content, reason in cases:
        if callable(content):
            content(path)
        elif isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content)
        before = lab.snapshot()
        result = lab.cli("machine", "withdraw", "srv-13", "--record-sha256", digest)
        require(result.returncode != 0 and "generated spec srv-13" in result.stderr and reason in result.stderr,
                f"withdraw went on with a {label} spec: {result.returncode} {result.stdout} {result.stderr}")
        require(lab.snapshot() == before and "srv-13" in lab.records(),
                f"a refused withdraw with a {label} spec changed the record or the spec")
        if path.is_dir() and not path.is_symlink():
            path.rmdir()
        else:
            path.chmod(0o600) if not path.is_symlink() else None
            path.unlink()

    # A generated directory that is a link elsewhere is no place to look.
    aside = lab.repo / "vm-specs/.generated-real"
    generated.rename(aside)
    generated.symlink_to(aside.name)
    try:
        before = lab.snapshot()
        result = lab.cli("machine", "withdraw", "srv-13", "--record-sha256", digest)
        require(result.returncode != 0 and "srv-13" in lab.records() and lab.snapshot() == before,
                f"withdraw went on through a linked generated directory: {result.stderr}")
    finally:
        generated.unlink()
        aside.rename(generated)

    # Nor is a dangling one: a link to nothing is not "no spec".
    generated.rename(aside)
    generated.symlink_to("missing-generated")
    try:
        before = lab.snapshot()
        result = lab.cli("machine", "withdraw", "srv-13", "--record-sha256", digest)
        require(result.returncode != 0 and "is not a real directory" in result.stderr
                and "srv-13" in lab.records() and lab.snapshot() == before,
                f"withdraw went on through a dangling generated directory link: {result.stdout} {result.stderr}")
    finally:
        generated.unlink()
        aside.rename(generated)

    # A spec that parses and differs from the projection is stale: it stays,
    # and the record, which never got past intent, is withdrawn.
    path.write_text("---\nname: srv-13\nstale: true\n")
    answer = lab.ok("machine", "withdraw", "srv-13", "--record-sha256", digest)
    require(answer == {"machine": "srv-13", "withdrawn": True} and "srv-13" not in lab.records()
            and path.read_text() == "---\nname: srv-13\nstale: true\n",
            f"a stale but well-formed spec stopped the withdrawal or was touched: {answer}")
    path.unlink()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hyperlab-create-plan-") as temporary:
        root = Path(temporary)
        lab = Lab(root)
        check_key_refusals(lab)
        check_bridge(lab)
        check_publication_faults(lab)
        check_withdraw(lab)
        check_withdraw_reads_the_spec(lab)
        check_plan_matches_factory(lab)
    print("C10 Machine create-plan and intent contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
