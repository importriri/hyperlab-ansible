#!/usr/bin/env python3
"""Behavioural contract for the reviewed Machine provisioner (ADR 0017).

The real provisioner runs against recording hyperlabctl, ansible-playbook
and openssl programs, in a temporary checkout whose playbooks are real,
inert files. Three layers are held:

  * the plan: the provisioner takes the Machine's name alone, matches every
    step against its reviewed shape and checks every playbook file before
    the first step runs, so a bad plan runs nothing and asks nothing;
  * the projection: over the real CLI, a Machine whose generated spec is
    not its record's projection is refused before any step;
  * the secret: in its own process on a real PTY, the password is asked
    twice without echo, reaches openssl on stdin only, and its hash file is
    gone after success, a failed step, SIGINT, SIGTERM and SIGHUP.

Nothing touches libvirt, sudo or a guest.
"""

from __future__ import annotations

import contextlib
import errno
import importlib.util
import io
import json
import os
import pty
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "roles/host_desktop_common/files/privatestack-machine-provision.py"
CLI = ROOT / "tools/hyperlabctl/bin/hyperlabctl"
sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))

from hyperlabctl.machine_provision import PROFILE_PLAYBOOKS  # noqa: E402

SECRET = "correct horse battery"
KEY_LINE = ("ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIAABAgMEBQYHCAkKCwwNDg8QERITFBUWFxgZGhscHR4f"
            " sid@nitro")
PLAYBOOKS = ("vm-create.yml", "vm-guest-inventory.yml", "guest-close-access.yml",
             *(Path(path).name for path in PROFILE_PLAYBOOKS.values()))
