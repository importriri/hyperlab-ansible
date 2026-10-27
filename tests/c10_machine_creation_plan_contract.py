#!/usr/bin/env python3
"""C10 creation plan and provisioning steps behind the shell's Create view (ADR 0017).

The provisioning steps are held to docs/first-machine.md twice: by literal
expectations written here, and by the ansible-playbook commands parsed out
of the document itself and compared with what the real `provision-steps`
CLI prints for Machines named as in the document. A projection that is not
exactly what the Machine record projects to is refused before any step.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/hyperlabctl/bin/hyperlabctl"
sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))

from hyperlabctl.errors import ContractError, Unavailable  # noqa: E402
from hyperlabctl.machine_factory import create_from_template, write_projected_vm_spec  # noqa: E402
from hyperlabctl.machine_provision import (  # noqa: E402
    PROFILE_PLAYBOOKS,
    creation_plan,
    guest_key,
    provision_steps,
)
from hyperlabctl.machine_registry import read_machine  # noqa: E402

DOC = ROOT / "docs/first-machine.md"

KEY_RAW = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(32))
KEY_BLOB = base64.b64encode(KEY_RAW).decode()
# What `ssh-keygen -lf` prints for this key, computed here and never by
# the helper under test: unpadded base64 of the SHA-256 of the blob.
KEY_FINGERPRINT = "SHA256:" + base64.b64encode(hashlib.sha256(KEY_RAW).digest()).decode().rstrip("=")
KEY_LINE = f"ssh-ed25519 {KEY_BLOB} sid@nitro"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def refuses(call, kind, text: str) -> None:
    try:
        call()
    except kind as exc:
        require(text in str(exc), f"refused for the wrong reason: {exc}")
    else:
        raise AssertionError(f"accepted what must be refused ({text})")


def prepare(root: Path) -> tuple[Path, Path, Path]:
    repo = root / "repo"
    for name in ("images", "templates"):
        shutil.copytree(ROOT / name, repo / name)
    (repo / "vm-specs").mkdir()
    for path in (repo / "templates").glob("*.md"):
        path.unlink()
    unreviewed = yaml.safe_load((repo / "templates/workstation-dev.yml").read_text())
    unreviewed["id"] = "workstation-unreviewed"
    (repo / "templates/workstation-unreviewed.yml").write_text(yaml.safe_dump(unreviewed, sort_keys=False))
    home = root / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh/hyperlab_ed25519.pub").write_text(KEY_LINE + "\n")
    # A private key beside it must never be read; make it unreadable proof.
    private = home / ".ssh/hyperlab_ed25519"
    private.write_text("PRIVATE")
    private.chmod(0)
    state = root / "state"
    return repo, home, state


def check_plan(repo: Path, home: Path) -> None:
    plan = creation_plan(repo, home=home, cpu_count=8)
    require(plan["schema"] == 1 and plan["host"] == {"vcpus": 8}, f"bad plan header: {plan}")
    require(plan["guest_key"]["available"] and plan["guest_key"]["fingerprint"] == KEY_FINGERPRINT,
            f"guest key not reported: {plan['guest_key']}")
    require("line" not in plan["guest_key"] and KEY_BLOB not in json.dumps(plan),
            "the plan carries key material; the shell needs only the fingerprint")
    by_id = {entry["id"]: entry for entry in plan["templates"]}

    # server-debian is a draft until debian-server carries the agent: a
    # Template that is not ready is never offered for creation.
    require("server-debian" not in by_id, "a draft Template was offered for creation")
    server = by_id["server-arch"]
    require(server["creatable"] and server["provision"] == {"profile_playbook": None, "password": False},
            f"server Template not offered as SSH-only: {server}")
    require(server["custom"] == {"memory_mb_min": 2048, "vcpus_min": 1, "vcpus_max": 8, "disk_gib_min": 2},
            f"custom limits do not come from the image: {server['custom']}")
    require(server["network_profiles"] == ["dev", "services", "lab"] and server["default_network"] == "dev",
            f"networks not from the Template: {server}")
    require(set(server["profiles"]) == {"balanced"} and server["profiles"]["balanced"]["vcpus"] == 4,
            f"profile resolution differs from the factory: {server['profiles']}")
    require(by_id["server-fedora"]["network_profiles"] == ["dev", "lab"], "Fedora allowlist lost")
    require(server["lifecycles"] == ["permanent", "disposable"] and server["default_lifecycle"] == "permanent",
            f"server lifecycles: {server['lifecycles']}")
    require(server["os"] == "Arch Linux" and by_id["server-fedora"]["os"] == "Fedora 44",
            f"the plan does not use the Machine cards' OS label: {server['os']}")

    work = by_id["workstation-dev"]
    require(work["creatable"] and work["provision"]["password"] is True
            and work["provision"]["profile_playbook"] == PROFILE_PLAYBOOKS["workstation-dev"],
            f"workstation does not ask for a password: {work}")
    require(work["custom"]["disk_gib_min"] == 100, "a workstation disk could be smaller than its image")
    require(work["device_capability"] == "vfio", "workstation device lost")

    blocked = by_id["workstation-unreviewed"]
    require(not blocked["creatable"] and "no reviewed profile playbook" in blocked["blocked_reason"],
            f"an unreviewed workstation Template was offered: {blocked}")

    require(creation_plan(repo, home=home, cpu_count=512)["templates"][0]["custom"]["vcpus_max"] == 256,
            "vCPU limit exceeds the factory's")
    refuses(lambda: creation_plan(repo, home=home, cpu_count=0), Unavailable, "CPU count")


def check_key_refusals(root: Path, repo: Path) -> None:
    cases = {
        "missing": None,
        "two keys": KEY_LINE + "\n" + KEY_LINE + "\n",
        "rsa": "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQ== x\n",
        "private": "-----BEGIN OPENSSH PRIVATE KEY-----\n",
        "short": "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIA== x\n",
    }
    for label, content in cases.items():
        home = root / f"home-{label.replace(' ', '-')}"
        (home / ".ssh").mkdir(parents=True)
        if content is not None:
            (home / ".ssh/hyperlab_ed25519.pub").write_text(content)
        plan = creation_plan(repo, home=home, cpu_count=4)
        require(not plan["guest_key"]["available"], f"{label} key accepted")
        require(all(not entry["creatable"] for entry in plan["templates"]),
                f"a Template was creatable without a valid guest key ({label})")
    home = root / "home-link"
    (home / ".ssh").mkdir(parents=True)
    target = root / "elsewhere.pub"
    target.write_text(KEY_LINE)
    (home / ".ssh/hyperlab_ed25519.pub").symlink_to(target)
    refuses(lambda: guest_key(home), Unavailable, "symbolic link")


def check_steps(repo: Path, home: Path, state: Path) -> None:
    runtime = Path("/run/user/1000")
    create_from_template(repo, state_home=state, template_id="server-arch", machine_id="srv-test",
                         owner="sid", created_at="2026-10-04T00:00:00Z",
                         resource_profile="custom", memory_mb=2048, vcpus=2, disk_gib=16)
    refuses(lambda: provision_steps(repo, "srv-test", home=home, runtime_dir=runtime, state_home=state),
            Unavailable, "not projected")
    write_projected_vm_spec(repo, read_machine("srv-test", state_home=state))
    server = provision_steps(repo, "srv-test", home=home, runtime_dir=runtime, state_home=state)
    require([step["id"] for step in server["steps"]] == ["create-domain", "inventory", "close-access"],
            f"server steps differ from docs/first-machine.md: {server}")
    require(server["steps"][2]["argv"] == ["ansible-playbook", "-i", "inventory.ini", "-i",
                                           "/run/user/1000/srv-test.ini", "playbooks/guest-close-access.yml"],
            f"the close-access step differs: {server['steps'][2]}")
    create = server["steps"][0]["argv"]
    require(create[:3] == ["ansible-playbook", "playbooks/vm-create.yml", "-K"]
            and "guest_spec=vm-specs/.generated/srv-test.yml" in create
            and "guest_start_after_create=true" in create, f"create step: {create}")
    keys = json.loads(create[-1])["guest_cloud_init_ssh_public_keys"]
    require(keys == [f"ssh-ed25519 {KEY_BLOB}"], f"the guest got the wrong key or the comment: {keys}")
    require(server["steps"][1]["argv"] == ["ansible-playbook", "playbooks/vm-guest-inventory.yml", "-K",
                                           "-e", "guest_spec=vm-specs/.generated/srv-test.yml"],
            "inventory step differs")

    create_from_template(repo, state_home=state, template_id="workstation-dev", machine_id="dev-test",
                         owner="sid", created_at="2026-10-04T00:00:00Z",
                         looking_glass_mode="linux-experimental")
    write_projected_vm_spec(repo, read_machine("dev-test", state_home=state))
    work = provision_steps(repo, "dev-test", home=home, runtime_dir=runtime, state_home=state)
    ids = [step["id"] for step in work["steps"]]
    require(ids == ["create-domain", "inventory", "profile-first", "profile-second", "close-access"],
            f"steps: {ids}")
    first, second = work["steps"][2], work["steps"][3]
    require(first["password"] is True and second["password"] is False, "password step misplaced")
    require(first["argv"][-2:] == ["-e", "@{access_file}"], f"hash file not a placeholder: {first}")
    require(second["argv"] == first["argv"][:-2], "the second pass differs from the first")
    require(second["argv"][:5] == ["ansible-playbook", "-i", "inventory.ini", "-i", "/run/user/1000/dev-test.ini"]
            and "-K" not in second["argv"], f"profile pass: {second['argv']}")
    require(all("password" not in " ".join(step["argv"]).lower() for step in work["steps"]),
            "a password reached an argument vector")

    refuses(lambda: provision_steps(repo, "../etc", home=home, runtime_dir=runtime, state_home=state),
            ContractError, "invalid Machine id")
    refuses(lambda: provision_steps(repo, "srv-test", home=home, runtime_dir=Path("run"), state_home=state),
            ContractError, "absolute")


def snapshot(repo: Path, state: Path) -> dict[str, object]:
    """Every path below the state home and the VM specs, with mode and bytes."""
    tree: dict[str, object] = {}
    for base in (state, repo / "vm-specs"):
        for path in sorted(base.rglob("*")):
            info = path.lstat()
            content = None
            if path.is_file() and not path.is_symlink():
                content = path.read_bytes() if info.st_mode & 0o400 else info.st_size
            tree[str(path)] = (info.st_mode, content)
    return tree


def check_projection(root: Path, repo: Path, home: Path, state: Path) -> None:
    """Only the projection of the record itself is provisioned.

    Each case changes what stands where the spec goes; the steps are refused
    and the registry and the specs stay exactly as the case left them.
    """
    runtime = Path("/run/user/1000")
    spec = repo / "vm-specs/.generated/srv-test.yml"
    good = spec.read_bytes()
    document = yaml.safe_load(good)

    def edited(change) -> bytes:
        copy = json.loads(json.dumps(document))
        change(copy)
        return b"---\n" + yaml.safe_dump(copy, sort_keys=False).encode()

    def link_to_copy() -> None:
        outside = root / "outside-srv-test.yml"
        outside.write_bytes(good)
        spec.unlink()
        spec.symlink_to(outside)

    def directory() -> None:
        spec.unlink()
        spec.mkdir()

    def unreadable() -> None:
        spec.chmod(0)

    cases = {
        "memory": (lambda: spec.write_bytes(edited(lambda d: d["resources"].__setitem__("memory_mb", 4096))),
                   ContractError, "differs from the projection"),
        "vcpus": (lambda: spec.write_bytes(edited(lambda d: d["resources"].__setitem__("vcpus", 3))),
                  ContractError, "differs from the projection"),
        "device": (lambda: spec.write_bytes(edited(lambda d: d.__setitem__("device_profile", "vfio"))),
                   ContractError, "differs from the projection"),
        "added field": (lambda: spec.write_bytes(edited(lambda d: d.__setitem__("clipboard", True))),
                        ContractError, "differs from the projection"),
        # Equal in Python, not in YAML: true is not 1, 0 is not false and
        # 2048.0 is not 2048. The spec's readers refuse those types.
        "boolean for integer": (lambda: spec.write_bytes(edited(lambda d: d.__setitem__("schema_version", True))),
                                ContractError, "differs from the projection"),
        "integer for boolean": (lambda: spec.write_bytes(edited(lambda d: d.__setitem__("autostart", 0))),
                                ContractError, "differs from the projection"),
        "float for integer": (lambda: spec.write_bytes(edited(
            lambda d: d["resources"].__setitem__("memory_mb", float(d["resources"]["memory_mb"])))),
            ContractError, "differs from the projection"),
        "malformed": (lambda: spec.write_bytes(b"name: [\n"), ContractError, "not one valid YAML document"),
        "repeated key": (lambda: spec.write_bytes(good + b"name: srv-test\n"), ContractError, "duplicate key"),
        "not a mapping": (lambda: spec.write_bytes(b"- srv-test\n"), ContractError, "not a YAML mapping"),
        "link": (link_to_copy, ContractError, "cannot be read"),
        "directory": (directory, ContractError, "not a regular file"),
        "missing": (spec.unlink, Unavailable, "not projected"),
    }
    if os.geteuid() != 0:
        # As root a mode-000 file is readable; the other cases cover root.
        cases["unreadable"] = (unreadable, ContractError, "cannot be read")
    for label, (tamper, kind, text) in cases.items():
        tamper()
        before = snapshot(repo, state)
        try:
            refuses(lambda: provision_steps(repo, "srv-test", home=home, runtime_dir=runtime,
                                            state_home=state), kind, text)
        except AssertionError as exc:
            raise AssertionError(f"projection case {label}: {exc}") from None
        require(snapshot(repo, state) == before, f"projection case {label} changed the registry or a spec")
        if spec.is_dir() and not spec.is_symlink():
            spec.rmdir()
        elif spec.exists() or spec.is_symlink():
            spec.unlink()
        spec.write_bytes(good)
        spec.chmod(0o600)
    require(provision_steps(repo, "srv-test", home=home, runtime_dir=runtime, state_home=state)["machine"]
            == "srv-test", "the restored projection is refused")

    # One vCPU, where `vcpus: true` is equal in Python and wrong in YAML.
    create_from_template(repo, state_home=state, template_id="server-arch", machine_id="srv-one",
                         owner="sid", created_at="2026-10-04T00:00:00Z",
                         resource_profile="custom", memory_mb=2048, vcpus=1, disk_gib=16)
    write_projected_vm_spec(repo, read_machine("srv-one", state_home=state))
    one = repo / "vm-specs/.generated/srv-one.yml"
    projected = one.read_bytes()
    require(provision_steps(repo, "srv-one", home=home, runtime_dir=runtime, state_home=state)["machine"]
            == "srv-one", "a one-vCPU projection is refused")
    for label, change in (("vcpus true for 1", lambda d: d["resources"].__setitem__("vcpus", True)),
                          ("memory_mb 2048.0 for 2048", lambda d: d["resources"].__setitem__("memory_mb", 2048.0))):
        typed = yaml.safe_load(projected)
        change(typed)
        require(typed == yaml.safe_load(projected), f"fixture: {label} is not equal in Python")
        one.write_bytes(b"---\n" + yaml.safe_dump(typed, sort_keys=False).encode())
        before = snapshot(repo, state)
        try:
            refuses(lambda: provision_steps(repo, "srv-one", home=home, runtime_dir=runtime,
                                            state_home=state), ContractError, "differs from the projection")
        except AssertionError as exc:
            raise AssertionError(f"projection case {label}: {exc}") from None
        require(snapshot(repo, state) == before, f"projection case {label} changed the registry or a spec")
    one.write_bytes(projected)

    # A workstation Template without a reviewed profile playbook is refused
    # even when its Machine was recorded and projected.
    create_from_template(repo, state_home=state, template_id="workstation-unreviewed",
                         machine_id="dev-unrev", owner="sid", created_at="2026-10-04T00:00:00Z",
                         looking_glass_mode="linux-experimental")
    write_projected_vm_spec(repo, read_machine("dev-unrev", state_home=state))
    before = snapshot(repo, state)
    refuses(lambda: provision_steps(repo, "dev-unrev", home=home, runtime_dir=runtime, state_home=state),
            ContractError, "no reviewed profile playbook")
    require(snapshot(repo, state) == before, "an unreviewed workstation changed the registry or a spec")


def doc_commands(section_titles: tuple[str, ...]) -> list[list[str]]:
    """The ansible-playbook commands of the named sections, in document order."""
    text = DOC.read_text(encoding="utf-8")
    sections = re.split(r"^## ", text, flags=re.MULTILINE)
    commands = []
    for title in section_titles:
        matches = [body for body in sections if body.split("\n", 1)[0].strip() == title]
        require(len(matches) == 1, f"docs/first-machine.md has no single section {title!r}")
        for block in re.findall(r"^```bash\n(.*?)^```", matches[0], flags=re.MULTILINE | re.DOTALL):
            for line in block.replace("\\\n", " ").splitlines():
                argv = shlex.split(line)
                if argv and argv[0] == "ansible-playbook":
                    commands.append(argv)
    return commands


def shape(argv: list[str]) -> tuple[str, bool, list[str], list[object]]:
    """What a playbook run means: playbook, become prompt, inventories, extra vars."""
    require(argv[0] == "ansible-playbook", f"not a playbook run: {argv}")
    playbook, become, inventories, extra = None, False, [], []
    index = 1
    while index < len(argv):
        part = argv[index]
        if part == "-K":
            become = True
        elif part in ("-i", "-e"):
            value = argv[index + 1]
            index += 1
            if part == "-i":
                inventories.append(value)
            else:
                extra.append(json.loads(value) if value.startswith("{") else value)
        else:
            require(not part.startswith("-") and playbook is None, f"unexpected argument {part!r} in {argv}")
            playbook = part
        index += 1
    require(playbook is not None, f"no playbook in {argv}")
    return playbook, become, inventories, extra


def documented(argv: list[str], machine: str, runtime: str, key: str) -> tuple:
    """A documented command with the shell's spellings replaced by values."""
    playbook, become, inventories, extra = shape(argv)
    inventories = [value.replace("/run/user/$UID/", runtime + "/") for value in inventories]
    values: list[object] = []
    for value in extra:
        if value == f"@/run/user/$UID/{machine}-access.yml":
            value = "@{access_file}"
        elif isinstance(value, dict):
            # The document hands over the whole key file; the provisioner
            # hands over type and key only, the comment stays on the host.
            keys = value.get("guest_cloud_init_ssh_public_keys")
            require(keys == ["$(command cat ~/.ssh/hyperlab_ed25519.pub)"],
                    f"the documented key argument changed: {value}")
            value = {"guest_cloud_init_ssh_public_keys": [key]}
        values.append(value)
    return playbook, become, inventories, values


