#!/usr/bin/env python3
"""Behaviour contract for the Workbench (docs/adr/0015-golden-image-capture.md).

tools/workbench.py runs against recording stand-ins for virsh, qemu-img,
virt-sysprep and guestfish, in a temporary root and repository, so every
assertion is about what the Workbench refuses, what it writes and what it
leaves behind:

  1. adoption is explicit, unique per domain and per image id, and never
     reuses the id of an existing image manifest;
  2. a seal refuses a running domain, a domain with more than one disk and a
     generalized copy the leftover scan does not pass, and a refused seal
     leaves no staging behind;
  3. a seal only ever reads the source disk, generalizes the copy with every
     ordinary user account removed by the guest's userdel, and renders a schema-valid local-import manifest
     with the digest of the staged image;
  4. the scan recognises each kind of leftover it promises to catch;
  5. release removes the record and its staging;
  6. the playbooks run privileged, keep staging private, never overwrite an
     image manifest and register the brick behind the image store.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/workbench.py"
sys.path.insert(0, str(ROOT / "tools"))
import workbench  # noqa: E402

FAKE = r'''#!/usr/bin/env python3
import json, os, shutil, sys
name = os.path.basename(sys.argv[0])
log = os.environ["FAKE_LOG"]
with open(log, "a") as handle:
    handle.write(json.dumps([name] + sys.argv[1:]) + "\n")
if name == "virsh":
    if "domstate" in sys.argv:
        print(os.environ.get("FAKE_DOMSTATE", "shut off"))
    elif "domblklist" in sys.argv:
        print(" Type   Device   Target   Source")
        print("------------------------------------------")
        for disk in os.environ["FAKE_DISKS"].split(","):
            print(f" file   disk     vda      {disk}")
        print(" file   cdrom    sda      -")
elif name == "qemu-img":
    if sys.argv[1] == "convert":
        shutil.copyfile(sys.argv[-2], sys.argv[-1])
    elif sys.argv[1] == "info":
        print(json.dumps({"format": "qcow2", "virtual-size": 107374182400}))
elif name == "virt-sysprep":
    # The real tool refuses a --format given after the -a it should apply to.
    if "--format" in sys.argv and sys.argv.index("--format") > sys.argv.index("-a"):
        print("virt-sysprep: error: --format parameter must appear before -a parameter", file=sys.stderr)
        sys.exit(1)
    image = sys.argv[sys.argv.index("-a") + 1]
    with open(image, "ab") as handle:
        handle.write(b"generalized")
elif name == "guestfish":
    sys.stdin.read()
    print(open(os.environ["FAKE_SCAN"]).read(), end="")
'''

CLEAN_SCAN = """@@home
@@root
.bashrc
@@machine-id