OPENSSL = shutil.which("openssl") or "/usr/bin/openssl"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def load():
    spec = importlib.util.spec_from_file_location("machine_provision", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def steps(machine: str, workstation: bool, runtime: Path) -> dict:
    """What `hyperlabctl machine provision-steps` prints for a valid Machine."""
    spec = f"vm-specs/.generated/{machine}.yml"
    key = json.dumps({"guest_cloud_init_ssh_public_keys": [" ".join(KEY_LINE.split()[:2])]},
                     separators=(",", ":"))
    inventory = str(runtime / f"{machine}.ini")
    result = [
        {"id": "create-domain", "label": "Create", "password": False,
         "argv": ["ansible-playbook", "playbooks/vm-create.yml", "-K", "-e", f"guest_spec={spec}",
                  "-e", "guest_start_after_create=true", "-e", key]},
        {"id": "inventory", "label": "Inventory", "password": False,
         "argv": ["ansible-playbook", "playbooks/vm-guest-inventory.yml", "-K", "-e", f"guest_spec={spec}"]},
    ]
    if workstation:
        profile = ["ansible-playbook", "-i", "inventory.ini", "-i", inventory,
                   "playbooks/guest-arch-dev-vfio.yml"]
        result += [
            {"id": "profile-first", "label": "Profile", "password": True,
             "argv": [*profile, "-e", "@{access_file}"]},
            {"id": "profile-second", "label": "Profile again", "password": False, "argv": profile},
        ]
    result.append({"id": "close-access", "label": "Close", "password": False,
                   "argv": ["ansible-playbook", "-i", "inventory.ini", "-i", inventory,
                            "playbooks/guest-close-access.yml"]})
    return {"schema": 1, "machine": machine, "spec": spec, "steps": result}


# Records its argv, environment, terminal and, for an @file argument, the
# file as it is while the playbook runs. While `hold` names a token of its
# argv it announces itself in `ready` and waits; it survives the hangup of
# its terminal, so only the provisioner's own SIGTERM ends it, and records
# whether the hash file was still there when that came. While `fail` names
# a token it exits 3.
ANSIBLE = r'''
import json, os, signal, stat, sys, time
base = sys.argv[1]
args = sys.argv[2:]
entry = {"argv": args, "env": dict(os.environ), "tty": os.isatty(0)}
try:
    os.close(os.open("/dev/tty", os.O_RDWR))
    entry["controlling_tty"] = True
except OSError:
    entry["controlling_tty"] = False
for part in args:
    if part.startswith("@"):
        path = part[1:]
        info = os.lstat(path)
        parent = os.lstat(os.path.dirname(path))
        entry.update(file=path, file_mode=stat.S_IMODE(info.st_mode), file_uid=info.st_uid,
                     dir=os.path.dirname(path), dir_mode=stat.S_IMODE(parent.st_mode),
                     dir_uid=parent.st_uid, content=open(path).read())
with open(os.path.join(base, "calls.jsonl"), "a") as stream:
    stream.write(json.dumps(entry) + "\n")
def token(name):
    try:
        return open(os.path.join(base, name)).read()
    except FileNotFoundError:
        return ""
hold, fail = token("hold"), token("fail")
if hold and hold in " ".join(args):
    def terminated(signum, frame):
        with open(os.path.join(base, "terminated"), "w") as stream:
            json.dump({"file_present": os.path.exists(entry["file"])}, stream)
        os._exit(143)
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, terminated)
    with open(os.path.join(base, "ready.tmp"), "w") as stream:
        json.dump({"pid": os.getpid(), "file": entry.get("file")}, stream)
    os.rename(os.path.join(base, "ready.tmp"), os.path.join(base, "ready"))
    time.sleep(60)
    sys.exit(0)
sys.exit(3 if fail and fail in " ".join(args) else 0)
'''

# Records what it was given, then lets the real openssl answer.
OPENSSL_STUB = r'''
import json, os, subprocess, sys
base = sys.argv[1]
data = sys.stdin.read()
with open(os.path.join(base, "openssl.jsonl"), "a") as stream:
    stream.write(json.dumps({"argv": sys.argv[3:], "env": dict(os.environ), "stdin": data}) + "\n")
result = subprocess.run([sys.argv[2], *sys.argv[3:]], input=data, capture_output=True, text=True)
sys.stdout.write(result.stdout)
sys.exit(result.returncode)
'''

CLI_STUB = r'''
import json, os, sys
base = sys.argv[1]
with open(os.path.join(base, "cli.jsonl"), "a") as stream:
    stream.write(json.dumps(sys.argv[2:]) + "\n")
plan = os.path.join(base, "plan.json")
if not os.path.exists(plan):
    sys.exit("no plan")
sys.stdout.write(open(plan).read())
'''


class Fixture:
    """A checkout with inert playbooks, a private runtime directory and stubs."""

    def __init__(self, base: Path, plan: dict | None = None) -> None:
        self.base = base
        self.repo = base / "repo"
        (self.repo / "playbooks").mkdir(parents=True)
        for name in PLAYBOOKS:
            (self.repo / "playbooks" / name).write_text("---\n- hosts: none\n  tasks: []\n")
        self.runtime = base / "runtime"
        self.runtime.mkdir(mode=0o700)
        self.pointer = base / "pointer"
        self.pointer.write_text(str(self.repo))
        self.bin = base / "bin"
        self.bin.mkdir()
        self.cli = self.program("hyperlabctl", CLI_STUB)
        self.ansible = self.program("ansible-playbook", ANSIBLE)
        self.openssl = self.program("openssl", OPENSSL_STUB, OPENSSL)
        if plan is not None:
            self.plan(plan)

    def program(self, name: str, source: str, *fixed: str) -> Path:
        (self.base / f"{name}.py").write_text(source)
        path = self.bin / name
        path.write_text("#!/bin/sh\nexec %s -I %s %s %s \"$@\"\n" % (
            sys.executable, self.base / f"{name}.py", self.base, " ".join(fixed)))
        path.chmod(0o755)
        return path

    def plan(self, plan: dict) -> None:
        (self.base / "plan.json").write_text(json.dumps(plan))

    def configure(self, module) -> None:
        module.CLI = str(self.cli)
        module.ANSIBLE = str(self.ansible)
        module.OPENSSL = str(self.openssl)
        module.POINTER = self.pointer

    def log(self, name: str) -> list:
        path = self.base / name
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    @property
    def calls(self) -> list[dict]:
        return self.log("calls.jsonl")

    @property
    def private(self) -> Path:
        return self.runtime / "hyperlab/provision"

    def leftovers(self) -> list[Path]:
        """What is left in the private provisioning directory, if it exists."""
        return list(self.private.iterdir()) if self.private.exists() else []


def argvs(calls: list[dict]) -> list[list[str]]:
    """What a failure message may show of the recorded calls: argv only."""
    return [call["argv"] for call in calls]


def run(module, fixture: Fixture, args: list[str], *, passwords=None, fail_step=""):
    """The provisioner's main() in this process, with getpass answered."""
    if fail_step:
        (fixture.base / "fail").write_text(fail_step)
    answers = iter(passwords or [])
    prompts: list[str] = []

    def getpass(prompt=""):
        prompts.append(prompt)
        return next(answers)

    fixture.configure(module)
    previous = Path.cwd()
    os.chdir(fixture.repo)
    output = io.StringIO()
    try:
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(fixture.runtime)}), \
                patch.object(module.getpass, "getpass", getpass), \
                contextlib.redirect_stdout(output):
            try:
                rc = module.main(args)
            except module.Refused as exc:
                rc = "refused: " + str(exc)
    finally:
        os.chdir(previous)
    return rc, fixture.calls, prompts, output.getvalue()


