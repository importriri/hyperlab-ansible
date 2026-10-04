#!/usr/bin/env python3
"""Re-receipt after a manifest policy change (ADR 0024).

The real official-checksum tool runs against checksum files shaped like
Arch's, Debian's and Fedora's; the role is checked for what it may touch:
the base is only read, only the receipt is rewritten, and nothing happens
without the exact image name.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/official_checksum.py"
TASKS = ROOT / "roles/image_factory/tasks/rereceipt.yml"
NAME = "debian-13-genericcloud-amd64-20261001-2618.qcow2"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def run(checksums: str, artifact: bytes, basename: str = NAME, link: bool = False) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        (base / "sums").write_text(checksums)
        target = base / "base.qcow2"
        target.write_bytes(artifact)
        if link:
            alias = base / "alias.qcow2"
            alias.symlink_to(target)
            target = alias
        result = subprocess.run([sys.executable, str(TOOL), "--checksums", str(base / "sums"),
                                 "--basename", basename, "--artifact", str(target)],
                                capture_output=True, text=True, check=False)
        return result.returncode, result.stdout + result.stderr


def tool_cases() -> None:
    data = b"sealed upstream artefact"
    sha256 = hashlib.sha256(data).hexdigest()
    sha512 = hashlib.sha512(data).hexdigest()
    other = hashlib.sha512(b"another file").hexdigest()

    debian = f"{other}  debian-13-azure-amd64-20261001-2618.json\n{sha512}  {NAME}\n"
    rc, out = run(debian, data)
    require(rc == 0 and json.loads(out)["algorithm"] == "sha512", f"Debian SHA512SUMS not accepted: {out}")

    rc, out = run(f"{sha256}  {NAME}\n", data)
    require(rc == 0 and json.loads(out)["algorithm"] == "sha256", f"Arch .SHA256 not accepted: {out}")

    fedora = ("-----BEGIN PGP SIGNED MESSAGE-----\nHash: SHA256\n\n"
              f"# {NAME}: 24 bytes\nSHA256 ({NAME}) = {sha256}\n"
              "-----BEGIN PGP SIGNATURE-----\nabc\n-----END PGP SIGNATURE-----\n")
    rc, out = run(fedora, data)
    require(rc == 0 and json.loads(out)["digest"] == sha256, f"Fedora CHECKSUM not accepted: {out}")

    for checksums, artifact, reason in (
        (f"{sha512}  {NAME}\n", b"a changed file", "does not match"),
        (f"{other}  another.qcow2\n", data, "no entry"),
        (f"{sha512}  {NAME}\n{sha256}  {NAME}\n", data, "conflicting"),
        (f"SHA256 ({NAME}) = {sha512}\n", data, "malformed"),
    ):
        rc, out = run(checksums, artifact)
        require(rc == 2 and reason in out, f"accepted a checksum file that must refuse ({reason}): {out}")
    rc, out = run(f"{sha256}  {NAME}\n", data, basename="../" + NAME)
    require(rc == 2, "a path was accepted as the expected basename")
    rc, out = run(f"{sha256}  {NAME}\n", data, link=True)
    require(rc == 2, "a redirected artefact was checked")


def role_cases() -> None:
    tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
    names = [task["name"] for task in tasks]
    gate = tasks[names.index("Require the exact image name, a sealed official image and its base")]
    that = gate["ansible.builtin.assert"]["that"]
    for condition in ("image_factory_confirm_rereceipt == image_factory_plan.id",
                      "image_factory_plan.manifest_status == 'sealed'",
                      "image_factory_plan.source_type == 'official-cloud'",
                      "image_factory_plan.manifest_artifact_sha256 == image_factory_plan.source_sha256"):
        require(condition in that, f"the re-receipt gate lost: {condition}")
    require(names.index("Require the exact image name, a sealed official image and its base")
            < names.index("Acquire the per-image factory lock"), "the lock is taken before the confirmation")

    work = tasks[names.index("Check the base and rewrite only the receipt while holding the lock")]
    steps = [task["name"] for task in work["block"]]
    order = ["Inspect the committed base as the source it was downloaded as",
             "Refuse a base that is not the pinned download",
             "Fetch the vendor's checksum file again",
             "Check the base against the vendor's own checksum",
             "Render the re-issued receipt beside the current one",
             "Replace the receipt atomically",
             "Validate the image against its new receipt"]
    require([step for step in steps if step in order] == order, f"re-receipt steps out of order: {steps}")

    text = TASKS.read_text(encoding="utf-8")
    writes = []
    for task in work["block"] + work["rescue"]:
        if "ansible.builtin.command" in task and task["ansible.builtin.command"]["argv"][0].endswith("mv_bin }}"):
            writes.append(task["ansible.builtin.command"]["argv"][-1])
        if "ansible.builtin.template" in task:
            writes.append(task["ansible.builtin.template"]["dest"])
        if task.get("ansible.builtin.file", {}).get("state") == "absent":
            writes.append(task["ansible.builtin.file"]["path"])
    require(set(writes) == {"{{ image_factory_plan.receipt_new_path }}", "{{ image_factory_plan.receipt_path }}"},
            f"re-receipt writes outside the receipt: {writes}")
    require("rmtree" not in text and "image_factory_plan.cache_" not in text,
            "re-receipt reaches beyond base and receipt")
    always = [task["name"] for task in work["always"]]
    require("Release the per-image factory lock" in always and "Remove the checksum workspace" in always,
            "the lock or the workspace can outlive a failure")


def wiring_cases() -> None:
    defaults = yaml.safe_load((ROOT / "roles/image_factory/defaults/main.yml").read_text())
    require("rereceipt" in defaults["image_factory_supported_operations"], "rereceipt is not a supported operation")
    main = (ROOT / "roles/image_factory/tasks/main.yml").read_text(encoding="utf-8")
    require("'validate' if image_factory_operation == 'rereceipt'" in main,
            "re-receipt does not plan exactly what validation plans")
    require("ansible.builtin.include_tasks: rereceipt.yml" in main, "the operation is not dispatched")
    group = yaml.safe_load((ROOT / "group_vars/all/image-factory.yml").read_text())
    require(group["image_factory_confirm_rereceipt"] == "", "the confirmation has a default")
    playbook = yaml.safe_load((ROOT / "playbooks/image-rereceipt.yml").read_text())
    require(playbook[0]["vars"]["image_factory_operation"] == "rereceipt" and playbook[0]["become"] is True,
            "the playbook does not run the re-receipt operation")


def main() -> int:
    tool_cases()
    role_cases()
    wiring_cases()
    print("Image re-receipt contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