def check_docs(repo: Path, home: Path, state: Path) -> None:
    """The real provision-steps CLI prints the documented commands, in order."""
    runtime = "/run/user/4242"
    env = {**os.environ, "HOME": str(home), "XDG_STATE_HOME": str(state),
           "XDG_RUNTIME_DIR": runtime, "PYTHONDONTWRITEBYTECODE": "1"}
    create_from_template(repo, state_home=state, template_id="server-arch", machine_id="srv-01",
                         owner="sid", created_at="2026-10-04T00:00:00Z",
                         resource_profile="custom", memory_mb=2048, vcpus=2, disk_gib=16)
    create_from_template(repo, state_home=state, template_id="workstation-dev", machine_id="dev-01",
                         owner="sid", created_at="2026-10-04T00:00:00Z",
                         looking_glass_mode="linux-experimental")
    for machine in ("srv-01", "dev-01"):
        write_projected_vm_spec(repo, read_machine(machine, state_home=state))
    key = f"ssh-ed25519 {KEY_BLOB}"

    def steps(machine: str) -> list[dict]:
        result = subprocess.run([str(CLI), "--repo", str(repo), "machine", "provision-steps", machine],
                                text=True, capture_output=True, check=False, env=env)
        require(result.returncode == 0, result.stderr + result.stdout)
        plan = json.loads(result.stdout)
        require(plan["machine"] == machine and plan["spec"] == f"vm-specs/.generated/{machine}.yml",
                f"plan header: {plan}")
        return plan["steps"]

    server = steps("srv-01")
    docs = doc_commands(("A server Machine",))
    require([shape(step["argv"]) for step in server]
            == [documented(argv, "srv-01", runtime, key) for argv in docs],
            f"server steps differ from docs/first-machine.md:\n{server}\n{docs}")
    require([step["id"] for step in server] == ["create-domain", "inventory", "close-access"],
            f"server step ids: {server}")

    work = steps("dev-01")
    docs = doc_commands(("2. The domain", "3. The rice"))
    require([shape(step["argv"]) for step in work]
            == [documented(argv, "dev-01", runtime, key) for argv in docs],
            f"workstation steps differ from docs/first-machine.md:\n{work}\n{docs}")
    require([step["id"] for step in work]
            == ["create-domain", "inventory", "profile-first", "profile-second", "close-access"],
            f"workstation step ids: {work}")
    # Independent of the document: the hash file goes to the first pass only.
    require([step["password"] for step in work] == [False, False, True, False, False]
            and [step["argv"].count("@{access_file}") for step in work] == [0, 0, 1, 0, 0],
            f"the hash file is not the first profile pass's alone: {work}")
    require(work[3]["argv"] == ["ansible-playbook", "-i", "inventory.ini", "-i", f"{runtime}/dev-01.ini",
                                PROFILE_PLAYBOOKS["workstation-dev"]],
            f"second profile pass: {work[3]}")
    require(work[4]["argv"] == ["ansible-playbook", "-i", "inventory.ini", "-i", f"{runtime}/dev-01.ini",
                                "playbooks/guest-close-access.yml"],
            f"close-access step: {work[4]}")