@@ssh-hostkeys
@@cloud-instances
@@sudoers-cloud-init
false
@@passwd
root:x:0:0::/root:/bin/bash
nobody:x:65534:65534:Kernel Overflow User:/:/usr/bin/nologin
"""


class Lab:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.root = base / "workbench"
        self.repo = base / "repo"
        (self.repo / "images").mkdir(parents=True)
        (self.repo / "images/arch.yml").write_text((ROOT / "images/arch.yml").read_text())
        self.bin = base / "bin"
        self.bin.mkdir()
        for name in ("virsh", "qemu-img", "virt-sysprep", "guestfish"):
            path = self.bin / name
            path.write_text(FAKE)
            path.chmod(0o755)
        self.disk = base / "domains/arch-dev-vfio.qcow2"
        self.disk.parent.mkdir()
        self.disk.write_bytes(b"source-disk")
        self.log = base / "tools.log"
        self.scan = base / "scan.txt"
        self.scan.write_text(CLEAN_SCAN)
        self.env = {
            "PATH": f"{self.bin}:{os.environ.get('PATH', '/usr/bin')}",
            "FAKE_LOG": str(self.log),
            "FAKE_SCAN": str(self.scan),
            "FAKE_DISKS": str(self.disk),
            "FAKE_DOMSTATE": "shut off",
        }

    def run(self, *args: str, ok: bool = True) -> dict | str:
        result = subprocess.run(
            [sys.executable, str(TOOL), "--root", str(self.root), *args],
            capture_output=True, text=True, timeout=30, env=self.env, check=False,
        )
        if ok:
            assert result.returncode == 0, (args, result.stderr)
            return json.loads(result.stdout)
        assert result.returncode == 2, (args, result.returncode, result.stdout)
        assert result.stderr.startswith("workbench: "), result.stderr
        return result.stderr

    def adopt(self, domain: str = "arch-dev-vfio", image: str = "arch-dev-20261003", ok: bool = True):
        return self.run("adopt", "--repo", str(self.repo), "--domain", domain,
                        "--image-id", image, "--base-image", "arch", "--profile", "dev",
                        "--by", "sid", ok=ok)

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]


def check_adoption(lab: Lab) -> None:
    record = lab.adopt()
    assert record["state"] == "candidate" and record["adopted_by"] == "sid"
    path = lab.root / "registry/arch-dev-vfio.json"
    assert oct(path.stat().st_mode & 0o777) == "0o644"
    assert "already in the Workbench" in lab.adopt(ok=False)
    assert "already taken" in lab.adopt(domain="arch-dev", ok=False)
    assert "never replaced" in lab.adopt(domain="arch-dev", image="arch", ok=False)
    assert "invalid domain" in lab.adopt(domain="Bad Name", image="x-1", ok=False)
    listing = lab.run("list")
    assert [item["domain"] for item in listing["candidates"]] == ["arch-dev-vfio"]


def check_refusals(lab: Lab) -> None:
    lab.env["FAKE_DOMSTATE"] = "running"
    assert "must be shut off" in lab.run("seal", "--repo", str(lab.repo), "--domain", "arch-dev-vfio", ok=False)
    lab.env["FAKE_DOMSTATE"] = "shut off"

    lab.env["FAKE_DISKS"] = f"{lab.disk},{lab.disk}"
    assert "exactly one file disk" in lab.run("seal", "--repo", str(lab.repo), "--domain", "arch-dev-vfio", ok=False)
    lab.env["FAKE_DISKS"] = str(lab.disk)

    lab.scan.write_text(CLEAN_SCAN.replace("@@home\n", "@@home\nsid\n"))
    message = lab.run("seal", "--repo", str(lab.repo), "--domain", "arch-dev-vfio", ok=False)
    assert "home directories remain: sid" in message, message
    assert not (lab.root / "staging/arch-dev-20261003").exists(), "a refused seal left staging behind"
    assert lab.run("show", "--domain", "arch-dev-vfio")["state"] == "candidate"
    lab.scan.write_text(CLEAN_SCAN)
    assert "not in the Workbench" in lab.run("seal", "--repo", str(lab.repo), "--domain", "arch-dev", ok=False)


def check_seal(lab: Lab) -> None:
    before = hashlib.sha256(lab.disk.read_bytes()).hexdigest()
    lab.log.write_text("")
    result = lab.run("seal", "--repo", str(lab.repo), "--domain", "arch-dev-vfio")
    assert hashlib.sha256(lab.disk.read_bytes()).hexdigest() == before, "the source disk changed"

    staged = Path(result["staged_image"])
    assert staged.is_file() and oct(staged.stat().st_mode & 0o777) == "0o600"
    assert result["sha256"] == hashlib.sha256(staged.read_bytes()).hexdigest()

    sysprep = [call for call in lab.calls() if call[0] == "virt-sysprep"]
    assert len(sysprep) == 1
    args = sysprep[0]
    assert args[args.index("-a") + 1].endswith(".qcow2.new"), "sysprep must run on the copy"
    assert args[args.index("--operations") + 1] == "defaults", "user-account fails on Arch"
    assert "/home/*" in args
    command = args[args.index("--run-command") + 1]
    assert "userdel -r" in command and "$3 >= 1000 && $3 < 60000" in command
    assert args[-2:] == ["--truncate", "/etc/machine-id"], "the machine-id must be emptied last"
    assert args.index("--truncate") > args.index("--run-command"), "a command can write a machine-id again"
    assert not any(str(lab.disk) == arg for arg in args), "sysprep touched the source disk"
    guestfish = [call for call in lab.calls() if call[0] == "guestfish"]
    assert guestfish and "--ro" in guestfish[0]

    manifest = yaml.safe_load(Path(result["manifest"]).read_text())
    assert manifest["id"] == "arch-dev-20261003" and manifest["version"] == "20261003"
    assert manifest["source_type"] == "local" and manifest["status"] == "not-built"
    assert manifest["source_sha256"] == result["sha256"]
    assert manifest["generalized"] is True and manifest["contains_personal_data"] is False
    assert manifest["private"] is True and manifest["network_allowlist"] == ["dev"]
    assert manifest["virtual_size_gib"] == 100

    # The rendered manifest passes the repository's own schema validator.
    images = ROOT / "images" / "arch-dev-20261003.yml"
    assert not images.exists()
    try:
        images.write_text(Path(result["manifest"]).read_text())
        validation = subprocess.run([sys.executable, str(ROOT / "tests/schema_validate.py")],
                                    capture_output=True, text=True, check=False)
        assert validation.returncode == 0, validation.stdout + validation.stderr
        # ...and the image factory accepts it as a local import of the staged disk.
        plan = subprocess.run(
            [sys.executable, str(ROOT / "tools/image_plan.py"), "--root", str(ROOT),
             "--manifest", "images/arch-dev-20261003.yml",
             "--store", "/var/lib/libvirt/images/hyperlab", "--operation", "prepare",
             "--source-sha256", result["sha256"], "--local-source", str(staged)],
            capture_output=True, text=True, check=False,
        )
        assert plan.returncode == 0, plan.stderr
        assert json.loads(plan.stdout)["local_source"] == str(staged)
    finally:
        images.unlink()

    record = lab.run("show", "--domain", "arch-dev-vfio")
    assert record["state"] == "captured" and record["captured"]["sha256"] == result["sha256"]
    assert "already captured" in lab.run("seal", "--repo", str(lab.repo), "--domain", "arch-dev-vfio", ok=False)

    assert lab.run("release", "--domain", "arch-dev-vfio")["released"] is True
    assert not staged.parent.exists() and lab.run("list")["candidates"] == []


def check_failure_detail() -> None:
    sysprep = (
        "[   0.0] Examining the guest ...\n"
        "virt-sysprep: error: libguestfs error: could not create appliance through "
        "libvirt.\n\n"
        "If reporting bugs, run virt-sysprep with debugging enabled and include the\n"
        "complete output:\n\n  virt-sysprep -v -x [...]\n"
    )
    detail = workbench.failure_detail(sysprep)
    assert "could not create appliance" in detail, detail
    assert "reporting bugs" not in detail
    assert workbench.failure_detail("plain failure\n") == "plain failure"


def check_scan_rules() -> None:
    assert workbench.evaluate_scan(CLEAN_SCAN) == []
    cases = {
        "home directories remain": CLEAN_SCAN.replace("@@home\n", "@@home\nsid\n"),
        "/root/.ssh remains": CLEAN_SCAN.replace(".bashrc", ".ssh"),
        "/root/.bash_history remains": CLEAN_SCAN.replace(".bashrc", ".bash_history"),
        "/root/.gnupg remains": CLEAN_SCAN.replace(".bashrc", ".gnupg"),
        "machine-id is not empty": CLEAN_SCAN.replace("@@machine-id\n", "@@machine-id\n3f2a\n"),
        "SSH host keys remain": CLEAN_SCAN.replace("@@ssh-hostkeys\n", "@@ssh-hostkeys\n/etc/ssh/ssh_host_ed25519_key\n"),
        "cloud-init instance state remains": CLEAN_SCAN.replace("@@cloud-instances\n", "@@cloud-instances\niid-arch\n"),
        "90-cloud-init-users remains": CLEAN_SCAN.replace("false", "true"),
        "user account sid (uid 1000) remains": CLEAN_SCAN + "sid:x:1000:1000::/home/sid:/bin/bash\n",
        "did not run completely": CLEAN_SCAN.replace("@@passwd", "@@other"),
    }
    for expected, output in cases.items():
        problems = workbench.evaluate_scan(output)
        assert any(expected in problem for problem in problems), (expected, problems)
    assert workbench.evaluate_scan(CLEAN_SCAN.replace("@@machine-id\n", "@@machine-id\nuninitialized\n")) == []


def check_wiring() -> None:
    tasks = (ROOT / "roles/workbench/tasks/main.yml").read_text()
    defaults = yaml.safe_load((ROOT / "roles/workbench/defaults/main.yml").read_text())
    assert defaults["workbench_root"] == "/var/lib/hyperlab-workbench"
    assert "guestfs-tools" in defaults["workbench_packages"]
    assert 'path: "{{ workbench_root }}/staging", mode: "0700"' in tasks, "staging must be private"
    assert "LIBGUESTFS_BACKEND: direct" in tasks
    assert "force: false" in tasks, "an existing image manifest must never be overwritten"
    assert "brick_guard_brick: workbench" in tasks
    bricks = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text())
    assert bricks["brick_requires"]["workbench"] == ["image_store"]
    for operation in ("adopt", "seal", "release"):
        play = yaml.safe_load((ROOT / f"playbooks/workbench-{operation}.yml").read_text())[0]
        assert play["become"] is True and play["vars"]["workbench_operation"] == operation
        assert play["roles"][0]["vars"]["brick_guard_brick"] == "workbench"
    # The source disk is read, never generalized in place.
    source = TOOL.read_text()
    assert '"qemu-img", "convert"' in source
    assert 'run(["virt-sysprep", "--format", "qcow2", "-a", str(partial)' in source
    assert '"guestfish", "--ro"' in source


def main() -> int:
    check_wiring()
    check_failure_detail()
    check_scan_rules()
    with tempfile.TemporaryDirectory(prefix="hyperlab-workbench-") as temporary:
        lab = Lab(Path(temporary))
        check_adoption(lab)
        check_refusals(lab)
        check_seal(lab)
    print("HyperLab Workbench contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
