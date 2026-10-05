#!/usr/bin/env python3
"""C10 creation plan and provisioning steps behind the shell's Create view (ADR 0017)."""

from __future__ import annotations

import base64
import json
import os
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

KEY_BLOB = base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(32))).decode()
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
    require(plan["guest_key"]["available"] and plan["guest_key"]["fingerprint"].startswith("SHA256:"),
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
    refuses(lambda: guest_key(home), Unavailable, "missing")


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
        check_cli(repo, home, state)
        (home / ".ssh/hyperlab_ed25519").chmod(0o600)
    print("C10 Machine creation plan contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