def check_sequences(module) -> None:
    with tempfile.TemporaryDirectory() as temp:
        fixture = Fixture(Path(temp))
        fixture.plan(steps("srv-a", False, fixture.runtime))
        rc, calls, prompts, _ = run(module, fixture, ["srv-a"])
        require(rc == 0, f"server provisioning failed: {rc}")
        require([call["argv"] for call in calls] == [step["argv"][1:] for step in
                                                     steps("srv-a", False, fixture.runtime)["steps"]],
                f"server steps ran differently: {argvs(calls)}")
        require(not prompts and not fixture.private.exists(), "a server asked for a password")
        require(fixture.log("cli.jsonl") == [["--repo", str(fixture.repo.resolve()), "machine",
                                              "provision-steps", "srv-a"]],
                f"the steps were not asked for this Machine: {fixture.log('cli.jsonl')}")

    with tempfile.TemporaryDirectory() as temp:
        fixture = Fixture(Path(temp))
        fixture.plan(steps("dev-a", True, fixture.runtime))
        rc, calls, prompts, output = run(module, fixture, ["dev-a"], passwords=[SECRET, SECRET])
        require(rc == 0, f"workstation provisioning failed: {rc}")
        require(len(calls) == 5 and calls[4]["argv"][-1] == "playbooks/guest-close-access.yml",
                f"workstation steps: {argvs(calls)}")
        first = calls[2]
        require(first.get("file_mode") == 0o600 and first.get("dir_mode") == 0o700
                and first["dir"] == str(fixture.private), f"hash file not private: {first.get('file_mode')} {first.get('dir_mode')} {first.get('dir')}")
        value = first["content"].split("'")[1]
        require(first["content"].startswith("workstation_access_password_hash: '")
                and module.HASH_RE.fullmatch(value), f"hash file content: {first['content']!r}")
        require(SECRET not in json.dumps(calls) and SECRET not in output, "the password leaked")
        require("@{access_file}" not in json.dumps(calls), "placeholder reached ansible")
        require(not list(fixture.private.iterdir()), "the hash file outlived the first pass")
        require("file" not in calls[3] and "file" not in calls[4], "a later pass read the hash")
        require(len(prompts) == 2, f"the password was not asked exactly twice: {prompts}")

    with tempfile.TemporaryDirectory() as temp:
        fixture = Fixture(Path(temp))
        fixture.plan(steps("dev-b", True, fixture.runtime))
        rc, calls, _, _ = run(module, fixture, ["dev-b"], passwords=[SECRET, SECRET],
                              fail_step="guest-arch-dev-vfio.yml -e")
        require(rc == 3 and len(calls) == 3, f"a failed profile pass did not stop: {rc} {argvs(calls)}")
        require(not list(fixture.private.iterdir()), "a failed pass left the hash file")

    with tempfile.TemporaryDirectory() as temp:
        fixture = Fixture(Path(temp))
        fixture.plan(steps("srv-b", False, fixture.runtime))
        rc, calls, _, _ = run(module, fixture, ["srv-b"], fail_step="vm-create")
        require(rc == 3 and len(calls) == 1, "a failed domain creation did not stop provisioning")

    with tempfile.TemporaryDirectory() as temp:
        fixture = Fixture(Path(temp))
        fixture.plan(steps("dev-c", True, fixture.runtime))
        rc, calls, _, _ = run(module, fixture, ["dev-c"],
                              passwords=["one-password", "two-password", "short", "short",
                                         SECRET, SECRET + "x"])
        require(isinstance(rc, str) and "no password" in rc and len(calls) == 2,
                f"unconfirmed passwords were accepted: {rc}")
        require(not fixture.leftovers(), "an unconfirmed password left a file")


def check_profile_table(module) -> None:
    reviewed = frozenset(PROFILE_PLAYBOOKS.values())
    require(reviewed == module.PROFILE_PLAYBOOKS,
            "the provisioner's reviewed profiles differ from hyperlabctl's table: "
            f"{sorted(module.PROFILE_PLAYBOOKS)} {sorted(PROFILE_PLAYBOOKS.values())}")


