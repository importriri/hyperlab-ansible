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
elif name == "virt-customize":
    if "--format" in sys.argv and sys.argv.index("--format") > sys.argv.index("-a"):
        print("virt-customize: error: --format parameter must appear before -a parameter", file=sys.stderr)
        sys.exit(1)
    image = sys.argv[sys.argv.index("-a") + 1]
    with open(image, "ab") as handle:
        handle.write(b"customized")
elif name == "virt-inspector":
    if "--format" in sys.argv and sys.argv.index("--format") > sys.argv.index("-a"):
        print("virt-inspector: error: --format parameter must appear before -a parameter", file=sys.stderr)
        sys.exit(1)
    print(open(os.environ["FAKE_INSPECT"]).read(), end="")
elif name == "guestfish":
    script = sys.stdin.read()
    if "is-file-opts" in script:
        present = os.environ.get("FAKE_AGENT", "").split(",")
        for line in script.splitlines():
            if line.startswith("is-file-opts "):
                print("true" if line.split()[1] in present else "false")
    elif "qemu-guest-agent.service" in script and "glob-expand" in script:
        print(os.environ.get("FAKE_ACTIVATION", ""))
    else:
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
@@apt-archives
@@apt-logs
@@dpkg-log
false
@@passwd
root:x:0:0::/root:/bin/bash
nobody:x:65534:65534:Kernel Overflow User:/:/usr/bin/nologin
"""


INSPECTION = """<?xml version="1.0"?>
<operatingsystems>
  <operatingsystem>
    <root>/dev/sda3</root>
    <name>linux</name>
    <package_format>pacman</package_format>
    <applications>
      <application><name>linux</name><version>6.17.1.arch1</version><release>1</release></application>
      <application><name>qemu-guest-agent</name><epoch>1</epoch><version>10.1.0</version><release>2</release></application>
      <application><name>bash</name><version>5.3.3</version><release>2</release></application>
    </applications>
  </operatingsystem>