def check_cli(repo: Path, home: Path, state: Path) -> None:
    env = {**os.environ, "HOME": str(home), "XDG_STATE_HOME": str(state),
           "XDG_RUNTIME_DIR": "/run/user/4242", "PYTHONDONTWRITEBYTECODE": "1"}

    def run(*args: str) -> dict:
        result = subprocess.run([str(CLI), "--repo", str(repo), "machine", *args], text=True,
                                capture_output=True, check=False, env=env)
        require(result.returncode == 0, result.stderr + result.stdout)
        return json.loads(result.stdout)

    plan = run("create-plan")
    require(plan["guest_key"]["available"] and plan["host"]["vcpus"] == (os.cpu_count() or 0),
            f"CLI plan: {plan['guest_key']}")
    steps = run("provision-steps", "srv-test")
    require(steps["steps"][0]["argv"][1] == "playbooks/vm-create.yml", "CLI steps")
    steps = run("provision-steps", "dev-test")
    require(steps["steps"][3]["argv"][4] == "/run/user/4242/dev-test.ini",
            "the inventory path does not follow XDG_RUNTIME_DIR")


def main() -> int:
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        repo, home, state = prepare(root)
        check_plan(repo, home)
        check_key_refusals(root, repo)
        check_steps(repo, home, state)
        check_projection(root, repo, home, state)
        check_docs(repo, home, state)
        check_cli(repo, home, state)
        (home / ".ssh/hyperlab_ed25519").chmod(0o600)
    print("C10 Machine creation plan contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