def check_plan_refusals(module) -> None:
    """A plan that is not the reviewed one runs nothing and asks nothing."""

    def tampered(change):
        def build(runtime: Path) -> dict:
            plan = steps("dev-t", True, runtime)
            change(plan, runtime)
            return plan
        return build

    def argv(index):
        return lambda plan: plan["steps"][index]["argv"]

    def key_json(value):
        return json.dumps(value, separators=(",", ":"))

    plans = {
        "unreviewed playbook": tampered(lambda p, r: argv(1)(p).__setitem__(1, "playbooks/lab.yml")),
        "variables file": tampered(lambda p, r: argv(0)(p).extend(["-e", "@/etc/shadow"])),
        "become prompt": tampered(lambda p, r: argv(0)(p).remove("-K")),
        "host privilege": tampered(lambda p, r: argv(3)(p).append("-K")),
        "order": tampered(lambda p, r: p["steps"].reverse()),
        "close-access early": tampered(lambda p, r: p["steps"].insert(2, p["steps"].pop())),
        "close-access as a profile": tampered(lambda p, r: argv(2)(p).__setitem__(
            5, "playbooks/guest-close-access.yml")),
        "close-access dropped": tampered(lambda p, r: p["steps"].pop()),
        "profile-second dropped": tampered(lambda p, r: p["steps"].pop(3)),
        "wrong final step": tampered(lambda p, r: p["steps"][-1].__setitem__(
            "argv", list(p["steps"][3]["argv"]))),
        "another spec": tampered(lambda p, r: p.__setitem__("spec", "vm-specs/arch-dev.yml")),
        "another Machine": tampered(lambda p, r: p.__setitem__("machine", "dev-u")),
        "another binary": tampered(lambda p, r: argv(0)(p).__setitem__(0, "bash")),
        "absolute binary": tampered(lambda p, r: argv(0)(p).__setitem__(0, "/usr/bin/ansible-playbook")),
        "placeholder": tampered(lambda p, r: argv(1)(p).append("{access_file}")),
        "traversal": tampered(lambda p, r: argv(4)(p).__setitem__(
            5, "playbooks/../playbooks/guest-close-access.yml")),
        "absolute playbook": tampered(lambda p, r: argv(1)(p).__setitem__(
            1, str(ROOT / "playbooks/vm-guest-inventory.yml"))),
        "second playbook": tampered(lambda p, r: argv(1)(p).insert(2, "/tmp/other.yml")),
        "unreviewed profile": tampered(lambda p, r: [argv(i)(p).__setitem__(
            5, "playbooks/guest-arch-hyprland.yml") for i in (2, 3)]),
        "profile passes differ": tampered(lambda p, r: argv(3)(p).__setitem__(
            5, PROFILE_PLAYBOOKS["workstation-dev-standard"])),
        "inventory elsewhere": tampered(lambda p, r: argv(4)(p).__setitem__(4, "/tmp/dev-t.ini")),
        "another inventory": tampered(lambda p, r: argv(2)(p).__setitem__(2, "/etc/ansible/hosts")),
        "extra variable": tampered(lambda p, r: argv(1)(p).extend(["-e", "ansible_python_interpreter=/bin/sh"])),
        "extra option": tampered(lambda p, r: argv(4)(p).append("--step")),
        "two keys": tampered(lambda p, r: argv(0)(p).__setitem__(-1, key_json(
            {"guest_cloud_init_ssh_public_keys": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA",
                                                  "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5BBBB"]}))),
        "key with more": tampered(lambda p, r: argv(0)(p).__setitem__(-1, key_json(
            {"guest_cloud_init_ssh_public_keys": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA"],
             "guest_start_after_create": False}))),
        "unknown step": tampered(lambda p, r: p["steps"][1].__setitem__("id", "shell")),
        "password on a host step": tampered(lambda p, r: p["steps"][0].__setitem__("password", True)),
    }
    for label, build in plans.items():
        with tempfile.TemporaryDirectory() as temp:
            fixture = Fixture(Path(temp))
            fixture.plan(build(fixture.runtime))
            rc, calls, prompts, _ = run(module, fixture, ["dev-t"], passwords=[SECRET] * 2)
            require(isinstance(rc, str) and rc.startswith("refused") and not calls and not prompts,
                    f"tampered steps ({label}) ran or asked: {rc} {argvs(calls)} {prompts}")


