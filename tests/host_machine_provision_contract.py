#!/usr/bin/env python3
"""Behavioural contract for the reviewed Machine provisioner (ADR 0017).

The real provisioner runs against fake hyperlabctl and ansible-playbook
programs and the real openssl. Nothing touches libvirt, sudo or a guest.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import stat
import tempfile
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "roles/host_desktop_common/files/privatestack-machine-provision.py"
SECRET = "correct horse battery"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def load():
    spec = importlib.util.spec_from_file_location("machine_provision", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def steps(machine: str, workstation: bool) -> dict:
    spec = f"vm-specs/.generated/{machine}.yml"
    result = [
        {"id": "create-domain", "label": "Create", "password": False,
         "argv": ["ansible-playbook", "playbooks/vm-create.yml", "-K", "-e", f"guest_spec={spec}",
                  "-e", "guest_start_after_create=true", "-e", '{"guest_cloud_init_ssh_public_keys":["k"]}']},
        {"id": "inventory", "label": "Inventory", "password": False,
         "argv": ["ansible-playbook", "playbooks/vm-guest-inventory.yml", "-K", "-e", f"guest_spec={spec}"]},
    ]
    if workstation:
        profile = ["ansible-playbook", "-i", "inventory.ini", "-i", f"/run/user/1/{machine}.ini",
                   "playbooks/guest-arch-dev-vfio.yml"]
        result += [
            {"id": "profile-first", "label": "Profile", "password": True,
             "argv": [*profile, "-e", "@{access_file}"]},
            {"id": "profile-second", "label": "Profile again", "password": False, "argv": profile},
        ]
    result.append({"id": "close-access", "label": "Close", "password": False,
                   "argv": ["ansible-playbook", "-i", "inventory.ini", "-i", f"/run/user/1/{machine}.ini",
                            "playbooks/guest-close-access.yml"]})
    return {"schema": 1, "machine": machine, "spec": spec, "steps": result}


def fixture(base: Path, plan: dict, fail_step: str = "") -> tuple[Path, Path]:
    repo = base / "repo"
    repo.mkdir()
    bin_dir = base / "bin"
    bin_dir.mkdir()
    log = base / "calls.jsonl"
    (base / "plan.json").write_text(json.dumps(plan))
    cli = bin_dir / "hyperlabctl"
    cli.write_text(f"#!/bin/sh\ncat {base / 'plan.json'}\n")
    ansible = bin_dir / "ansible-playbook"
    # Records argv and, for an @file argument, whether the file is private
    # and what it holds at the moment the playbook runs.
    ansible.write_text(f"""#!/usr/bin/python3
import json, os, stat, sys
entry = {{"argv": sys.argv[1:]}}
for part in sys.argv[1:]:
    if part.startswith("@"):
        info = os.lstat(part[1:])
        entry["file_mode"] = stat.S_IMODE(info.st_mode)
        entry["file"] = open(part[1:]).read()
with open({str(log)!r}, "a") as stream:
    stream.write(json.dumps(entry) + "\\n")