</operatingsystems>
"""


def git(repo: Path, *args: str) -> str:
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t",
           "GIT_COMMITTER_EMAIL": "t@t", "PATH": os.environ.get("PATH", "/usr/bin"),
           "HOME": str(repo.parent)}
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                          check=True, env=env).stdout.strip()


class Lab:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.root = base / "workbench"
        self.repo = base / "repo"
        (self.repo / "images").mkdir(parents=True)
        (self.repo / "images/arch.yml").write_text((ROOT / "images/arch.yml").read_text())
        git(self.repo, "init", "-q")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "--no-gpg-sign", "-m", "fixture")
        self.bin = base / "bin"
        self.bin.mkdir()
        for name in ("virsh", "qemu-img", "virt-sysprep", "virt-customize", "guestfish", "virt-inspector"):
            path = self.bin / name
            path.write_text(FAKE)
            path.chmod(0o755)
        self.disk = base / "domains/arch-dev-vfio.qcow2"
        self.disk.parent.mkdir()
        self.disk.write_bytes(b"source-disk")
        self.log = base / "tools.log"
        self.scan = base / "scan.txt"
        self.scan.write_text(CLEAN_SCAN)
        self.inspect = base / "inspect.xml"
        self.inspect.write_text(INSPECTION)
        self.env = {
            "FAKE_INSPECT": str(self.inspect),
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

    def adopt(self, domain: str = "arch-dev-vfio", image: str = "contract-dev-20261003", ok: bool = True):
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
    # A reviewed not-built placeholder may reserve an id for a Template; it is
    # the only manifest adoption accepts. A placeholder carrying a digest or a
    # recorded source is a real manifest.
    placeholder = yaml.safe_load((ROOT / "images/arch-dev-standard.yml").read_text())
    (lab.repo / "images/arch-dev-standard.yml").write_text(yaml.safe_dump(placeholder))
    adopted = lab.adopt(domain="arch-dev", image="arch-dev-standard")
    assert adopted["image_id"] == "arch-dev-standard", adopted
    lab.run("release", "--domain", "arch-dev")
    for field, value in (("sha256", "a" * 64), ("source_sha256", "a" * 64), ("status", "sealed"),
                         ("source_type", "official-cloud"), ("id", "another-id")):
        forged = dict(placeholder, **{field: value})
        (lab.repo / "images/arch-dev-standard.yml").write_text(yaml.safe_dump(forged))
        assert "never replaced" in lab.adopt(domain="arch-dev", image="arch-dev-standard", ok=False), field
    (lab.repo / "images/arch-dev-standard.yml").unlink()
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
    assert not (lab.root / "staging/contract-dev-20261003").exists(), "a refused seal left staging behind"
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
    for path in ("/root/.config", "/root/.cache", "/root/.npm"):
        assert args[args.index(path) - 1] == "--delete", path
    command = args[args.index("--run-command") + 1]
    assert "userdel -r" in command and "$3 >= 1000 && $3 < 60000" in command
    assert args[-2:] == ["--truncate", "/etc/machine-id"], "the machine-id must be emptied last"
    assert args.index("--truncate") > args.index("--run-command"), "a command can write a machine-id again"
    assert not any(str(lab.disk) == arg for arg in args), "sysprep touched the source disk"
    guestfish = [call for call in lab.calls() if call[0] == "guestfish"]
    assert guestfish and "--ro" in guestfish[0]

    manifest = yaml.safe_load(Path(result["manifest"]).read_text())
    assert manifest["id"] == "contract-dev-20261003" and manifest["version"] == "20261003"
    assert manifest["source_type"] == "local" and manifest["status"] == "not-built"
    assert manifest["source_sha256"] == result["sha256"]
    assert manifest["generalized"] is True and manifest["contains_personal_data"] is False
    assert manifest["private"] is True and manifest["network_allowlist"] == ["dev"]
    assert manifest["virtual_size_gib"] == 100

    # Build provenance: the checkout, the base and the packages, bound by digest.
    build = manifest["build"]
    assert build["workbench_commit"] == git(lab.repo, "rev-parse", "HEAD")
    assert build["workbench_tree_dirty"] is False
    assert build["base_image"] == "arch" and build["base_sha256"] == yaml.safe_load(
        (lab.repo / "images/arch.yml").read_text()).get("sha256")
    listing = Path(result["packages"])
    assert listing.read_text() == (
        "bash 5.3.3-2\nlinux 6.17.1.arch1-1\nqemu-guest-agent 1:10.1.0-2\n"), listing.read_text()
    assert build["packages"] == {
        "manager": "pacman", "count": 3, "file": "packages/contract-dev-20261003.txt",
        "sha256": hashlib.sha256(listing.read_bytes()).hexdigest(),
    }
    inspector = next(call for call in lab.calls() if call[0] == "virt-inspector")
    assert inspector[inspector.index("-a") + 1].endswith(".qcow2.new"), "inspection must read the copy"

    # The rendered manifest passes the repository's own schema validator.
    images = ROOT / "images" / "contract-dev-20261003.yml"
    packages = ROOT / "images" / "packages" / "contract-dev-20261003.txt"
    assert not images.exists() and not packages.exists()
    try:
        images.write_text(Path(result["manifest"]).read_text())
        packages.write_text(Path(result["packages"]).read_text())
        validation = subprocess.run([sys.executable, str(ROOT / "tests/schema_validate.py")],
                                    capture_output=True, text=True, check=False)
        assert validation.returncode == 0, validation.stdout + validation.stderr
        # ...and the image factory accepts it as a local import of the staged disk.
        plan = subprocess.run(
            [sys.executable, str(ROOT / "tools/image_plan.py"), "--root", str(ROOT),
             "--manifest", "images/contract-dev-20261003.yml",
             "--store", "/var/lib/libvirt/images/hyperlab", "--operation", "prepare",
             "--source-sha256", result["sha256"], "--local-source", str(staged)],
            capture_output=True, text=True, check=False,
        )
        assert plan.returncode == 0, plan.stderr
        assert json.loads(plan.stdout)["local_source"] == str(staged)
        # The repository refuses a package list that no longer matches.
        packages.write_text("bash 5.3.3-2\n")
        validation = subprocess.run([sys.executable, str(ROOT / "tests/schema_validate.py")],
                                    capture_output=True, text=True, check=False)
        assert validation.returncode != 0 and "package list" in validation.stdout + validation.stderr
    finally:
        images.unlink()
        packages.unlink(missing_ok=True)

    record = lab.run("show", "--domain", "arch-dev-vfio")
    assert record["state"] == "captured" and record["captured"]["sha256"] == result["sha256"]
    assert lab.run("release", "--domain", "arch-dev-vfio")["released"] is True
    lab.adopt()

    # A tracked change is recorded; odd text from the image or no package
    # format refuses the seal and leaves no staging.
    (lab.repo / "images/arch.yml").write_text((lab.repo / "images/arch.yml").read_text() + "# local\n")
    dirty = lab.run("seal", "--repo", str(lab.repo), "--domain", "arch-dev-vfio")
    assert yaml.safe_load(Path(dirty["manifest"]).read_text())["build"]["workbench_tree_dirty"] is True
    git(lab.repo, "checkout", "--", "images/arch.yml")
    assert lab.run("release", "--domain", "arch-dev-vfio")["released"] is True
    for inspection, expected in (
        (INSPECTION.replace("<name>bash</name>", "<name>bash;rm -rf /</name>"), "unreadable package entry"),
        (INSPECTION.replace("<package_format>pacman</package_format>", ""), "unknown package format"),
        ("not xml", "unreadable output"),
    ):
        lab.adopt()
        lab.inspect.write_text(inspection)
        assert expected in lab.run("seal", "--repo", str(lab.repo), "--domain", "arch-dev-vfio", ok=False)
        assert not (lab.root / "staging/contract-dev-20261003").exists(), "a refused seal left staging"
        lab.inspect.write_text(INSPECTION)
        assert lab.run("release", "--domain", "arch-dev-vfio")["released"] is True
    lab.adopt()
    result = lab.run("seal", "--repo", str(lab.repo), "--domain", "arch-dev-vfio")
    staged = Path(result["staged_image"])
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
        "/root/.config remains": CLEAN_SCAN.replace(".bashrc", ".config"),
        "/root/.npm remains": CLEAN_SCAN.replace(".bashrc", ".npm"),
        "machine-id is not empty": CLEAN_SCAN.replace("@@machine-id\n", "@@machine-id\n3f2a\n"),
        "SSH host keys remain": CLEAN_SCAN.replace("@@ssh-hostkeys\n", "@@ssh-hostkeys\n/etc/ssh/ssh_host_ed25519_key\n"),
        "cloud-init instance state remains": CLEAN_SCAN.replace("@@cloud-instances\n", "@@cloud-instances\niid-arch\n"),
        "90-cloud-init-users remains": CLEAN_SCAN.replace("false", "true"),
        "user account sid (uid 1000) remains": CLEAN_SCAN + "sid:x:1000:1000::/home/sid:/bin/bash\n",
        "did not run completely": CLEAN_SCAN.replace("@@passwd", "@@other"),
        "downloaded packages remain": CLEAN_SCAN.replace(
            "@@apt-archives\n", "@@apt-archives\n/var/cache/apt/archives/qemu-guest-agent_10.0_amd64.deb\n"),
        "apt logs remain": CLEAN_SCAN.replace("@@apt-logs\n", "@@apt-logs\n/var/log/apt/history.log\n"),
        "/var/log/dpkg.log remains": CLEAN_SCAN.replace("@@dpkg-log\nfalse", "@@dpkg-log\ntrue"),
    }
    for expected, output in cases.items():
        problems = workbench.evaluate_scan(output)
        assert any(expected in problem for problem in problems), (expected, problems)
    assert workbench.evaluate_scan(CLEAN_SCAN.replace("@@machine-id\n", "@@machine-id\nuninitialized\n")) == []


def check_derive(base_dir: Path) -> None:
    """An offline derivation (ADR 0026): verified base, apt inside, scan, agent."""
    lab = Lab(base_dir)
    store = base_dir / "store"
    (store / "bases/linux").mkdir(parents=True)
    base_bytes = b"sealed debian genericcloud"
    (store / "bases/linux/debian.qcow2").write_bytes(base_bytes)
    debian = yaml.safe_load((ROOT / "images/debian.yml").read_text())
    debian["sha256"] = hashlib.sha256(base_bytes).hexdigest()
    (lab.repo / "images/debian.yml").write_text(yaml.safe_dump(debian))
    placeholder = (ROOT / "images/debian-server.yml").read_text()
    (lab.repo / "images/debian-server.yml").write_text(placeholder)
    agent = "/usr/sbin/qemu-ga,/lib/systemd/system/qemu-guest-agent.service"
    lab.env.update({"FAKE_AGENT": agent,
                    "FAKE_ACTIVATION": "/etc/systemd/system/dev-virtio\\x2dports-org.qemu.guest_agent.0.device.wants/qemu-guest-agent.service"})

    def derive(ok: bool = True):
        return lab.run("derive", "--repo", str(lab.repo), "--store", str(store),
                       "--image-id", "debian-server", ok=ok)

    result = derive()
    staged = Path(result["staged_image"])
    assert result["base"] == "debian" and result["installed"] == ["qemu-guest-agent"]
    assert result["sha256"] == hashlib.sha256(staged.read_bytes()).hexdigest()
    assert (store / "bases/linux/debian.qcow2").read_bytes() == base_bytes, "the base was modified"
    manifest = yaml.safe_load(Path(result["manifest"]).read_text())
    assert manifest["status"] == "not-built" and manifest["sha256"] is None
    assert manifest["source_sha256"] == result["sha256"] and manifest["derive"]["install"] == ["qemu-guest-agent"]
    assert manifest["build"]["base_image"] == "debian"
    assert manifest["build"]["base_sha256"] == debian["sha256"]
    assert manifest["build"]["packages"]["file"] == "packages/debian-server.txt"
    assert Path(result["packages"]).is_file()
    calls = lab.calls()
    names = [call[0] for call in calls]
    assert "virsh" not in names and "ssh" not in names, "a derivation booted or reached a guest"
    customize = next(call for call in calls if call[0] == "virt-customize")
    assert customize[customize.index("--install") + 1] == "qemu-guest-agent" and "--network" in customize
    sysprep = next(call for call in calls if call[0] == "virt-sysprep")
    for path in ("/var/cache/apt/archives/*.deb", "/var/lib/apt/lists/*", "/var/log/apt/*", "/var/log/dpkg.log"):
        assert path in sysprep, f"apt residue {path} is not removed"
    assert sysprep[-2:] == ["--truncate", "/etc/machine-id"], "the machine-id is not emptied last"
    assert names.index("virt-customize") < names.index("virt-sysprep") < names.index("guestfish")
    assert all("--ro" in call for call in calls if call[0] == "guestfish")
    assert "stale staging" in derive(ok=False)
    assert lab.run("discard", "--image-id", "debian-server")["discarded"] is True

    for change, expected in (
        ({"FAKE_AGENT": ""}, "binary or unit is missing"),
        ({"FAKE_ACTIVATION": ""}, "nothing starts the QEMU Guest Agent"),
    ):
        saved = dict(lab.env)
        lab.env.update(change)
        assert expected in derive(ok=False), expected
        assert not (lab.root / "staging/debian-server").exists(), "a refused derivation left staging"
        lab.env = saved

    lab.scan.write_text(CLEAN_SCAN.replace("@@apt-logs\n", "@@apt-logs\n/var/log/apt/term.log\n"))
    assert "apt logs remain" in derive(ok=False)
    lab.scan.write_text(CLEAN_SCAN)

    (store / "bases/linux/debian.qcow2").write_bytes(b"changed base")
    assert "no longer matches its sealed digest" in derive(ok=False)
    (store / "bases/linux/debian.qcow2").write_bytes(base_bytes)

    sealed = yaml.safe_load(placeholder)
    sealed.update(status="sealed", sha256="a" * 64, source_sha256="a" * 64)
    (lab.repo / "images/debian-server.yml").write_text(yaml.safe_dump(sealed))
    assert "never replaced" in derive(ok=False)
    (lab.repo / "images/debian-server.yml").write_text(placeholder)

    lab.adopt(domain="arch-dev-vfio", image="contract-dev-20261003")
    assert "release the candidate instead" in lab.run("discard", "--image-id", "contract-dev-20261003", ok=False)


def check_wiring() -> None:
    tasks = (ROOT / "roles/workbench/tasks/main.yml").read_text()
    defaults = yaml.safe_load((ROOT / "roles/workbench/defaults/main.yml").read_text())
    assert defaults["workbench_root"] == "/var/lib/hyperlab-workbench"
    assert "guestfs-tools" in defaults["workbench_packages"]
    assert 'path: "{{ workbench_root }}/staging", mode: "0700"' in tasks, "staging must be private"
    assert "LIBGUESTFS_BACKEND: direct" in tasks
    publish_text = (ROOT / "roles/workbench/tasks/publish-manifest.yml").read_text()
    tasks = tasks + publish_text
    copy_names = [task["name"] for task in yaml.safe_load(publish_text)]
    assert copy_names.index("Refuse to replace a real image manifest") < copy_names.index(
        "Put the manifest in the checkout for review"), "the manifest can be copied before the placeholder check"
    assert 'force: "{{ workbench_existing_manifest.stat.exists }}"' in tasks
    for condition in ("status | default('') == 'not-built'", "sha256 | default('x') is none",
                      "source_sha256 | default('x') is none", "source_type | default('') == 'local'",
                      "id | default('') == workbench_capture.image_id"):
        assert condition in tasks, f"the seal's placeholder rule lost: {condition}"
    assert "brick_guard_brick: workbench" in tasks
    bricks = yaml.safe_load((ROOT / "group_vars/all/bricks.yml").read_text())
    assert bricks["brick_requires"]["workbench"] == ["image_store"]
    main_tasks = yaml.safe_load((ROOT / "roles/workbench/tasks/main.yml").read_text())
    for operation in ("seal", "derive"):
        block = next(task for task in main_tasks if task.get("when") == f"workbench_operation == '{operation}'")
        assert block["block"][-1].get("ansible.builtin.include_tasks") == "publish-manifest.yml", operation
    derive_block = next(task for task in main_tasks if task.get("when") == "workbench_operation == 'derive'")
    argv = derive_block["block"][0]["ansible.builtin.command"]["argv"]
    assert "derive" in argv and derive_block["block"][0]["environment"]["LIBGUESTFS_BACKEND"] == "direct"
    for operation in ("adopt", "seal", "release", "derive", "discard"):
        play = yaml.safe_load((ROOT / f"playbooks/workbench-{operation}.yml").read_text())[0]
        assert play["become"] is True and play["vars"]["workbench_operation"] == operation
        assert play["roles"][0]["vars"]["brick_guard_brick"] == "workbench"
    # The source disk is read, never generalized in place.
    source = TOOL.read_text()
    assert '"qemu-img", "convert"' in source
    assert 'run(["virt-sysprep", "--format", "qcow2", "-a", str(partial)' in source
    assert '"guestfish", "--ro"' in source
    # Run as root over the operator's checkout, git must never rewrite the index.
    assert '"git", "--no-optional-locks"' in source
    publish = (ROOT / "roles/workbench/tasks/publish-manifest.yml").read_text()
    assert 'path: "{{ workbench_capture.packages }}"' in publish
    assert 'dest: "{{ workbench_repository_root }}/images/packages/{{ workbench_capture.image_id }}.txt"' in publish


def main() -> int:
    check_wiring()
    check_failure_detail()
    check_scan_rules()
    with tempfile.TemporaryDirectory(prefix="hyperlab-workbench-") as temporary:
        lab = Lab(Path(temporary))
        check_adoption(lab)
        check_refusals(lab)
        check_seal(lab)
    with tempfile.TemporaryDirectory(prefix="hyperlab-workbench-derive-") as temporary:
        check_derive(Path(temporary))
    print("HyperLab Workbench contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