def check_file_refusals(module) -> None:
    """Every playbook is an existing regular file in the real playbooks/
    directory, checked for the whole plan before its first step."""

    def remove(name):
        return lambda f: (f.repo / "playbooks" / name).unlink()

    def link_inside(name, target):
        def change(f):
            (f.repo / "playbooks" / name).unlink()
            (f.repo / "playbooks" / name).symlink_to(target)
        return change

    def link_outside(name):
        def change(f):
            outside = f.base / "outside.yml"
            outside.write_text("---\n")
            (f.repo / "playbooks" / name).unlink()
            (f.repo / "playbooks" / name).symlink_to(outside)
        return change

    def linked_directory(f):
        real = f.base / "elsewhere"
        shutil.copytree(f.repo / "playbooks", real)
        shutil.rmtree(f.repo / "playbooks")
        (f.repo / "playbooks").symlink_to(real)

    def directory(name):
        def change(f):
            (f.repo / "playbooks" / name).unlink()
            (f.repo / "playbooks" / name).mkdir()
        return change

    def fifo(name):
        def change(f):
            (f.repo / "playbooks" / name).unlink()
            os.mkfifo(f.repo / "playbooks" / name)
        return change

    cases = {
        "missing final playbook": remove("guest-close-access.yml"),
        "missing profile": remove("guest-arch-dev-vfio.yml"),
        "missing inventory playbook": remove("vm-guest-inventory.yml"),
        "missing create playbook": remove("vm-create.yml"),
        "final playbook linked inside": link_inside("guest-close-access.yml", "vm-create.yml"),
        "final playbook linked outside": link_outside("guest-close-access.yml"),
        "create playbook linked outside": link_outside("vm-create.yml"),
        "playbooks directory linked": linked_directory,
        "final playbook a directory": directory("guest-close-access.yml"),
        "final playbook a pipe": fifo("guest-close-access.yml"),
    }
    for label, change in cases.items():
        with tempfile.TemporaryDirectory() as temp:
            fixture = Fixture(Path(temp))
            fixture.plan(steps("dev-t", True, fixture.runtime))
            change(fixture)
            rc, calls, prompts, _ = run(module, fixture, ["dev-t"], passwords=[SECRET] * 2)
            require(isinstance(rc, str) and rc.startswith("refused") and not calls and not prompts,
                    f"a plan with a {label} ran or asked: {rc} {argvs(calls)} {prompts}")


def check_arguments(module) -> None:
    for args in (["--spec", "vm-specs/.generated/dev-t.yml", "dev-t"], [], ["dev-t", "dev-t"],
                 ["dev-t", "--verbose"], ["../x"], ["Dev-T"], ["vm-specs/.generated/dev-t.yml"],
                 ["dev-u"]):
        with tempfile.TemporaryDirectory() as temp:
            fixture = Fixture(Path(temp))
            fixture.plan(steps("dev-t", True, fixture.runtime))
            rc, calls, prompts, _ = run(module, fixture, args, passwords=[SECRET] * 2)
            require(isinstance(rc, str) and not calls and not prompts, f"bad arguments accepted: {args}")


# --- over the real CLI ----------------------------------------------------

def tree(*bases: Path) -> dict:
    result = {}
    for base in bases:
        for path in sorted(base.rglob("*")):
            info = path.lstat()
            data = path.read_bytes() if path.is_file() and not path.is_symlink() else None
            result[str(path)] = (info.st_mode, data)
    return result