sys.exit(3 if {fail_step!r} and {fail_step!r} in " ".join(sys.argv) else 0)
""")
    for program in (cli, ansible):
        program.chmod(0o755)
    return repo, log


def run(module, base: Path, plan: dict, args: list[str], *, passwords=None, fail_step=""):
    repo, log = fixture(base, plan, fail_step)
    pointer = base / "pointer"
    pointer.write_text(str(repo))
    runtime = base / "runtime"
    runtime.mkdir(mode=0o700)
    answers = iter(passwords or [])
    module.CLI = str(base / "bin/hyperlabctl")
    module.ANSIBLE = str(base / "bin/ansible-playbook")
    module.POINTER = pointer
    previous = Path.cwd()
    os.chdir(repo)
    output = io.StringIO()
    try:
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime)}), \
                patch.object(module.getpass, "getpass", lambda prompt="": next(answers)), \
                contextlib.redirect_stdout(output):
            try:
                rc = module.main(args)
            except module.Refused as exc:
                rc = "refused: " + str(exc)
    finally:
        os.chdir(previous)
    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return rc, calls, runtime, output.getvalue()


def main() -> int:
    module = load()

    with tempfile.TemporaryDirectory() as temp:
        rc, calls, runtime, _ = run(module, Path(temp), steps("srv-a", False),
                                    ["--spec", "vm-specs/.generated/srv-a.yml", "srv-a"])
        require(rc == 0, f"server provisioning failed: {rc}")
        require([call["argv"][0] for call in calls[:2]] == ["playbooks/vm-create.yml", "playbooks/vm-guest-inventory.yml"]
                and len(calls) == 3 and calls[2]["argv"][-1] == "playbooks/guest-close-access.yml",
                f"server steps ran out of order: {calls}")
        require(not (runtime / "hyperlab/provision").exists(), "a server asked for a password")

    with tempfile.TemporaryDirectory() as temp:
        rc, calls, runtime, output = run(module, Path(temp), steps("dev-a", True),
                                         ["--spec", "vm-specs/.generated/dev-a.yml", "dev-a"],
                                         passwords=[SECRET, SECRET])
        require(rc == 0, f"workstation provisioning failed: {rc}")
        require(len(calls) == 5 and calls[4]["argv"][-1] == "playbooks/guest-close-access.yml",
                f"workstation steps: {calls}")
        first = calls[2]
        require(first.get("file_mode") == 0o600, f"hash file not private: {first}")
        value = first["file"].split("'")[1]
        require(first["file"].startswith("workstation_access_password_hash: '")
                and module.HASH_RE.fullmatch(value), f"hash file content: {first['file']!r}")
        require(SECRET not in json.dumps(calls) and SECRET not in output, "the password leaked")
        require("@{access_file}" not in json.dumps(calls), "placeholder reached ansible")
        directory = runtime / "hyperlab/provision"
        require(stat.S_IMODE(directory.stat().st_mode) == 0o700 and not list(directory.iterdir()),
                "the hash file outlived the first pass")
        require("file" not in calls[3], "the second pass read the hash")

    with tempfile.TemporaryDirectory() as temp:
        rc, calls, runtime, _ = run(module, Path(temp), steps("dev-b", True),
                                    ["--spec", "vm-specs/.generated/dev-b.yml", "dev-b"],
                                    passwords=[SECRET, SECRET], fail_step="guest-arch-dev-vfio.yml -e")
        require(rc == 3 and len(calls) == 3, f"a failed profile pass did not stop: {rc} {calls}")
        require(not list((runtime / "hyperlab/provision").iterdir()), "a failed pass left the hash file")

    with tempfile.TemporaryDirectory() as temp:
        rc, calls, _, _ = run(module, Path(temp), steps("srv-b", False),
                              ["--spec", "vm-specs/.generated/srv-b.yml", "srv-b"], fail_step="vm-create")
        require(rc == 3 and len(calls) == 1, "a failed domain creation did not stop provisioning")

    with tempfile.TemporaryDirectory() as temp:
        rc, calls, _, _ = run(module, Path(temp), steps("dev-c", True),
                              ["--spec", "vm-specs/.generated/dev-c.yml", "dev-c"],
                              passwords=["one-password", "two-password", "short", "short",
                                         SECRET, SECRET + "x"])
        require(isinstance(rc, str) and "no password" in rc and len(calls) == 2,
                f"unconfirmed passwords were accepted: {rc}")

    def tampered(change) -> dict:
        plan = steps("dev-t", True)
        change(plan)
        return plan

    refusals = {
        "unreviewed playbook": tampered(lambda p: p["steps"][1]["argv"].__setitem__(1, "playbooks/lab.yml")),
        "variables file": tampered(lambda p: p["steps"][0]["argv"].extend(["-e", "@/etc/shadow"])),
        "become prompt": tampered(lambda p: p["steps"][0]["argv"].remove("-K")),
        "host privilege": tampered(lambda p: p["steps"][3]["argv"].append("-K")),
        "order": tampered(lambda p: p["steps"].reverse()),
        "close-access early": tampered(lambda p: p["steps"].insert(2, p["steps"].pop())),
        "close-access as a profile": tampered(lambda p: p["steps"][2]["argv"].__setitem__(
            5, "playbooks/guest-close-access.yml")),
        "close-access dropped": tampered(lambda p: p["steps"].pop()),
        "another spec": tampered(lambda p: p.__setitem__("spec", "vm-specs/arch-dev.yml")),
        "another binary": tampered(lambda p: p["steps"][0]["argv"].__setitem__(0, "bash")),
        "placeholder": tampered(lambda p: p["steps"][1]["argv"].append("{access_file}")),
    }
    for label, plan in refusals.items():
        with tempfile.TemporaryDirectory() as temp:
            rc, calls, _, _ = run(module, Path(temp), plan,
                                  ["--spec", "vm-specs/.generated/dev-t.yml", "dev-t"], passwords=[SECRET] * 2)
            require(isinstance(rc, str) and rc.startswith("refused") and not calls,
                    f"tampered steps ({label}) ran: {rc} {calls}")

    for args in (["--spec", "vm-specs/arch-dev.yml", "dev-t"], ["dev-t"],
                 ["--spec", "vm-specs/.generated/../x.yml", "../x"]):
        with tempfile.TemporaryDirectory() as temp:
            rc, calls, _, _ = run(module, Path(temp), steps("dev-t", True), args)
            require(isinstance(rc, str) and not calls, f"bad arguments accepted: {args}")

    source = SOURCE.read_text(encoding="utf-8")
    require("shell=True" not in source and "--become-password" not in source,
            "the provisioner gained a shell or cached the become password")
    print("HyperLab Machine provisioner contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
