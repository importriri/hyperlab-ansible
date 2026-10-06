#!/usr/bin/env python3
"""Per-Machine QEMU identities (ADR 0037 part 2a), behind a switch that is off.

  1. the identity name is derived from the Machine name alone: a valid,
     prefixed system user name of at most 32 characters, distinct for
     distinct Machines, long names included;
  2. in per-machine mode the domain carries the identity as a static DAC
     label, the seed is not relabelled, and the SPICE socket sits in the
     Machine's own directory; shared mode renders exactly as before; the
     domain XML guard refuses a domain whose label drifted either way;
  3. the guest role makes the identity (system, no home, no shell, no
     password, its own group, the Looking Glass memory group only for VFIO
     Looking Glass Machines) before any file it owns, refuses an identity
     made for another purpose, gives the Machine's disk and seed to it
     (0600, 0400), checks them against it, and refuses disposable Machines
     in this mode until the bases get their own reader group (part 2b);
  4. Looking Glass: in per-machine mode no QEMU user owns the kvmfr node,
     the SPICE root is not writable by any Machine, and the libvirt hook that
     makes each Machine's directory is installed; in shared mode it is
     removed; the hook itself makes the directory for the labelled identity
     with the operator's ACL, removes it on release, ignores shared-mode
     domains and refuses a per-machine socket without a static label or a
     redirected directory;
  5. the store gives traverse without listing to the three directories a
     Machine identity must reach;
  6. the switch ships off.
"""

from __future__ import annotations

import json
import os
import pwd
import re
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import jinja2
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))

import guest_contract  # noqa: E402
from guest_plan import qemu_identity_name  # noqa: E402

XML_GUARD = ROOT / "tools/guest_xml_contract.py"
HOOK = ROOT / "roles/looking_glass/files/hyperlab-spice-dir.py"
SPICE_ROOT = yaml.safe_load((ROOT / "group_vars/all/looking-glass.yml").read_text())[
    "hyperlab_looking_glass_spice_socket_dir"]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def check_names() -> None:
    names = ["dev-01", "srv-tz-01", "arch-minimal-ssh", "a" * 28, "a" * 29, "a" * 31, "b" + "a" * 30,
             "x-" * 15 + "y", "x-" * 15 + "z"]
    identities = [qemu_identity_name(name) for name in names]
    for name, identity in zip(names, identities):
        require(re.fullmatch(r"hlq-[a-z0-9-]+", identity) is not None and len(identity) <= 32,
                f"{name} got an invalid identity {identity!r}")
        require(qemu_identity_name(name) == identity, f"{name}'s identity is not deterministic")
    require(len(set(identities)) == len(identities), f"two Machines share an identity: {identities}")
    require(qemu_identity_name("dev-01") == "hlq-dev-01", "a short name is not kept readable")


def render(mode: str, socket: str | None = None) -> str:
    env = guest_contract.template_env()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec, store, report, profiles, trust = guest_contract.vfio_fixture(root)
        plan = guest_contract.build_plan(root, spec, store)
        result = guest_contract.build_vfio_plan(plan, report, profiles, trust)
        require(result.returncode == 0, result.stderr)
        variables = {
            "guest_plan": plan, "guest_resolved_memory_mb": 6144,
            "guest_vfio": json.loads(result.stdout),
            "hyperlab_looking_glass_spice_socket_dir": SPICE_ROOT,
            "hyperlab_qemu_identity_mode": mode,
        }
        if mode == "per-machine":
            variables.update(guest_machine_uid="972", guest_machine_gid="971",
                             guest_spice_socket=socket or f"{SPICE_ROOT}/{plan['name']}/{plan['name']}.sock")
        return env.get_template("domain.xml.j2").render(**variables), plan["name"]


def guard(expected: str, actual: str) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "e.xml").write_text(expected)
        (Path(td) / "a.xml").write_text(actual)
        return subprocess.run([sys.executable, str(XML_GUARD), "--expected", f"{td}/e.xml", "--actual", f"{td}/a.xml"],
                              capture_output=True, text=True, check=False)