def check_real_cli(module) -> None:
    """The provisioner over the real `provision-steps` of a temporary checkout."""
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        fixture = Fixture(base)
        for name in ("images", "templates"):
            shutil.copytree(ROOT / name, fixture.repo / name)
        for path in (fixture.repo / "templates").glob("*.md"):
            path.unlink()
        unreviewed = yaml.safe_load((fixture.repo / "templates/workstation-dev.yml").read_text())
        unreviewed["id"] = "workstation-unreviewed"
        (fixture.repo / "templates/workstation-unreviewed.yml").write_text(
            yaml.safe_dump(unreviewed, sort_keys=False))
        (fixture.repo / "vm-specs").mkdir()
        home = base / "home"
        (home / ".ssh").mkdir(parents=True)
        (home / ".ssh/hyperlab_ed25519.pub").write_text(KEY_LINE + "\n")
        state = base / "state"
        env = {"HOME": str(home), "XDG_STATE_HOME": str(state), "PYTHONDONTWRITEBYTECODE": "1"}
        # Where the provisioner expects hyperlabctl: the real CLI, with this
        # fixture's home and state, in its own process.
        fixture.cli.write_text(
            f"#!{sys.executable}\n"
            "import os, sys\n"
            f"os.environ.update({env!r})\n"
            "sys.dont_write_bytecode = True\n"
            f"sys.path.insert(0, {str(ROOT / 'tools/hyperlabctl')!r})\n"
            "from hyperlabctl.cli import main\n"
            "sys.exit(main(sys.argv[1:]))\n")

        def factory(*args: str) -> None:
            result = subprocess.run([sys.executable, str(CLI), "--repo", str(fixture.repo), *args],
                                    text=True, capture_output=True, check=False,
                                    env={**os.environ, **env})
            require(result.returncode == 0, f"hyperlabctl {args}: {result.stderr}")

        factory("machine", "create", "server-arch", "srv-01", "--resource-profile", "custom",
                "--memory-mb", "2048", "--vcpus", "2", "--disk-gib", "16", "--project")
        rc, calls, prompts, _ = run(module, fixture, ["srv-01"])
        require(rc == 0 and [call["argv"][0] for call in calls]
                == ["playbooks/vm-create.yml", "playbooks/vm-guest-inventory.yml", "-i"]
                and calls[2]["argv"][-1] == "playbooks/guest-close-access.yml" and not prompts,
                f"a projected server was not provisioned over the real CLI: {rc} {argvs(calls)}")
        (base / "calls.jsonl").unlink()

        factory("machine", "create", "workstation-dev", "dev-01", "--looking-glass-mode",
                "linux-experimental", "--project")
        rc, calls, prompts, _ = run(module, fixture, ["dev-01"], passwords=[SECRET, SECRET])
        require(rc == 0 and len(calls) == 5 and calls[2]["argv"][3] == str(fixture.runtime / "dev-01.ini")
                and len(prompts) == 2 and not list(fixture.private.iterdir()),
                f"a projected workstation was not provisioned over the real CLI: {rc} {argvs(calls)}")
        (base / "calls.jsonl").unlink()

        # One vCPU, where `vcpus: true` is equal in Python and wrong in YAML.
        factory("machine", "create", "server-arch", "srv-03", "--resource-profile", "custom",
                "--memory-mb", "2048", "--vcpus", "1", "--disk-gib", "16", "--project")
        for machine, field, change in (
                ("srv-01", "memory", lambda d: d["resources"].__setitem__("memory_mb", 8192)),
                ("srv-01", "device", lambda d: d.__setitem__("device_profile", "vfio")),
                ("srv-01", "network", lambda d: d.__setitem__("network_profile", "lab")),
                ("srv-01", "float memory", lambda d: d["resources"].__setitem__(
                    "memory_mb", float(d["resources"]["memory_mb"]))),
                ("srv-01", "boolean schema", lambda d: d.__setitem__("schema_version", True)),
                ("srv-01", "integer autostart", lambda d: d.__setitem__("autostart", 0)),
                ("srv-03", "vcpus true for 1", lambda d: d["resources"].__setitem__("vcpus", True)),
                ("srv-03", "memory_mb 2048.0 for 2048", lambda d: d["resources"].__setitem__("memory_mb", 2048.0))):
            spec = fixture.repo / f"vm-specs/.generated/{machine}.yml"
            good = spec.read_bytes()
            document = yaml.safe_load(good)
            change(document)
            spec.write_text("---\n" + yaml.safe_dump(document, sort_keys=False))
            before = tree(state, fixture.repo / "vm-specs")
            rc, calls, prompts, _ = run(module, fixture, [machine])
            require(isinstance(rc, str) and "differs from the projection" in rc and not calls and not prompts,
                    f"the provisioner ran with an edited spec ({field}): {rc} {argvs(calls)}")
            require(tree(state, fixture.repo / "vm-specs") == before,
                    f"a refused provisioning changed the registry or a spec ({field})")
            spec.write_bytes(good)
        rc, calls, prompts, _ = run(module, fixture, ["srv-03"])
        require(rc == 0 and len(calls) == 3 and not prompts,
                f"the restored one-vCPU projection was not provisioned: {rc} {argvs(calls)}")
        (base / "calls.jsonl").unlink()

        factory("machine", "create", "workstation-unreviewed", "dev-02", "--looking-glass-mode",
                "linux-experimental", "--project")
        before = tree(state, fixture.repo / "vm-specs")
        rc, calls, prompts, _ = run(module, fixture, ["dev-02"], passwords=[SECRET] * 2)
        require(isinstance(rc, str) and "no reviewed profile playbook" in rc and not calls and not prompts,
                f"an unreviewed workstation was provisioned: {rc} {argvs(calls)}")
        require(tree(state, fixture.repo / "vm-specs") == before, "an unreviewed workstation changed state")


# --- the real program on a real PTY ----------------------------------------

LAUNCHER = """\
import importlib.util, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location("provisioner", {source!r})
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.CLI, module.ANSIBLE, module.OPENSSL = {cli!r}, {ansible!r}, {openssl!r}
module.POINTER = Path({pointer!r})
sys.exit(module.entry(sys.argv[1:]))
"""


