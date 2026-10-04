#!/usr/bin/env python3
"""A manifest's QEMU Guest Agent claim is checked inside the image.

Debian 13 genericcloud was sealed with supports.qemu_guest_agent: true while
the image carried no agent, and the first Machine from it could not have its
SSH host key pinned. The real inspection tool runs here against a fake
guestfish that answers like an image with or without the agent.
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/image_guest_agent.py"
VALIDATE = ROOT / "roles/image_factory/tasks/validate.yml"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def load():
    spec = importlib.util.spec_from_file_location("image_guest_agent", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fake_guestfish(directory: Path, present: set[str]) -> Path:
    """Answer each is-file-opts line from the given set; log argv and env."""
    path = directory / "guestfish"
    path.write_text(f"""#!/usr/bin/python3
import json, os, sys
present = {sorted(present)!r}
with open({str(directory / 'call.json')!r}, "w") as log:
    json.dump({{"argv": sys.argv[1:], "backend": os.environ.get("LIBGUESTFS_BACKEND")}}, log)
for line in sys.stdin:
    if line.startswith("is-file-opts "):
        print("true" if line.split()[1] in present else "false")
""")
    path.chmod(0o755)
    return path


def run_tool(present: set[str]) -> tuple[int, dict | None, dict]:
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        image = directory / "image.qcow2"
        image.write_bytes(b"qcow2 fixture")
        guestfish = fake_guestfish(directory, present)
        result = subprocess.run([sys.executable, str(TOOL), "--image", str(image), "--guestfish", str(guestfish)],
                                capture_output=True, text=True, check=False)
        call = json.loads((directory / "call.json").read_text())
        return result.returncode, json.loads(result.stdout) if result.returncode == 0 else None, call


def tool_cases() -> None:
    tool = load()
    rc, answer, call = run_tool({"/usr/sbin/qemu-ga", "/lib/systemd/system/qemu-guest-agent.service"})
    require(rc == 0 and answer["qemu_guest_agent"] is True and answer["binary"] == "/usr/sbin/qemu-ga",
            f"an image with the agent was not recognised: {answer}")
    require(call["argv"][:3] == ["--ro", "--format=qcow2", "-a"] and "-i" in call["argv"]
            and "--rw" not in call["argv"] and call["backend"] == "direct",
            f"the image was not opened read-only through the direct backend: {call}")
    rc, answer, _ = run_tool(set())
    require(rc == 0 and answer["qemu_guest_agent"] is False,
            "Debian genericcloud (no agent) was not reported as lacking it")
    rc, answer, _ = run_tool({"/usr/bin/qemu-ga"})
    require(rc == 0 and answer["qemu_guest_agent"] is False, "a binary without its unit counted as the agent")
    for broken in ("", "true\n", "yes\nno\nyes\nno\n"):
        try:
            tool.evaluate(broken)
        except ValueError:
            continue
        raise AssertionError(f"a malformed guestfish answer was accepted: {broken!r}")
    with tempfile.TemporaryDirectory() as temporary:
        link = Path(temporary) / "link.qcow2"
        link.symlink_to("/etc/hostname")
        result = subprocess.run([sys.executable, str(TOOL), "--image", str(link)],
                                capture_output=True, text=True, check=False)
        require(result.returncode == 2, "a redirected image path was inspected")


def role_cases() -> None:
    tasks = yaml.safe_load(VALIDATE.read_text(encoding="utf-8"))
    names = [task["name"] for task in tasks]
    claim = names.index("Read the guest agent claim of a Linux image manifest")
    inspect = names.index("Look inside the image for the QEMU Guest Agent it claims")
    require(names.index("Verify the base and receipt against the current manifest policy") < claim < inspect
            < names.index("Publish validated image evidence"),
            "the agent check does not run as part of validation")
    block = tasks[inspect]
    require("image_factory_claims_guest_agent | bool" in block["when"], "the check is not tied to the claim")
    inner = {task["name"]: task for task in block["block"]}
    require("Refuse to trust a guest agent claim that cannot be checked" in inner,
            "a missing libguestfs would skip the check")
    refusal = inner["Refuse an image whose manifest claims an agent it does not carry"]
    require("qemu_guest_agent" in refusal["ansible.builtin.assert"]["that"][0], "the refusal does not read the answer")
    prepare = (ROOT / "roles/image_factory/tasks/prepare.yml").read_text(encoding="utf-8")
    require(prepare.count("ansible.builtin.include_tasks: validate.yml") >= 2,
            "a new seal no longer passes through validation")


def manifest_cases() -> None:
    debian = yaml.safe_load((ROOT / "images/debian.yml").read_text())
    require(debian["supports"]["qemu_guest_agent"] is False,
            "the upstream Debian genericcloud image claims an agent it does not carry")
    server = yaml.safe_load((ROOT / "images/debian-server.yml").read_text())
    require(server["supports"]["qemu_guest_agent"] is True and server["status"] != "sealed",
            "debian-server must claim the agent and be sealed only after the check")
    template = yaml.safe_load((ROOT / "templates/server-debian.yml").read_text())
    require(template["image"] == "debian-server" and template["status"] == "draft",
            "server-debian is offered without an image that carries the agent")


def main() -> int:
    os.umask(0o022)
    tool_cases()
    role_cases()
    manifest_cases()
    print("Image guest agent contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