def check_domain() -> None:
    shared, name = render("shared")
    per_machine, _ = render("per-machine")
    shared_root, machine_root = ET.fromstring(shared), ET.fromstring(per_machine)
    require(shared_root.find("./seclabel") is None, "shared mode gained a domain label")
    require(shared_root.find("./devices/graphics/listen[@type='socket']").get("socket") == f"{SPICE_ROOT}/{name}.sock",
            "shared mode moved the SPICE socket")
    labels = machine_root.findall("./seclabel")
    require(len(labels) == 1 and labels[0].get("type") == "static" and labels[0].get("model") == "dac"
            and labels[0].findtext("./label").strip() == "+972:+971",
            "per-machine mode does not label the domain with the Machine's identity")
    require(machine_root.find("./devices/graphics/listen[@type='socket']").get("socket")
            == f"{SPICE_ROOT}/{name}/{name}.sock", "the SPICE socket is not in the Machine's own directory")
    env = guest_contract.template_env()
    with tempfile.TemporaryDirectory() as td:
        spec, store = guest_contract.standard_fixture(Path(td))
        plan = guest_contract.build_plan(Path(td), spec, store)
        require(plan["cloud_init"], "the standard fixture has no seed to check")
        seeded = ET.fromstring(env.get_template("domain.xml.j2").render(
            guest_plan=plan, guest_resolved_memory_mb=2048, guest_vfio={},
            hyperlab_qemu_identity_mode="per-machine", guest_machine_uid="972", guest_machine_gid="971"))
    seed = seeded.find("./devices/disk[@device='cdrom']/source/seclabel")
    require(seed is not None and seed.get("relabel") == "no", "libvirt would relabel the Machine's own seed")
    disk = machine_root.find("./devices/disk[@device='disk']/source/seclabel")
    require(disk is not None and disk.get("relabel") == "no", "libvirt would relabel the Machine's own disk")
    require(guard(per_machine, per_machine).returncode == 0, "the guard refused a per-machine domain")
    require(guard(per_machine, shared).returncode == 1, "the guard accepted a domain that lost its identity")
    require(guard(shared, per_machine).returncode == 1, "the guard accepted a domain that gained an identity")
    other = per_machine.replace("+972:+971", "+973:+971")
    require(guard(per_machine, other).returncode == 1, "the guard accepted another identity's label")


def check_role() -> None:
    tasks = (ROOT / "roles/guest/tasks/create.yml").read_text()
    main = (ROOT / "roles/guest/tasks/main.yml").read_text()
    validate = (ROOT / "roles/guest/tasks/validate.yml").read_text()
    identity = tasks.index("- name: Create the Machine's own QEMU identity")
    require(identity < tasks.index("- name: Build, verify and commit the guest artefacts"),
            "the identity is made after the files it owns")
    require(tasks.index("Refuse a disposable Machine with its own identity for now") < identity,
            "a disposable Machine could get an identity it cannot use")
    require(tasks.index("- name: Refuse an identity that names another Machine")
            < tasks.index("- name: Create the Machine identity's user"),
            "an account made for something else is changed before it is refused")
    for needle in ("system: true", "create_home: false", "shell: /usr/bin/nologin", 'password: "!"',
                   "append: false", "comment: \"HyperLab QEMU for {{ guest_plan.name }}\"",
                   "if guest_plan.device_profile == 'vfio' and guest_plan.looking_glass else []",
                   "Refuse an identity that names another Machine"):
        require(needle in tasks, f"the identity is not made as reviewed: {needle}")
    for needle in ('owner: "{{ guest_files_user }}"', 'mode: "{{ guest_disk_mode }}"', 'mode: "{{ guest_seed_mode }}"'):
        require(needle in tasks, f"a Machine file is not given to its identity: {needle}")
    require("guest_disk_stat.stat.pw_name == guest_files_user" in validate
            and "guest_seed_image_stat.stat.pw_name == guest_files_user" in validate,
            "the files are not checked against the Machine's identity")
    require("'0600' if hyperlab_qemu_identity_mode == 'per-machine' else '0640'" in main
            and "'0400' if hyperlab_qemu_identity_mode == 'per-machine' else '0440'" in main,
            "the per-machine file modes are not private")
    require("Refuse a per-machine Machine without its identity" in main, "a Machine may run without its identity")
    switch = yaml.safe_load((ROOT / "group_vars/all/guest.yml").read_text())
    require(switch["hyperlab_qemu_identity_mode"] == "shared", "the switch ships on before the lab proved it")


def render_template(path: str, mode: str) -> str:
    variables = {"hyperlab_qemu_identity_mode": mode, "hyperlab_kvmfr_group": "hyperlab-kvmfr",
                 "looking_glass_qemu_user": "libvirt-qemu", "looking_glass_device_group": "kvm",
                 "looking_glass_spice_socket_dir": SPICE_ROOT, "admin_user": "sid"}
    return jinja2.Template((ROOT / path).read_text(), undefined=jinja2.StrictUndefined).render(**variables)


