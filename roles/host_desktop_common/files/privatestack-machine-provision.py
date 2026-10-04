#!/usr/bin/python3 -I
"""Provision one created and projected Machine inside its operation terminal.

The operation runner starts this as the reviewed command of
machine.provision. The steps come from `hyperlabctl machine provision-steps`
in the reviewed checkout, never from a caller; only ansible-playbook runs of
reviewed playbooks are accepted. Each -K playbook asks for the become
password in this terminal. A workstation password is asked here without
echo, turned into a SHA-512 crypt hash, written to a private runtime file for
the first profile pass and deleted in every outcome (ADR 0017).
"""
from __future__ import annotations

import contextlib
import getpass
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

CLI = "/usr/local/bin/hyperlabctl"
ANSIBLE = "/usr/bin/ansible-playbook"
OPENSSL = "/usr/bin/openssl"
POINTER = Path("/etc/hyperlabctl/checkout")
MACHINE_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,30}$")
HASH_RE = re.compile(r"^\$6\$[^$]{1,16}\$[./A-Za-z0-9]{86}$")
PLAYBOOKS = {"playbooks/vm-create.yml", "playbooks/vm-guest-inventory.yml"}
PROFILE_RE = re.compile(r"^playbooks/guest-[a-z0-9-]+\.yml$")
ACCESS_FILE = "{access_file}"
STEP_IDS = ("create-domain", "inventory", "profile-first", "profile-second")
PASSWORD_MIN = 8


class Refused(ValueError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise Refused(reason)


def checkout() -> Path:
    repo = Path(POINTER.read_text(encoding="utf-8").strip())
    require(repo.is_absolute() and repo.is_dir(), "invalid HyperLab checkout")
    return repo.resolve()


def runtime_dir() -> Path:
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    info = runtime.lstat()
    require(runtime.is_absolute() and stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == 0o700, "unsafe runtime directory")
    return runtime


def private_dir(runtime: Path) -> Path:
    path = runtime
    for name in ("hyperlab", "provision"):
        path = path / name
        with contextlib.suppress(FileExistsError):
            path.mkdir(mode=0o700)
        info = path.lstat()
        require(stat.S_ISDIR(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o700, "unsafe provisioning directory")
    return path


def valid_step(step: object, spec: str) -> dict:
    require(isinstance(step, dict) and step.get("id") in STEP_IDS
            and isinstance(step.get("label"), str) and isinstance(step.get("password"), bool),
            "invalid provisioning step")
    argv = step.get("argv")
    require(isinstance(argv, list) and len(argv) >= 2 and argv[0] == "ansible-playbook"
            and all(isinstance(part, str) and part and not any(ord(c) < 32 for c in part)
                    for part in argv), "invalid provisioning command")
    playbooks = [part for part in argv[1:] if part.startswith("playbooks/")]
    require(len(playbooks) == 1 and (playbooks[0] in PLAYBOOKS or PROFILE_RE.fullmatch(playbooks[0])),
            "unreviewed playbook in a provisioning step")
    files = [argv[i + 1] for i, part in enumerate(argv[:-1]) if part == "-e" and argv[i + 1].startswith("@")]
    require(files == (["@" + ACCESS_FILE] if step["password"] else []),
            "a provisioning step reads an unexpected variables file")
    require(step["password"] or ACCESS_FILE not in argv, "unexpected password placeholder")
    if playbooks[0] in PLAYBOOKS:
        require("-K" in argv and f"guest_spec={spec}" in argv, "a host step lost its spec or become prompt")
    else:
        require("-K" not in argv, "a profile pass must not ask for host privilege")
    return step


def steps_for(repo: Path, machine: str, spec: str) -> list[dict]:
    result = subprocess.run([CLI, "--repo", str(repo), "machine", "provision-steps", machine],
                            capture_output=True, text=True, timeout=60, check=False)
    require(result.returncode == 0, (result.stderr.strip() or "provisioning steps unavailable")[:400])
    plan = json.loads(result.stdout)
    require(isinstance(plan, dict) and plan.get("schema") == 1 and plan.get("machine") == machine
            and plan.get("spec") == spec and isinstance(plan.get("steps"), list), "invalid provisioning plan")
    steps = [valid_step(step, spec) for step in plan["steps"]]
    ids = [step["id"] for step in steps]
    require(ids in (list(STEP_IDS[:2]), list(STEP_IDS)), "provisioning steps out of order")
    return steps


def ask_password(machine: str) -> str:
    print(f"\nThe account on {machine} needs a password for the lock screen and the console.")
    print("It is hashed here and never stored; the hash file is deleted after the first pass.")
    for _ in range(3):
        first = getpass.getpass("New password for the Machine account: ")
        second = getpass.getpass("Repeat it: ")
        if first != second:
            print("The passwords differ.")
        elif len(first) < PASSWORD_MIN:
            print(f"Use at least {PASSWORD_MIN} characters.")
        elif "\n" in first or "\r" in first:
            print("The password must be one line.")
        else:
            return first
    raise Refused("no password was confirmed")


def password_hash(password: str) -> str:
    result = subprocess.run([OPENSSL, "passwd", "-6", "-stdin"], input=password + "\n",
                            capture_output=True, text=True, timeout=30, check=False)
    value = result.stdout.strip()
    require(result.returncode == 0 and HASH_RE.fullmatch(value) is not None, "could not hash the password")
    return value


def write_access_file(directory: Path, machine: str, value: str) -> Path:
    path = directory / f"{machine}-access.yml"
    with contextlib.suppress(FileNotFoundError):
        require(stat.S_ISREG(path.lstat().st_mode), "unsafe stale access file")
        path.unlink()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(f"workstation_access_password_hash: '{value}'\n")
    return path


def run_step(repo: Path, argv: list[str]) -> int:
    return subprocess.run([ANSIBLE, *argv[1:]], cwd=repo, check=False).returncode


def main(args: list[str]) -> int:
    os.umask(0o077)
    require(len(args) == 3 and args[0] == "--spec", "usage: privatestack-machine-provision --spec SPEC MACHINE")
    spec, machine = args[1], args[2]
    require(MACHINE_RE.fullmatch(machine) is not None, "invalid Machine id")
    require(spec == f"vm-specs/.generated/{machine}.yml", "the spec is not this Machine's projection")
    repo = checkout()
    require(Path.cwd().resolve() == repo, "provisioning must run in the reviewed checkout")
    steps = steps_for(repo, machine, spec)
    runtime = runtime_dir()

    for number, step in enumerate(steps, 1):
        print(f"\n=== Step {number}/{len(steps)}: {step['label']}", flush=True)
        argv = list(step["argv"])
        access = None
        try:
            if step["password"]:
                password = ask_password(machine)
                try:
                    value = password_hash(password)
                finally:
                    del password
                access = write_access_file(private_dir(runtime), machine, value)
                argv = [part.replace(ACCESS_FILE, str(access)) for part in argv]
            rc = run_step(repo, argv)
        finally:
            if access is not None:
                with contextlib.suppress(FileNotFoundError):
                    access.unlink()
        if rc != 0:
            print(f"\nStep {number} failed (exit {rc}): {step['label']}.")
            print(f"The Machine record and {spec} stay; the remaining steps are in docs/first-machine.md.")
            return rc

    print(f"\n{machine} is provisioned.", flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except (Refused, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"HyperLab provisioning refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
    except (KeyboardInterrupt, EOFError):
        print("\nHyperLab provisioning cancelled.", file=sys.stderr)
        raise SystemExit(130) from None