class Terminal:
    """The provisioner in its own session, on a PTY that is its controlling terminal."""

    def __init__(self, fixture: Fixture, machine: str) -> None:
        launcher = fixture.base / "launcher.py"
        launcher.write_text(LAUNCHER.format(source=str(SOURCE), cli=str(fixture.cli),
                                            ansible=str(fixture.ansible), openssl=str(fixture.openssl),
                                            pointer=str(fixture.pointer)))
        env = {"PATH": "/usr/local/bin:/usr/bin", "HOME": str(fixture.base),
               "XDG_RUNTIME_DIR": str(fixture.runtime), "LANG": "C.UTF-8", "TERM": "xterm-256color"}
        self.transcript = b""
        self.status: int | None = None
        pid, fd = pty.fork()
        if pid == 0:
            try:
                os.chdir(fixture.repo)
                os.execve(sys.executable, [sys.executable, "-I", str(launcher), machine], env)
            finally:
                os._exit(127)
        self.pid, self.fd = pid, fd

    def pump(self, timeout: float) -> None:
        ready, _, _ = select.select([self.fd], [], [], timeout)
        if ready:
            try:
                data = os.read(self.fd, 65536)
            except OSError as exc:
                if exc.errno != errno.EIO:
                    raise
                data = b""
            self.transcript += data

    def expect(self, text: str, deadline: float = 20) -> None:
        end = time.monotonic() + deadline
        while text.encode() not in self.transcript:
            require(time.monotonic() < end and self.alive(),
                    f"the provisioner never printed {text!r}: {self.transcript[-400:]!r}")
            self.pump(0.2)

    def answer(self, prompt: str, value: str) -> None:
        seen = self.transcript.count(prompt.encode())
        end = time.monotonic() + 20
        while self.transcript.count(prompt.encode()) <= seen:
            require(time.monotonic() < end and self.alive(),
                    f"no prompt {prompt!r}: {self.transcript[-400:]!r}")
            self.pump(0.2)
        os.write(self.fd, (value + "\n").encode())

    def alive(self) -> bool:
        if self.status is None:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid:
                self.status = status
        return self.status is None

    def wait(self, deadline: float = 30) -> int:
        end = time.monotonic() + deadline
        while self.alive():
            if time.monotonic() > end:
                os.kill(self.pid, signal.SIGKILL)
                raise AssertionError(f"the provisioner did not end: {self.transcript[-400:]!r}")
            self.pump(0.1)
        with contextlib.suppress(OSError):
            while True:
                ready, _, _ = select.select([self.fd], [], [], 0)
                if not ready:
                    break
                data = os.read(self.fd, 65536)
                if not data:
                    break
                self.transcript += data
        os.close(self.fd)
        return self.status


def secret_free(fixture: Fixture, transcript: bytes) -> None:
    require(SECRET.encode() not in transcript, "the password was echoed into the terminal")
    for call in fixture.calls:
        require(SECRET not in json.dumps(call["argv"]) and SECRET not in json.dumps(call["env"]),
                f"the password reached a playbook's argv or environment: {call['argv']}")
    for call in fixture.log("openssl.jsonl"):
        require(SECRET not in json.dumps(call["argv"]) and SECRET not in json.dumps(call["env"]),
                "the password reached openssl's argv or environment")


def check_terminal_success(module) -> None:
    with tempfile.TemporaryDirectory() as temp:
        fixture = Fixture(Path(temp), steps("dev-p", True, Path(temp) / "runtime"))
        terminal = Terminal(fixture, "dev-p")
        terminal.answer("New password for the Machine account: ", SECRET)
        terminal.answer("Repeat it: ", SECRET)
        status = terminal.wait()
        require(os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0,
                f"workstation provisioning failed on a PTY: {status} {terminal.transcript[-400:]!r}")
        require(terminal.transcript.count(b"New password for the Machine account: ") == 1
                and terminal.transcript.count(b"Repeat it: ") == 1,
                "the password was not asked exactly twice")
        secret_free(fixture, terminal.transcript)
        openssl = fixture.log("openssl.jsonl")
        require(len(openssl) == 1 and openssl[0]["argv"] == ["passwd", "-6", "-stdin"]
                and openssl[0]["stdin"] == SECRET + "\n",
                f"openssl did not get the password on stdin alone: {[o['argv'] for o in openssl]}")
        calls = fixture.calls
        require(len(calls) == 5, f"workstation steps on a PTY: {[c['argv'] for c in calls]}")
        require(all(call["tty"] and call["controlling_tty"] for call in calls),
                "a step ran without the operation terminal, where its become prompt goes")
        first = calls[2]
        require(first.get("file_mode") == 0o600 and first.get("dir_mode") == 0o700
                and first["file_uid"] == os.getuid() and first["dir_uid"] == os.getuid()
                and first["dir"] == str(fixture.private), f"hash file not private: {first.get('file_mode')} {first.get('dir_mode')} {first.get('dir')}")
        hashed = first["content"].split("'")[1]
        require(module.HASH_RE.fullmatch(hashed) and hashed.startswith("$6$"),
                f"not a SHA-512 crypt hash: {first['content']!r}")
        require(all("file" not in call for call in calls[:2] + calls[3:]),
                "the hash file reached a step other than the first profile pass")
        require(stat.S_IMODE(fixture.private.stat().st_mode) == 0o700 and not list(fixture.private.iterdir()),
                "the hash file outlived a successful run")