def check_looking_glass() -> None:
    rules = render_template("roles/looking_glass/templates/70-kvmfr.rules.j2", "per-machine")
    active = [line for line in rules.splitlines() if line.startswith("SUBSYSTEM")]
    require(active == ['SUBSYSTEM=="kvmfr", OWNER="root", GROUP="hyperlab-kvmfr", MODE="0660", TAG+="uaccess"'],
            f"per-machine kvmfr access is not group-only: {active}")
    shared_rules = [line for line in render_template("roles/looking_glass/templates/70-kvmfr.rules.j2", "shared")
                    .splitlines() if line.startswith("SUBSYSTEM")]
    require(shared_rules == ['SUBSYSTEM=="kvmfr", OWNER="libvirt-qemu", GROUP="kvm", MODE="0660", TAG+="uaccess"'],
            "shared mode changed the kvmfr rule")
    tmpfiles = render_template("roles/looking_glass/templates/hyperlab-spice.tmpfiles.j2", "per-machine")
    require(f"d {SPICE_ROOT} 0711 root root -" in tmpfiles and "libvirt-qemu" not in tmpfiles,
            "a Machine identity could write the SPICE root")
    tasks = (ROOT / "roles/looking_glass/tasks/main.yml").read_text()
    require("dest: /etc/libvirt/hooks/qemu.d/50-hyperlab-spice-dir" in tasks
            and "when: hyperlab_qemu_identity_mode == 'per-machine'" in tasks
            and "Remove the per-Machine SPICE directory hook in shared mode" in tasks,
            "the SPICE directory hook is not tied to the mode")


def run_hook(phase: str, xml: str, config: dict, root: Path) -> subprocess.CompletedProcess:
    config_path = root / "spice-dir.json"
    config_path.write_text(json.dumps(config))
    env = dict(os.environ, HYPERLAB_SPICE_DIR_CONFIG=str(config_path), HYPERLAB_SPICE_DIR_DRY_RUN="1")
    return subprocess.run([sys.executable, str(HOOK), "dev-01", phase], input=xml, capture_output=True,
                          text=True, env=env, check=False)


def check_hook() -> None:
    operator = pwd.getpwuid(os.getuid()).pw_name
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spice = root / "spice"
        spice.mkdir()
        config = {"root": str(spice), "operator": operator}
        labelled = (f"<domain><name>dev-01</name><devices><graphics type='spice'><listen type='socket' "
                    f"socket='{spice}/dev-01/dev-01.sock'/></graphics></devices>"
                    "<seclabel type='static' model='dac' relabel='yes'><label>+972:+971</label></seclabel></domain>")
        made = run_hook("prepare", labelled, config, root)
        require(made.returncode == 0, f"the hook refused a labelled Machine: {made.stderr}")
        actions = made.stdout.splitlines()
        require(f"ACTION install -d -m 0770 -o 972 -g 971 {spice}/dev-01" in actions,
                f"the directory is not made for the labelled identity: {actions}")
        acl = next((line for line in actions if line.startswith("ACTION setfacl")), "")
        require(f"u:{operator}:rwx" in acl and "o::---" in acl and "d:o::---" in acl,
                f"the directory's ACL is not operator-only: {acl}")
        released = run_hook("release", labelled, config, root)
        require(released.returncode == 0, "the hook failed on release")
        shared = labelled.replace(f"{spice}/dev-01/dev-01.sock", f"{spice}/dev-01.sock")
        untouched = run_hook("prepare", shared, config, root)
        require(untouched.returncode == 0 and untouched.stdout == "", "the hook touched a shared-mode Machine")
        unlabelled = labelled.split("<seclabel")[0] + "</domain>"
        require(run_hook("prepare", unlabelled, config, root).returncode == 1,
                "the hook made a directory for a Machine without a static label")
        (spice / "dev-01").symlink_to(root)
        require(run_hook("prepare", labelled, config, root).returncode == 1,
                "the hook followed a redirected directory")
        require(run_hook("started", labelled, config, root).returncode == 0, "another phase was not ignored")


def check_store() -> None:
    defaults = yaml.safe_load((ROOT / "roles/image_store/defaults/main.yml").read_text())
    require(defaults["image_store_qemu_traverse_paths"] == ["permanent", "cloud-init", "nvram"],
            "the store's traverse directories changed")
    require("'0751' if hyperlab_qemu_identity_mode == 'per-machine' else '0750'"
            in defaults["image_store_qemu_traverse_mode"], "the traverse mode is not tied to the switch")


def main() -> int:
    check_names()
    check_domain()
    check_role()
    check_looking_glass()
    check_hook()
    check_store()
    print("Per-Machine QEMU identity contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