def check_terminal_failure(module) -> None:
    with tempfile.TemporaryDirectory() as temp:
        fixture = Fixture(Path(temp), steps("dev-f", True, Path(temp) / "runtime"))
        (fixture.base / "fail").write_text("guest-arch-dev-vfio.yml -e")
        terminal = Terminal(fixture, "dev-f")
        terminal.answer("New password for the Machine account: ", SECRET)
        terminal.answer("Repeat it: ", SECRET)
        status = terminal.wait()
        require(os.WIFEXITED(status) and os.WEXITSTATUS(status) == 3,
                f"a failed profile pass did not end the run with its status: {status}")
        require(len(fixture.calls) == 3, f"steps ran after a failure: {[c['argv'] for c in fixture.calls]}")
        require(not list(fixture.private.iterdir()), "a failed step left the hash file")
        secret_free(fixture, terminal.transcript)


def check_terminal_signals(module) -> None:
    """A real signal while the first profile pass holds the hash file."""
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        with tempfile.TemporaryDirectory() as temp:
            fixture = Fixture(Path(temp), steps("dev-s", True, Path(temp) / "runtime"))
            (fixture.base / "hold").write_text("guest-arch-dev-vfio.yml -e")
            terminal = Terminal(fixture, "dev-s")
            child = None
            try:
                terminal.answer("New password for the Machine account: ", SECRET)
                terminal.answer("Repeat it: ", SECRET)
                ready = fixture.base / "ready"
                end = time.monotonic() + 20
                while not ready.exists():
                    require(time.monotonic() < end and terminal.alive(),
                            f"the first profile pass never started: {terminal.transcript[-400:]!r}")
                    terminal.pump(0.1)
                handshake = json.loads(ready.read_text())
                child = handshake["pid"]
                require(Path(handshake["file"]).is_file(), "fixture: no hash file at the handshake")
                os.kill(terminal.pid, sig)
                status = terminal.wait()
            finally:
                if terminal.alive():
                    os.kill(terminal.pid, signal.SIGKILL)
                    terminal.wait()
            name = signal.Signals(sig).name
            gone = False
            for _ in range(50):
                try:
                    os.kill(child, 0)
                except ProcessLookupError:
                    gone = True
                    break
                time.sleep(0.1)
            if not gone:
                os.kill(child, signal.SIGKILL)
            require(not Path(handshake["file"]).exists() and not list(fixture.private.iterdir()),
                    f"the hash file outlived {name}")
            require(not (os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0),
                    f"{name} was reported as success")
            require(os.WIFEXITED(status) and os.WEXITSTATUS(status) == 128 + sig,
                    f"{name} did not end the provisioner through its handler: {status}")
            require(len(fixture.calls) == 3, f"a step ran after {name}: {[c['argv'] for c in fixture.calls]}")
            require(gone, f"the running playbook outlived {name}")
            stopped = fixture.base / "terminated"
            require(stopped.exists() and json.loads(stopped.read_text()) == {"file_present": True},
                    f"after {name} the running playbook was not stopped before its hash file went")
            secret_free(fixture, terminal.transcript)


def main() -> int:
    module = load()
    check_profile_table(module)
    check_sequences(module)
    check_plan_refusals(module)
    check_file_refusals(module)
    check_arguments(module)
    check_real_cli(module)
    check_terminal_success(module)
    check_terminal_failure(module)
    check_terminal_signals(module)

    source = SOURCE.read_text(encoding="utf-8")
    require("shell=True" not in source and "--become-password" not in source,
            "the provisioner gained a shell or cached the become password")
    print("HyperLab Machine provisioner contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
