#!/usr/bin/env python3
"""Host-independent structural and mutation tests for the M4 guest brick."""
from __future__ import annotations

import base64
import configparser
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "tools/guest_plan.py"
VFIO_PLAN = ROOT / "tools/vfio_plan.py"
MEMORY = ROOT / "tools/guest_memory.py"
XML_CONTRACT = ROOT / "tools/guest_xml_contract.py"
STATE_GUARD = ROOT / "tools/guest_state_guard.py"
VFIO_REGISTRY = ROOT / "tools/vfio_registry.py"
LG_BUILD = "B7-263-g0140a3f6fb"


def run(*args: str, stdin: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, input=stdin, text=True, capture_output=True, check=False)


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def standard_fixture(root: Path) -> tuple[Path, Path]:
    (root / "images").mkdir()
    (root / "vm-specs").mkdir()
    store = root / "store"
    base = store / "bases/linux/debian.qcow2"
    base.parent.mkdir(parents=True)
    base.write_bytes(b"sealed synthetic base\n")
    manifest = {
        "schema_version": 1,
        "id": "debian",
        "display_name": "Debian fixture",
        "os_family": "linux",
        "os_variant": "debian12",
        "version": "fixture",
        "format": "qcow2",
        "status": "sealed",
        "sha256": hashlib.sha256(base.read_bytes()).hexdigest(),
        "private": False,
        "contains_personal_data": False,
        "generalized": True,
        "instance_policy": "multiple",
        "source_type": "local",
        "source_url": None,
        "source_checksum_url": None,
        "filename": "debian.qcow2",
        "virtual_size_gib": 20,
        "minimum_size_gib": 8,
        "min_memory_mb": 2048,
        "supports": {"standard": True, "vfio": False, "cloud_init": True, "qemu_guest_agent": True},
        "requires": {"uefi": True, "secure_boot": False, "tpm2": False},
        "defaults": {"lifecycle": "permanent", "device_profile": "standard", "network_profile": "dev"},
        "network_allowlist": ["dev", "lab"],
        "licensing": {"redistributable": True},
        "looking_glass_host_build_required": None,
    }
    spec = {
        "schema_version": 1,
        "name": "debian-test",
        "image": "debian",
        "lifecycle": "disposable",
        "device_profile": "standard",
        "network_profile": "lab",
        "resources": {"memory_mb": "auto", "vcpus": 2, "disk_gib": None},
        "memory_overcommit": False,
        "autostart": False,
        "qemu_guest_agent": True,
        "looking_glass": False,
        "clipboard": False,
        "shared_folders": False,
        "usb_allowlist": [],
        "owner": "sid",
        "purpose": "fixture",
        "tags": ["test"],
    }
    spec_path = root / "vm-specs/debian-test.yml"
    write_yaml(root / "images/debian.yml", manifest)
    write_yaml(spec_path, spec)
    return spec_path, store


def vfio_fixture(root: Path) -> tuple[Path, Path, Path, dict[str, Any], dict[str, int]]:
    (root / "images").mkdir()
    (root / "vm-specs").mkdir()
    store = root / "store"
    base = store / "bases/windows/win11clean.qcow2"
    base.parent.mkdir(parents=True)
    base.write_bytes(b"sealed synthetic Windows base\n")
    manifest = {
        "schema_version": 1,
        "id": "win11clean",
        "display_name": "Windows fixture",
        "os_family": "windows",
        "os_variant": "win11",
        "version": "fixture",
        "format": "qcow2",
        "status": "sealed",
        "sha256": hashlib.sha256(base.read_bytes()).hexdigest(),
        "private": True,
        "contains_personal_data": True,
        "generalized": False,
        "instance_policy": "singleton",
        "source_type": "local",
        "source_url": None,
        "source_checksum_url": None,
        "filename": "win11clean.qcow2",
        "virtual_size_gib": 128,
        "minimum_size_gib": 80,
        "min_memory_mb": 6144,
        "supports": {"standard": True, "vfio": True, "cloud_init": False, "qemu_guest_agent": True},
        "requires": {"uefi": True, "secure_boot": True, "tpm2": True},
        "defaults": {"lifecycle": "permanent", "device_profile": "vfio", "network_profile": "clean"},
        "network_allowlist": ["clean"],
        "licensing": {"redistributable": False},
        "looking_glass_host_build_required": LG_BUILD,
    }
    spec = {
        "schema_version": 1,
        "name": "win11clean-test",
        "image": "win11clean",
        "lifecycle": "permanent",
        "device_profile": "vfio",
        "network_profile": "clean",
        "resources": {"memory_mb": "auto", "vcpus": 6, "disk_gib": None},
        "memory_overcommit": False,
        "autostart": False,
        "qemu_guest_agent": True,
        "looking_glass": True,
        "looking_glass_mode": "windows",
        "clipboard": True,
        "shared_folders": False,
        "usb_allowlist": [],
        "owner": "sid",
        "purpose": "VFIO fixture",
        "tags": ["windows", "vfio"],
        "benchmark": "unigine-valley",
    }
    report = {
        "host_profile": "nitro-3060",
        "vfio_ids": ["10de:2520", "10de:228e"],
        "vfio_devices": [
            {"id": "10de:2520", "pci": "01:00.0"},
            {"id": "10de:228e", "pci": "01:00.1"},
        ],
        "gpu_pci": "01:00.0",
        "gpu_audio_pci": "01:00.1",
        "cpu_threads": 8,
    }
    profiles = {
        "nitro-3060": {
            "vfio_ids": ["10de:2520", "10de:228e"],
            "memory": {
                "host_reserved_mb": 2048,
                "qemu_overhead_per_domain_mb": 512,
                "services_reserved_mb": 0,
                "vfio_fixed_overhead_mb": 256,
                "max_auto_memory_mb": 6144,
                "standard_overcommit_ratio": 1.0,
            },
            "cpu_pinning": {
                "host_cpu_threads": 8,
                "plans": {
                    "4": {
                        "vcpu_pins": [2, 6, 3, 7],
                        "emulator_cpus": [0, 4],
                        "iothread_cpus": [1, 5],
                        "topology": {
                            "sockets": 1, "dies": 1, "cores": 2, "threads": 2
                        },
                    },
                    "6": {
                        "vcpu_pins": [1, 5, 2, 6, 3, 7],
                        "emulator_cpus": [0, 4],
                        "iothread_cpus": [0, 4],
                        "topology": {
                            "sockets": 1, "dies": 1, "cores": 3, "threads": 2
                        },
                    },
                },
            },
        }
    }
    trust = {"clean": 3, "dev": 2, "dirty": 1, "lab": 0}
    spec_path = root / "vm-specs/win11clean-test.yml"
    report_path = root / "hardware-profile.yml"
    write_yaml(root / "images/win11clean.yml", manifest)
    write_yaml(spec_path, spec)
    write_yaml(report_path, report)
    return spec_path, store, report_path, profiles, trust


def build_plan(root: Path, spec: Path, store: Path) -> dict[str, Any]:
    result = run(sys.executable, str(PLAN), "--root", str(root), "--spec", str(spec), "--store", str(store))
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def build_vfio_plan(plan: dict[str, Any], report: Path, profiles: dict[str, Any], trust: dict[str, int],
                    build: str = LG_BUILD) -> subprocess.CompletedProcess[str]:
    return run(
        sys.executable,
        str(VFIO_PLAN),
        "--report", str(report),
        "--profiles-json", json.dumps(profiles),
        "--trust-levels-json", json.dumps(trust),
        "--looking-glass-build", build,
        "--looking-glass-device", "/dev/kvmfr0",
        "--looking-glass-shm-mb", "64",
        "--spice-host", "127.0.0.1",
        "--spice-port", "5900",
        stdin=json.dumps(plan),
    )


def test_standard_plan() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec, store = standard_fixture(root)
        plan = build_plan(root, spec, store)
        second = build_plan(root, root / "vm-specs/debian-test.yml", store)
        assert second["uuid"] == plan["uuid"]
        assert second["mac"] == plan["mac"]
        assert plan["device_profile"] == "standard"
        assert plan["looking_glass"] is False
        assert plan["looking_glass_mode"] is None
        assert plan["gpu_lock_path"].endswith("/state/locks/gpu.lock")

        manifest_path = root / "images/debian.yml"
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest["status"] = "not-built"
        manifest["sha256"] = None
        write_yaml(manifest_path, manifest)
        refused = run(sys.executable, str(PLAN), "--root", str(root), "--spec", str(spec), "--store", str(store))
        assert refused.returncode == 2 and "not sealed" in refused.stderr

        manifest["status"] = "sealed"
        manifest["sha256"] = hashlib.sha256((store / "bases/linux/debian.qcow2").read_bytes()).hexdigest()
        write_yaml(manifest_path, manifest)
        data = yaml.safe_load(spec.read_text())
        data["device_profile"] = "vfio"
        write_yaml(spec, data)
        refused = run(sys.executable, str(PLAN), "--root", str(root), "--spec", str(spec), "--store", str(store))
        assert refused.returncode == 2 and "does not support vfio" in refused.stderr

        data["device_profile"] = "standard"
        data["shared_folders"] = True
        write_yaml(spec, data)
        refused = run(sys.executable, str(PLAN), "--root", str(root), "--spec", str(spec), "--store", str(store))
        assert refused.returncode == 2 and "shared folders" in refused.stderr

        outside = root / "outside.yml"
        shutil.copy(spec, outside)
        refused = run(sys.executable, str(PLAN), "--root", str(root), "--spec", str(outside), "--store", str(store))
        assert refused.returncode == 2 and "below vm-specs" in refused.stderr


def test_vfio_plan() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec, store, report, profiles, trust = vfio_fixture(root)
        plan = build_plan(root, spec, store)
        result = build_vfio_plan(plan, report, profiles, trust)
        assert result.returncode == 0, result.stderr
        vfio = json.loads(result.stdout)
        assert vfio["gpu"]["bdf"] == "0000:01:00.0"
        assert vfio["audio"]["bdf"] == "0000:01:00.1"
        assert vfio["trust_level"] == 3
        assert vfio["looking_glass_shm_bytes"] == 64 * 1024 * 1024
        assert vfio["looking_glass_mode"] == "windows"
        assert vfio["spice_port"] == 5900
        assert vfio["cpu_pinning"]["enabled"] is True
        assert [item["cpuset"] for item in vfio["cpu_pinning"]["vcpu_pins"]] == [
            "1", "5", "2", "6", "3", "7"
        ]
        assert vfio["cpu_pinning"]["emulator_cpuset"] == "0,4"
        assert vfio["cpu_pinning"]["iothread_cpuset"] == "0,4"

        data = yaml.safe_load(spec.read_text())
        data["gpu_handoff_profile"] = "clean"
        data["network_profile"] = "lab"
        write_yaml(spec, data)
        manifest_path = root / "images/win11clean.yml"
        manifest_data = yaml.safe_load(manifest_path.read_text())
        manifest_data["network_allowlist"] = ["clean", "lab"]
        write_yaml(manifest_path, manifest_data)
        refused = run(sys.executable, str(PLAN), "--root", str(root), "--spec", str(spec), "--store", str(store))
        assert refused.returncode == 2 and "ranks above network lab" in refused.stderr, refused.stderr
        data["network_profile"] = "clean"
        data.pop("gpu_handoff_profile")
        write_yaml(spec, data)

        mismatch = build_vfio_plan(plan, report, profiles, trust, build="B7-999-g0123456789")
        assert mismatch.returncode == 2 and "differs" in mismatch.stderr

        report_data = yaml.safe_load(report.read_text())
        report_data["gpu_audio_pci"] = "02:00.1"
        report_data["vfio_devices"][1]["pci"] = "02:00.1"
        write_yaml(report, report_data)
        split = build_vfio_plan(plan, report, profiles, trust)
        assert split.returncode == 2 and "share one PCI slot" in split.stderr

        spec_data = yaml.safe_load(spec.read_text())
        spec_data["autostart"] = True
        write_yaml(spec, spec_data)
        refused = run(sys.executable, str(PLAN), "--root", str(root), "--spec", str(spec), "--store", str(store))
        assert refused.returncode == 2 and "cannot autostart" in refused.stderr


def template_env() -> Environment:
    env = Environment(
        loader=FileSystemLoader(str(ROOT / "roles/guest/templates")),
        undefined=StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )
    env.filters.update({"bool": bool, "to_json": json.dumps})
    return env


class UniqueKeyLoader(yaml.SafeLoader):
    """A YAML loader that refuses a mapping with a repeated key."""


def _unique_mapping(loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
    seen: set[Any] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=deep)
        assert key not in seen, f"duplicate YAML key {key!r} on line {key_node.start_mark.line + 1}"
        seen.add(key)
    return yaml.SafeLoader.construct_mapping(loader, node, deep)


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping)


def load_unique(text: str) -> Any:
    return yaml.load(text, Loader=UniqueKeyLoader)  # noqa: S506 - a SafeLoader subclass


def run_playbook(tmp: Path, playbook: list[dict[str, Any]], extra_vars: dict[str, Any],
                 *options: str, inventory: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run one playbook with the real ansible-playbook on this host only."""
    path = tmp / f"playbook-{len(list(tmp.glob('playbook-*.yml')))}.yml"
    write_yaml(path, playbook)  # type: ignore[arg-type]
    variables = tmp / f"{path.stem}-vars.json"
    variables.write_text(json.dumps(extra_vars), encoding="utf-8")
    environment = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "HOME": str(tmp),
        "LC_ALL": "C.UTF-8",
        "ANSIBLE_CONFIG": str(ROOT / "ansible.cfg"),
        "ANSIBLE_HOME": str(tmp / "ansible-home"),
        "ANSIBLE_LOCAL_TEMP": str(tmp / "ansible-local"),
        "ANSIBLE_REMOTE_TEMP": str(tmp / "ansible-remote"),
        "ANSIBLE_RETRY_FILES_ENABLED": "false",
        "ANSIBLE_NOCOLOR": "1",
    }
    argv = ["ansible-playbook", "-i", str(inventory) if inventory else "localhost,",
            "-e", f"@{variables}", *options, str(path)]
    return subprocess.run(argv, cwd=tmp, env=environment, text=True, capture_output=True, check=False)


CLOSE_ROLE = ROOT / "roles/guest_access_close"
AGENT_CONF = "/etc/qemu/qemu-ga.conf"
AGENT_RESTART = ["systemctl", "restart", "qemu-guest-agent.service"]


def close_role_agent_conf() -> tuple[list[str], str]:
    """The allowlist and the file guest_access_close writes, from that role."""
    rpcs = yaml.safe_load((CLOSE_ROLE / "defaults/main.yml").read_text())["guest_access_close_agent_rpcs"]
    tasks = yaml.safe_load((CLOSE_ROLE / "tasks/main.yml").read_text())
    copy = next(task for task in tasks
                if task["name"] == "Restrict the QEMU Guest Agent to the calls HyperLab uses")["ansible.builtin.copy"]
    assert copy["dest"] == AGENT_CONF and copy["owner"] == copy["group"] == "root"
    content = Environment(undefined=StrictUndefined, keep_trailing_newline=True).from_string(copy["content"]).render(
        guest_access_close_agent_rpcs=rpcs)
    return rpcs, content


def render_seeds(cases: dict[str, dict[str, Any]]) -> dict[str, str]:
    """Render user-data.j2 through Ansible with the guest role's own defaults."""
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        out = tmp / "seeds"
        out.mkdir()
        playbook = [{
            "name": "Render guest seeds the way the create operation does",
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "vars_files": [str(ROOT / "roles/guest/defaults/main.yml")],
            "vars": {"guest_repository_root": str(ROOT)},
            "tasks": [{
                "name": "Render one seed",
                "ansible.builtin.copy": {
                    "content": "{{ lookup('ansible.builtin.template', seed_template, template_vars=item.value) }}",
                    "dest": "{{ seed_out }}/{{ item.key }}",
                    "mode": "0600",
                },
                "loop": "{{ seed_cases | dict2items }}",
            }],
        }]
        result = run_playbook(tmp, playbook, {
            "seed_template": str(ROOT / "roles/guest/templates/user-data.j2"),
            "seed_out": str(out),
            "seed_cases": cases,
        })
        assert result.returncode == 0, result.stdout + result.stderr
        return {name: (out / name).read_text(encoding="utf-8") for name in cases}


def seed_case(changes: dict[str, Any], variant: str = "debian12") -> dict[str, Any]:
    """Template variables for one fixture Machine, its plan built by guest_plan.py."""
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec_path, store = standard_fixture(root)
        manifest_path = root / "images/debian.yml"
        manifest = yaml.safe_load(manifest_path.read_text())
        manifest["os_variant"] = variant
        write_yaml(manifest_path, manifest)
        spec = yaml.safe_load(spec_path.read_text())
        spec.update(changes)
        write_yaml(spec_path, spec)
        plan = build_plan(root, spec_path, store)
    groups = yaml.safe_load((ROOT / "group_vars/all/guest.yml").read_text())["guest_admin_groups"]
    return {
        "guest_plan": plan,
        "guest_resolved_timezone": "Europe/Rome",
        "guest_cloud_init_user": "sid",
        "guest_admin_group": groups[re.sub(r"[0-9.]+$", "", variant)],
        "guest_cloud_init_ssh_public_keys": ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGateFixture gate"],
        "guest_vault_listener": (ROOT / "roles/guest/files/hyperlab-vault-listen.py").read_text(),
    }


def agent_entries(seed: dict[str, Any]) -> tuple[list[dict[str, Any]], list[Any]]:
    files = [item for item in (seed.get("write_files") or []) if item["path"] == AGENT_CONF]
    restarts = [command for command in (seed.get("runcmd") or []) if command == AGENT_RESTART]
    return files, restarts


def test_disposable_seed() -> None:
    """ADR 0018: every disposable boot restores the agent restriction itself."""
    rpcs, content = close_role_agent_conf()
    cases = {
        "arch": seed_case({}, "archlinux"),
        "debian": seed_case({}, "debian12"),
        "fedora": seed_case({}, "fedora44"),
        "permanent": seed_case({"lifecycle": "permanent"}),
        "no-agent": seed_case({"qemu_guest_agent": False}),
    }
    rendered = render_seeds(cases)
    for name in ("arch", "debian", "fedora"):
        text = rendered[name]
        assert text.startswith("#cloud-config\n"), f"{name}: the seed lost its header"
        seed = load_unique(text)
        files, restarts = agent_entries(seed)
        assert len(files) == 1, f"{name}: the disposable seed has no agent restriction"
        entry = files[0]
        assert entry["owner"] == "root:root" and entry["permissions"] == "0644", (
            f"{name}: the agent configuration is not root-owned 0644: {entry}")
        assert "defer" not in entry and "append" not in entry and "encoding" not in entry, (
            f"{name}: the agent configuration is not written whole in the init stage: {entry}")
        assert entry["content"] == content, (
            f"{name}: the seed's agent configuration differs from guest_access_close's:\n{entry['content']}")
        configuration = configparser.ConfigParser(interpolation=None, strict=True)
        configuration.read_string(entry["content"])
        assert configuration.sections() == ["general"]
        allowed = [configuration["general"]["allow-rpcs"].split(",")]
        assert allowed == [rpcs], f"{name}: the seed's allowlist differs from the close role: {allowed}"
        assert "guest-exec" not in allowed[0] and "guest-exec-status" not in allowed[0]
        # write_files runs in cloud-init's init stage and runcmd in its final
        # stage, so the restart reads the file the same boot just wrote. The
        # restart comes first: nothing else in the seed waits for it.
        assert restarts == [AGENT_RESTART] and seed["runcmd"][0] == AGENT_RESTART, (
            f"{name}: the restriction is never activated on this boot: {seed.get('runcmd')}")
        assert seed["users"][0]["sudo"] == "ALL=(ALL:ALL) NOPASSWD:ALL"
        assert seed["users"][0]["lock_passwd"] is True
    for name in ("permanent", "no-agent"):
        seed = load_unique(rendered[name])
        assert "write_files" not in seed and "runcmd" not in seed, (
            f"{name}: a Machine that is not a disposable agent Machine gained boot files")

    # The canonical list is read, never copied: the seed follows the file
    # the guest role points at, and that file is guest_access_close's.
    defaults = yaml.safe_load((ROOT / "roles/guest/defaults/main.yml").read_text())
    assert defaults["guest_disposable_agent_policy_file"] == (
        "{{ guest_repository_root }}/roles/guest_access_close/defaults/main.yml"), "the seed reads another policy"
    with tempfile.TemporaryDirectory() as td:
        other = Path(td) / "policy.yml"
        write_yaml(other, {"guest_access_close_agent_rpcs": ["guest-sync", "guest-ping"]})
        moved = render_seeds({"moved": {**cases["debian"], "guest_disposable_agent_policy_file": str(other)}})
    files, _ = agent_entries(load_unique(moved["moved"]))
    assert files and files[0]["content"].endswith("allow-rpcs=guest-sync,guest-ping\n"), (
        "the seed keeps an allowlist of its own instead of reading the close role's")
    check_allowlist_gate(rpcs)


GATE = "Refuse a disposable seed without the canonical agent allowlist"


def check_allowlist_gate(rpcs: list[str]) -> None:
    """create and reset refuse a seed whose allowlist is not the reviewed shape."""
    main = yaml.safe_load((ROOT / "roles/guest/tasks/main.yml").read_text())
    names = [task.get("name") for task in main]
    gate = main[names.index(GATE)]
    assert gate["when"] == ["guest_operation in ['create', 'reset']", "guest_plan.cloud_init",
                            "guest_plan.lifecycle == 'disposable'", "guest_plan.qemu_guest_agent"]
    assert names.index(GATE) < names.index("Install lifecycle dependencies after every read-only gate"), (
        "the allowlist is checked after a host write")
    candidates: dict[str, Any] = {
        "canonical": rpcs, "widened": rpcs + ["guest-file-write"], "narrowed": rpcs[:-1],
        "empty": [], "string": ",".join(rpcs), "missing": None,
        "guest-exec": rpcs + ["guest-exec"], "guest-exec-status": rpcs + ["guest-exec-status"],
        "duplicate": rpcs + [rpcs[0]], "newline": rpcs + ["guest-ping\nallow-rpcs=guest-exec"],
        "comma": rpcs + ["guest-ping,guest-exec"], "mapping": {"guest-ping": True},
    }
    check = {key: value for key, value in gate.items() if key != "when"}
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        plays = []
        for label, candidate in candidates.items():
            plays.append({
                "name": f"Gate {label}", "hosts": "localhost", "connection": "local", "gather_facts": False,
                "vars": {"guest_plan": {"name": "srv-fix-01"},
                         "guest_repository_root": str(ROOT),
                         "guest_disposable_agent_policy_file": str(CLOSE_ROLE / "defaults/main.yml"),
                         **({} if candidate is None else {"guest_disposable_agent_rpcs": candidate})},
                "tasks": [{"name": "Try the gate", "block": [check, {
                    "name": "Record acceptance", "ansible.builtin.copy": {
                        "content": "accepted", "dest": str(tmp / label), "mode": "0600"}}],
                    "rescue": [{"name": "Record refusal", "ansible.builtin.copy": {
                        "content": "refused", "dest": str(tmp / label), "mode": "0600"}}]}],
            })
        result = run_playbook(tmp, plays, {})
        assert result.returncode == 0, result.stdout + result.stderr
        outcome = {label: (tmp / label).read_text() for label in candidates}
    assert outcome.pop("canonical") == "accepted", "the canonical allowlist is refused"
    accepted = [label for label, verdict in outcome.items() if verdict != "refused"]
    assert not accepted, f"the gate let these allowlists reach a seed: {accepted}"


STUB_VIRSH = '''#!{python} -I
"""A virsh stand-in: answers from scenario.json, logs every argv."""
import json
import sys
from pathlib import Path

here = Path(__file__).resolve().parent
argv = sys.argv[1:]
with (here / "calls.jsonl").open("a", encoding="utf-8") as log:
    log.write(json.dumps(argv) + "\\n")
if "qemu-agent-command" in argv:
    key = json.loads(argv[-1])["execute"]
elif "domifaddr" in argv:
    key = "domifaddr"
else:
    key = argv[0]
scenario = json.loads((here / "scenario.json").read_text(encoding="utf-8"))
answers = scenario.get(key) or [{{"rc": 1, "stderr": "error: unexpected call " + key}}]
counter = here / ("count-" + key)
used = int(counter.read_text()) if counter.exists() else 0
counter.write_text(str(used + 1))
answer = answers[min(used, len(answers) - 1)]
sys.stdout.write(answer.get("stdout", ""))
sys.stderr.write(answer.get("stderr", ""))
sys.exit(answer.get("rc", 0))
'''


def write_stub_virsh(directory: Path, scenario: dict[str, list[dict[str, Any]]]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stub = directory / "virsh"
    stub.write_text(STUB_VIRSH.format(python=sys.executable), encoding="utf-8")
    stub.chmod(0o700)
    (directory / "scenario.json").write_text(json.dumps(scenario), encoding="utf-8")
    for old in list(directory.glob("count-*")) + list(directory.glob("calls.jsonl")):
        old.unlink()
    return stub


def stub_calls(directory: Path) -> list[list[str]]:
    log = directory / "calls.jsonl"
    if not log.exists():
        return []
    return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]


def agent_info(exec_enabled: bool) -> dict[str, Any]:
    commands = [{"name": name, "enabled": True, "success-response": True}
                for name in ("guest-sync-delimited", "guest-ping", "guest-info", "guest-file-open")]
    commands.append({"name": "guest-exec", "enabled": exec_enabled, "success-response": True})
    return {"rc": 0, "stdout": json.dumps({"return": {"version": "9.2.0", "supported_commands": commands}})}


AGENT_DOWN = {"rc": 1, "stderr": "error: Guest agent is not responding: QEMU guest agent is not connected\n"}
EXEC_DISABLED = {"rc": 1, "stderr": "error: internal error: unable to execute QEMU agent command 'guest-exec': "
                                    "Command guest-exec has been disabled\n"}
def boot_result(content: str | None = None) -> dict[str, list[dict[str, Any]]]:
    if content is None:
        content = json.dumps({"v1": {"datasource": "DataSourceNoCloud", "errors": []}})
    return {
        "guest-file-open": [{"rc": 1, "stderr": "file not found"}, {"stdout": '{"return":5}'}],
        "guest-file-read": [{"stdout": json.dumps({"return": {
            "count": len(content), "eof": True, "buf-b64": base64.b64encode(content.encode()).decode()}})}],
        "guest-file-close": [{"stdout": '{"return":{}}'}],
    }


START_TASKS = ROOT / "roles/guest/tasks/start.yml"
DECIDE = "Decide whether this start makes a new disposable boot"
PROVE = "Prove a new disposable boot closed its agent before the start succeeds"


def walk_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found = []
    for task in tasks:
        found.append(task)
        for section in ("block", "rescue", "always"):
            found.extend(walk_tasks(task.get(section, [])))
    return found


def start_tasks() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    tasks = yaml.safe_load(START_TASKS.read_text(encoding="utf-8"))
    by_name = {task.get("name"): task for task in tasks}
    return tasks, by_name[DECIDE], by_name[PROVE]


def disposable_start_plan(**changes: Any) -> dict[str, Any]:
    return {"name": "srv-fix-01", "lifecycle": "disposable", "cloud_init": True,
            "qemu_guest_agent": True, **changes}


def run_start_proofs(tmp: Path, cases: dict[str, dict[str, Any]], *options: str,
                     ) -> dict[str, tuple[list[list[str]], str | None, str | None]]:
    """Run start.yml's own decision and proof tasks, one play per case, against stub virsh.

    Each case gives a stub scenario and optionally the domain state and plan.
    The result per case is the stub's calls, the recorded decision (None when
    the proof failed) and the failure message (None when it passed).
    """
    _, decide, prove = start_tasks()
    defaults = yaml.safe_load((ROOT / "roles/guest/defaults/main.yml").read_text())
    plays = []
    for label, case in cases.items():
        out = tmp / label
        out.mkdir()
        stub = write_stub_virsh(out / "stub", {**boot_result(), **case["scenario"]})
        plays.append({
            "name": f"Exercise the managed start's disposable proof: {label}",
            "hosts": "localhost",
            "connection": "local",
            "gather_facts": False,
            "vars": {
                **defaults,
                "guest_repository_root": str(ROOT),
                "guest_python_bin": sys.executable,
                "guest_plan": case.get("plan", disposable_start_plan()),
                "guest_domain_state": case.get("state", "shut off"),
                "guest_virsh_bin": str(stub),
                "guest_qga_timeout_seconds": 2,
                "guest_disposable_agent_poll_seconds": 1,
            },
            "tasks": [{
                "name": "Run the start's proof",
                "block": [decide, prove, {
                    "name": "Record the decision",
                    "check_mode": False,
                    "ansible.builtin.copy": {"content": "{{ guest_start_new_disposable_boot | bool }}",
                                             "dest": str(out / "decision"), "mode": "0600"},
                }],
                "rescue": [{
                    "name": "Record the failure",
                    "check_mode": False,
                    "ansible.builtin.copy": {"content": "{{ ansible_failed_result.msg | default('') }}",
                                             "dest": str(out / "failure"), "mode": "0600"},
                }],
            }],
        })
    result = run_playbook(tmp, plays, {}, *options)
    assert result.returncode == 0, result.stdout + result.stderr
    outcome = {}
    for label in cases:
        out = tmp / label
        decision = out / "decision"
        failure = out / "failure"
        outcome[label] = (stub_calls(out / "stub"), decision.read_text() if decision.exists() else None,
                          failure.read_text() if failure.exists() else None)
    return outcome


def agent_calls(calls: list[list[str]]) -> list[str]:
    return [json.loads(argv[-1])["execute"] for argv in calls if "qemu-agent-command" in argv]


def test_disposable_start_proof() -> None:
    """A new disposable boot is started only once its agent proves guest-exec closed."""
    tasks, decide, prove = start_tasks()
    names = [task.get("name") for task in tasks]
    gate = next(task for task in tasks if task.get("name") == "Gate and start the shut-off domain atomically against other starts")
    assert names.index(DECIDE) < names.index(gate["name"]), "the boot is decided after QEMU started"
    assert names.index("Wait for QEMU Guest Agent readiness") < names.index(PROVE) == len(names) - 1, (
        "something reports the start after the disposable proof, or the proof precedes agent readiness")
    assert prove["when"] == "guest_start_new_disposable_boot | bool"
    boot_wait = prove["block"][0]
    assert boot_wait["name"] == "Wait for this boot's cloud-init to finish without errors", (
        "a restricted base agent can pass readiness before this boot's configuration finishes")
    probes = [task for task in prove["block"] if "ansible.builtin.command" in task
              and "qemu-agent-command" in task["ansible.builtin.command"]["argv"]]
    for task in probes:
        argv = task["ansible.builtin.command"]["argv"]
        assert argv[1:4] == ["qemu-agent-command", "--timeout", "{{ guest_agent_call_timeout_seconds }}"], (
            f"an agent call can block forever: {argv}")
    executes = [json.loads(task["ansible.builtin.command"]["argv"][-1])["execute"] for task in probes]
    assert executes == ["guest-info", "guest-exec"], f"the proof calls {executes}"
    exec_call = json.loads(probes[1]["ansible.builtin.command"]["argv"][-1])
    assert exec_call == {"execute": "guest-exec", "arguments": {"path": "/bin/true"}}, (
        "the probe runs something in the guest")
    power = yaml.safe_load((ROOT / "roles/guest/tasks/power-cycle.yml").read_text())
    assert power[-1]["ansible.builtin.include_tasks"] == "start.yml", "power cycle starts outside the shared path"
    create = [task for task in walk_tasks(yaml.safe_load((ROOT / "roles/guest/tasks/create.yml").read_text()))
              if task.get("name") == "Start after create only when explicitly requested"]
    assert [task["ansible.builtin.include_tasks"] for task in create] == ["start.yml"], (
        "create starts outside the shared path")

    closed = "did not prove its QEMU Guest Agent closed"
    cases: dict[str, dict[str, Any]] = {
        # The restricted agent comes up after one restart: open, then gone,
        # then listed with guest-exec disabled.
        "restarted": {"scenario": {"guest-info": [agent_info(True), AGENT_DOWN, agent_info(False)],
                                   "guest-exec": [EXEC_DISABLED]}},
        "guest-exec ran": {"scenario": {"guest-info": [agent_info(False)],
                                        "guest-exec": [{"rc": 0, "stdout": '{"return":{"pid":7}}'}]}},
        "agent unavailable at the probe": {"scenario": {"guest-info": [agent_info(False)], "guest-exec": [AGENT_DOWN]}},
        "probe timed out": {"scenario": {"guest-info": [agent_info(False)], "guest-exec": [{
            "rc": 1, "stderr": "error: Guest agent is not responding: Guest agent not available for now\n"}]}},
        "unrelated RPC error": {"scenario": {"guest-info": [agent_info(False)], "guest-exec": [{
            "rc": 1, "stderr": "error: internal error: unable to execute QEMU agent command 'guest-exec': "
                               "Invalid parameter 'path'\n"}]}},
        "unrelated disabled message": {"scenario": {"guest-info": [agent_info(False)], "guest-exec": [{
            "rc": 1, "stderr": "error: argument unsupported: QEMU guest agent is disabled\n"}]}},
        # Without the restriction on this boot (a seed from before it) or
        # without an agent, guest-exec is never even tried.
        "cloud-init failed": {"scenario": boot_result('{"v1":{"errors":["runcmd failed"]}}')},
        "cloud-init malformed": {"scenario": boot_result('not JSON')},
        "cloud-init missing errors": {"scenario": boot_result('{"v1":{}}')},
        "cloud-init unfinished": {"scenario": {"guest-file-open": [AGENT_DOWN]}},
        "cloud-init unreadable": {"scenario": {"guest-file-read": [AGENT_DOWN]}},
        "old seed": {"scenario": {"guest-info": [agent_info(True)]}},
        "agent never answers": {"scenario": {"guest-info": [AGENT_DOWN]}},
        "no supported_commands": {"scenario": {"guest-info": [{"rc": 0, "stdout": '{"return":{}}'}]}},
        "not JSON": {"scenario": {"guest-info": [{"rc": 0, "stdout": "guest-exec disabled"}]}},
        # Not a new disposable boot: nothing is asked of the agent.
        "already running": {"state": "running", "scenario": {}},
        "permanent": {"plan": disposable_start_plan(lifecycle="permanent"), "scenario": {}},
        "no cloud-init": {"plan": disposable_start_plan(cloud_init=False), "scenario": {}},
        "no agent": {"plan": disposable_start_plan(qemu_guest_agent=False), "scenario": {}},
    }
    with tempfile.TemporaryDirectory() as td:
        outcome = run_start_proofs(Path(td), cases)
    with tempfile.TemporaryDirectory() as td:
        checked = run_start_proofs(Path(td), {"check mode": {"scenario": {}}}, "--check")

    for case_calls, _, _ in outcome.values():
        for argv in case_calls:
            if "qemu-agent-command" in argv:
                command = json.loads(argv[-1])
                if command["execute"] == "guest-file-open":
                    assert command["arguments"] == {"path": "/run/cloud-init/result.json", "mode": "r"}

    calls, decided, failure = outcome.pop("restarted")
    assert failure is None and decided == "True", f"a new disposable boot did not start: {failure} {decided}"
    assert agent_calls(calls) == ["guest-file-open", "guest-file-open", "guest-file-read", "guest-file-close",
                                  "guest-info", "guest-info", "guest-info", "guest-exec"], calls
    for label in ("guest-exec ran", "agent unavailable at the probe", "probe timed out", "unrelated RPC error",
                  "unrelated disabled message"):
        calls, decided, failure = outcome.pop(label)
        assert decided is None and failure and closed in failure, f"{label}: the start succeeded ({failure})"
        assert agent_calls(calls)[-1] == "guest-exec", f"{label}: {calls}"
    for label in ("old seed", "agent never answers", "no supported_commands", "not JSON",
                  "cloud-init failed", "cloud-init malformed", "cloud-init missing errors",
                  "cloud-init unfinished", "cloud-init unreadable"):
        calls, decided, failure = outcome.pop(label)
        assert decided is None and failure and closed in failure, f"{label}: the start succeeded ({failure})"
        assert "guest-exec" not in agent_calls(calls), f"{label}: guest-exec was tried: {calls}"
        if label.startswith("cloud-init"):
            assert "guest-info" not in agent_calls(calls), f"{label}: readiness ran before cloud-init finished"
    for label, (calls, decided, failure) in {**outcome, **checked}.items():
        assert failure is None, f"{label}: {failure}"
        assert decided == "False" and calls == [], f"{label}: treated as a new disposable boot ({decided}, {calls})"


def test_domain_templates() -> None:
    env = template_env()
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec, store = standard_fixture(root)
        plan = build_plan(root, spec, store)
        rendered = env.get_template("domain.xml.j2").render(
            guest_plan=plan, guest_resolved_memory_mb=2048, guest_vfio={}
        )
        domain = ET.fromstring(rendered)
        assert domain.find("./devices/hostdev") is None
        # ADR 0018: a disposable disk is transient, so every stop discards it.
        assert plan["lifecycle"] == "disposable"
        assert domain.find("./devices/disk[@device='disk']/transient") is not None
        assert domain.find("./devices/disk[@device='cdrom']/transient") is None
        with tempfile.TemporaryDirectory() as xml_dir:
            expected = Path(xml_dir) / "expected.xml"
            actual = Path(xml_dir) / "actual.xml"
            expected.write_text(rendered, encoding="utf-8")
            actual.write_text(rendered.replace("<transient/>", ""), encoding="utf-8")
            kept = run(sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual))
            assert kept.returncode == 1 and "disk_transient" in kept.stderr, kept.stderr
        disk_source = domain.find("./devices/disk[@device='disk']/source")
        disk_dac = disk_source.find("./seclabel[@model='dac']")
        assert disk_dac is not None and disk_dac.get("relabel") == "no"
        assert domain.find("./devices/graphics").get("autoport") == "yes"
        sound = domain.find("./devices/sound")
        assert sound is not None and sound.get("model") == "ich9"
        assert sound.find("./codec").get("type") == "output", "a guest got a capture device"
        assert sound.find("./audio").get("id") == "1"
        audio = domain.find("./devices/audio")
        assert audio is not None and audio.attrib == {"id": "1", "type": "spice"}
        assert domain.find("./devices/input[@type='tablet']") is not None
        assert domain.find("./features/ps2") is None
        assert domain.find("./devices/memballoon").get("model") == "virtio"

        public_keys = ["ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIGateFixture gate"]
        state = yaml.safe_load(env.get_template("state.yml.j2").render(
            guest_plan=plan,
            guest_resolved_memory_mb=2048,
            guest_vfio=None,
            guest_cloud_init_user="sid",
            guest_cloud_init_ssh_public_keys=public_keys,
        ))
        assert state["cloud_init_user"] == "sid"
        assert state["cloud_init_ssh_public_keys"] == public_keys

        user_data = yaml.safe_load(env.get_template("user-data.j2").render(
            guest_plan=plan,
            guest_cloud_init_user="sid",
            guest_cloud_init_ssh_public_keys=public_keys,
            guest_resolved_timezone="Europe/Rome",
            guest_admin_group="wheel",
            guest_disposable_agent_conf=close_role_agent_conf()[1],
        ))
        assert user_data["timezone"] == "Europe/Rome"
        assert user_data["users"][0]["groups"] == ["wheel"]
        assert "password" not in json.dumps(user_data).lower().replace("ssh_pwauth", "")
        assert user_data["disable_root"] is True
        assert user_data["users"][0]["lock_passwd"] is True
        assert user_data["ssh_pwauth"] is False

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec, store, report, profiles, trust = vfio_fixture(root)
        plan = build_plan(root, spec, store)
        result = build_vfio_plan(plan, report, profiles, trust)
        assert result.returncode == 0, result.stderr
        vfio = json.loads(result.stdout)
        looking = yaml.safe_load(
            (ROOT / "group_vars/all/looking-glass.yml").read_text()
        )
        rendered = env.get_template("domain.xml.j2").render(
            guest_plan=plan,
            guest_resolved_memory_mb=6144,
            guest_vfio=vfio,
            hyperlab_looking_glass_spice_socket_dir=looking[
                "hyperlab_looking_glass_spice_socket_dir"
            ],
        )
        domain = ET.fromstring(rendered)
        hostdevs = domain.findall("./devices/hostdev")
        assert len(hostdevs) == 2
        assert plan["lifecycle"] == "permanent"
        assert domain.find("./devices/disk[@device='disk']/transient") is None
        assert all(node.get("managed") == "yes" for node in hostdevs)
        disk_source = domain.find("./devices/disk[@device='disk']/source")
        disk_dac = disk_source.find("./seclabel[@model='dac']")
        assert disk_dac is not None and disk_dac.get("relabel") == "no"
        graphics = domain.find("./devices/graphics")
        assert graphics.get("port") is None
        spice_listen = graphics.find("./listen")
        assert spice_listen is not None
        assert spice_listen.get("type") == "socket"
        assert spice_listen.get("socket", "").startswith("/run/hyperlab-spice/")
        assert spice_listen.get("socket", "").endswith(".sock")
        sound = domain.find("./devices/sound")
        assert sound is not None and sound.get("model") == "ich9"
        assert sound.find("./audio").get("id") == "1"
        audio = domain.find("./devices/audio")
        assert audio is not None and audio.get("type") == "spice"
        assert domain.find("./devices/input[@type='mouse'][@bus='virtio']") is not None
        assert domain.find("./devices/input[@type='keyboard'][@bus='virtio']") is not None
        ps2 = domain.find("./features/ps2")
        assert ps2 is not None and ps2.get("state") == "off"
        assert domain.find("./devices/memballoon").get("model") == "none"
        assert domain.find("./iothreads").text == "1"
        pins = domain.findall("./cputune/vcpupin")
        assert [(node.get("vcpu"), node.get("cpuset")) for node in pins] == [
            ("0", "1"), ("1", "5"), ("2", "2"),
            ("3", "6"), ("4", "3"), ("5", "7"),
        ]
        assert domain.find("./cputune/emulatorpin").get("cpuset") == "0,4"
        assert domain.find("./cputune/iothreadpin").get("cpuset") == "0,4"
        topology = domain.find("./cpu/topology")
        assert topology.attrib == {
            "sockets": "1", "dies": "1", "cores": "3", "threads": "2"
        }
        disk_driver = domain.find("./devices/disk[@device='disk']/driver")
        assert disk_driver.get("iothread") == "1"
        qemu_args = [node.get("value") for node in domain.findall(
            "./{http://libvirt.org/schemas/domain/qemu/1.0}commandline/"
            "{http://libvirt.org/schemas/domain/qemu/1.0}arg"
        )]
        assert any("/dev/kvmfr0" in value for value in qemu_args if value)
        assert any("67108864" in value for value in qemu_args if value)


def test_state_guard() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        spec, store = standard_fixture(root)
        plan = build_plan(root, spec, store)
        state_root = store / "state/vms"
        empty = run(sys.executable, str(STATE_GUARD), "--state-root", str(state_root), stdin=json.dumps(plan))
        assert empty.returncode == 0, empty.stderr
        state_root.mkdir(parents=True)
        collision = {
            "schema_version": 1,
            "name": "other",
            "uuid": "6d7aca2e-5a7b-5c3c-a168-5b094fc306fa",
            "mac": plan["mac"],
            "image": "other-image",
            "instance_policy": "multiple",
        }
        write_yaml(state_root / "other.yml", collision)
        refused = run(sys.executable, str(STATE_GUARD), "--state-root", str(state_root), stdin=json.dumps(plan))
        assert refused.returncode == 2 and "planned MAC collides" in refused.stderr


def test_memory() -> None:
    profile = {
        "host_reserved_mb": 2048,
        "qemu_overhead_per_domain_mb": 512,
        "services_reserved_mb": 0,
        "vfio_fixed_overhead_mb": 256,
        "max_auto_memory_mb": 6144,
        "standard_overcommit_ratio": 1.0,
    }
    standard = run(
        sys.executable, str(MEMORY),
        "--profile-json", json.dumps(profile),
        "--memtotal-mb", "16384",
        "--request", "auto",
        "--floor-mb", "2048",
        "--overcommit", "false",
        "--device-profile", "standard",
    )
    assert standard.returncode == 0, standard.stderr
    standard_result = json.loads(standard.stdout)
    assert standard_result["resolved_memory_mb"] == 6144
    assert standard_result["overhead_mb"] == 512

    vfio = run(
        sys.executable, str(MEMORY),
        "--profile-json", json.dumps(profile),
        "--memtotal-mb", "16384",
        "--request", "auto",
        "--floor-mb", "6144",
        "--overcommit", "false",
        "--device-profile", "vfio",
    )
    assert vfio.returncode == 0, vfio.stderr
    vfio_result = json.loads(vfio.stdout)
    assert vfio_result["vfio_fixed_overhead_mb"] == 256
    assert vfio_result["overhead_mb"] == 768

    refused = run(
        sys.executable, str(MEMORY),
        "--profile-json", json.dumps(profile),
        "--memtotal-mb", "16384",
        "--request", "6144",
        "--floor-mb", "6144",
        "--overcommit", "true",
        "--device-profile", "vfio",
    )
    assert refused.returncode == 2 and "cannot be overcommitted" in refused.stderr


def domain_xml(name: str, bdfs: list[str], port: str = "5900") -> str:
    hostdevs = []
    for bdf in bdfs:
        domain, bus, tail = bdf.split(":")
        slot, function = tail.split(".")
        hostdevs.append(
            "<hostdev type='pci'><source><address "
            f"domain='0x{domain}' bus='0x{bus}' slot='0x{slot}' function='0x{function}'/>")
        hostdevs[-1] += "</source></hostdev>"
    return f"<domain><name>{name}</name><devices>{''.join(hostdevs)}<graphics type='spice' port='{port}' listen='127.0.0.1'/></devices></domain>"


def managed_vfio_xml(name: str, bdfs: list[str], *, profile: str = "vfio", kvmfr: bool = False,
                     namespace: str = "https://github.com/importriri/hyperlab-ansible/hyperlab/1") -> str:
    xml = domain_xml(name, bdfs, port="")
    metadata = f"<metadata><hyperlab:instance xmlns:hyperlab='{namespace}' device-profile='{profile}'/></metadata>"
    xml = xml.replace("<devices>", metadata + "<devices>", 1)
    if kvmfr:
        qemu = "http://libvirt.org/schemas/domain/qemu/1.0"
        xml = xml.replace("<domain>", f"<domain xmlns:qemu='{qemu}'>", 1).replace("</domain>", (
            "<qemu:commandline><qemu:arg value='-object'/><qemu:arg value=\"{'qom-type':'memory-backend-file',"
            "'id':'looking-glass','mem-path':'/dev/kvmfr0','size':67108864,'share':true}\"/></qemu:commandline></domain>"))
    return xml


def test_vfio_registry() -> None:
    planned = ["0000:01:00.0", "0000:01:00.1"]
    safe_payload = {
        "planned_name": "win11clean-test",
        "planned_bdfs": planned,
        "domains": [{"name": "win11clean-test", "xml": domain_xml("win11clean-test", planned)}],
        "active_names": [],
        "spice_port": 5900,
        "mode": "start",
    }
    safe = run(sys.executable, str(VFIO_REGISTRY), stdin=json.dumps(safe_payload))
    assert safe.returncode == 0, safe.stderr

    collision = dict(safe_payload)
    collision["mode"] = "define"
    collision["domains"] = [{"name": "other", "xml": domain_xml("other", [planned[0]])}]
    refused = run(sys.executable, str(VFIO_REGISTRY), stdin=json.dumps(collision))
    assert refused.returncode == 2 and "already assigned" in refused.stderr

    # The GPU is a boot-scoped lease: another managed VFIO domain may name the
    # same functions, but only one of them may run.
    managed = managed_vfio_xml("arch-dev-vfio", planned)
    shared = dict(safe_payload)
    shared["mode"] = "define"
    shared["domains"] = [{"name": "arch-dev-vfio", "xml": managed}]
    accepted = run(sys.executable, str(VFIO_REGISTRY), stdin=json.dumps(shared))
    assert accepted.returncode == 0, accepted.stderr
    legacy = dict(shared)
    legacy["domains"] = [{"name": "arch-dev-vfio", "xml": managed_vfio_xml(
        "arch-dev-vfio", planned, namespace="https://github.com/importriri/privatestack-ansible/hyperlab/1")}]
    accepted = run(sys.executable, str(VFIO_REGISTRY), stdin=json.dumps(legacy))
    assert accepted.returncode == 0, accepted.stderr
    standard = dict(shared)
    standard["domains"] = [{"name": "arch-dev", "xml": managed_vfio_xml("arch-dev", planned, profile="standard")}]
    refused = run(sys.executable, str(VFIO_REGISTRY), stdin=json.dumps(standard))
    assert refused.returncode == 2 and "does not manage" in refused.stderr

    lease = dict(safe_payload)
    lease["planned_name"] = "dev-01"
    lease["domains"] = [
        {"name": "dev-01", "xml": managed_vfio_xml("dev-01", planned, kvmfr=True)},
        {"name": "arch-dev-vfio", "xml": managed_vfio_xml("arch-dev-vfio", planned, kvmfr=True)},
    ]
    accepted = run(sys.executable, str(VFIO_REGISTRY), stdin=json.dumps(lease))
    assert accepted.returncode == 0, accepted.stderr
    running = dict(lease, active_names=["arch-dev-vfio"])
    refused = run(sys.executable, str(VFIO_REGISTRY), stdin=json.dumps(running))
    assert refused.returncode == 2 and "in use by running domain arch-dev-vfio" in refused.stderr

    transport = dict(lease, active_names=["lg-only"])
    transport["domains"] = lease["domains"] + [{"name": "lg-only", "xml": managed_vfio_xml("lg-only", [], kvmfr=True)}]
    refused = run(sys.executable, str(VFIO_REGISTRY), stdin=json.dumps(transport))
    assert refused.returncode == 2 and "/dev/kvmfr0 is in use by running domain lg-only" in refused.stderr

    port_collision = dict(safe_payload)
    port_collision["domains"] = [
        {"name": "win11clean-test", "xml": domain_xml("win11clean-test", planned)},
        {"name": "other", "xml": domain_xml("other", [], port="5900")},
    ]
    port_collision["active_names"] = ["other"]
    refused = run(sys.executable, str(VFIO_REGISTRY), stdin=json.dumps(port_collision))
    assert refused.returncode == 2 and "fixed SPICE port" in refused.stderr


def test_xml_contract() -> None:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        expected = root / "expected.xml"
        actual = root / "actual.xml"
        expected.write_text(domain_xml("vm", ["0000:01:00.0", "0000:01:00.1"]), encoding="utf-8")
        actual.write_text(domain_xml("vm", ["0000:01:00.0", "0000:01:00.1"]), encoding="utf-8")
        ok = run(sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual))
        assert ok.returncode == 0, ok.stderr
        actual.write_text(domain_xml("vm", ["0000:02:00.0", "0000:02:00.1"]), encoding="utf-8")
        drift = run(sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual))
        assert drift.returncode == 1 and "hostdev_bdfs" in drift.stderr

        current_metadata_namespace = (
            "https://github.com/importriri/hyperlab-ansible/hyperlab/1"
        )
        legacy_metadata_namespace = (
            "https://github.com/importriri/privatestack-ansible/hyperlab/1"
        )
        metadata_attributes = (
            "schema='1' image='arch' lifecycle='permanent' "
            "device-profile='vfio' network-profile='dev'"
        )
        expected.write_text(
            f"<domain><metadata><hyperlab:instance xmlns:hyperlab='{current_metadata_namespace}' "
            f"{metadata_attributes}/></metadata><devices/></domain>",
            encoding="utf-8",
        )
        actual.write_text(
            f"<domain><metadata><hyperlab:instance xmlns:hyperlab='{legacy_metadata_namespace}' "
            f"{metadata_attributes}/></metadata><devices/></domain>",
            encoding="utf-8",
        )
        legacy_metadata = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert legacy_metadata.returncode == 0, legacy_metadata.stderr

        actual.write_text(
            "<domain><metadata><foreign:instance xmlns:foreign='urn:foreign' "
            f"{metadata_attributes}/></metadata><devices/></domain>",
            encoding="utf-8",
        )
        foreign_metadata = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert foreign_metadata.returncode == 1 and "metadata" in foreign_metadata.stderr

        actual.write_text(
            "<domain><metadata>"
            f"<current:instance xmlns:current='{current_metadata_namespace}' {metadata_attributes}/>"
            f"<legacy:instance xmlns:legacy='{legacy_metadata_namespace}' {metadata_attributes}/>"
            "</metadata><devices/></domain>",
            encoding="utf-8",
        )
        duplicate_metadata = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert duplicate_metadata.returncode == 2
        assert "multiple supported HyperLab metadata instances" in duplicate_metadata.stderr

        expected.write_text(
            "<domain><devices><disk device='disk'><source file='/disk.qcow2'>"
            "<seclabel model='dac' relabel='no'/></source></disk></devices></domain>",
            encoding="utf-8",
        )
        actual.write_text(
            "<domain><devices><disk device='disk'><source file='/disk.qcow2'/>"
            "</disk></devices></domain>",
            encoding="utf-8",
        )
        missing_dac = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert missing_dac.returncode == 1 and "disk_dac_relabel" in missing_dac.stderr
        legacy_dac = run(
            sys.executable,
            str(XML_CONTRACT),
            "--expected",
            str(expected),
            "--actual",
            str(actual),
            "--allow-legacy-missing-dac-relabel",
        )
        assert legacy_dac.returncode == 0, legacy_dac.stderr

        expected.write_text(
            "<domain><devices><sound model='ich9'><codec type='output'/>"
            "<audio id='1'/></sound><audio id='1' type='spice'/></devices></domain>",
            encoding="utf-8",
        )
        actual.write_text(
            "<domain><devices><audio id='1' type='spice'/></devices></domain>",
            encoding="utf-8",
        )
        missing_sound = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert missing_sound.returncode == 1 and "sound_model" in missing_sound.stderr
        legacy_sound = run(
            sys.executable,
            str(XML_CONTRACT),
            "--expected",
            str(expected),
            "--actual",
            str(actual),
            "--allow-legacy-missing-spice-sound",
        )
        assert legacy_sound.returncode == 0, legacy_sound.stderr

        # A domain defined with the duplex codec is recognised as legacy,
        # never as the playback-only contract, and nothing else passes.
        for codec, strict_ok, legacy_ok in (("duplex", False, True), ("micro", False, False),
                                            ("output", True, True)):
            actual.write_text(
                f"<domain><devices><sound model='ich9'><codec type='{codec}'/>"
                "<audio id='1'/></sound><audio id='1' type='spice'/></devices></domain>",
                encoding="utf-8",
            )
            strict = run(sys.executable, str(XML_CONTRACT), "--expected", str(expected),
                         "--actual", str(actual))
            legacy = run(sys.executable, str(XML_CONTRACT), "--expected", str(expected),
                         "--actual", str(actual), "--allow-legacy-duplex-codec")
            assert (strict.returncode == 0) is strict_ok, (codec, strict.stderr)
            assert (legacy.returncode == 0) is legacy_ok, (codec, legacy.stderr)

        actual.write_text(
            "<domain><devices><sound model='ac97'><audio id='1'/></sound>"
            "<audio id='1' type='spice'/></devices></domain>",
            encoding="utf-8",
        )
        unsafe_sound = run(
            sys.executable,
            str(XML_CONTRACT),
            "--expected",
            str(expected),
            "--actual",
            str(actual),
            "--allow-legacy-missing-spice-sound",
        )
        assert unsafe_sound.returncode == 1 and "sound_model" in unsafe_sound.stderr

        expected.write_text(
            "<domain><devices><disk device='disk'><source file='/disk.qcow2'>"
            "<seclabel model='dac' relabel='no'/></source></disk></devices></domain>",
            encoding="utf-8",
        )
        actual.write_text(
            "<domain><devices><disk device='disk'><source file='/disk.qcow2'>"
            "<seclabel model='dac' relabel='yes'/></source></disk></devices></domain>",
            encoding="utf-8",
        )
        unsafe_dac = run(
            sys.executable,
            str(XML_CONTRACT),
            "--expected",
            str(expected),
            "--actual",
            str(actual),
            "--allow-legacy-missing-dac-relabel",
        )
        assert unsafe_dac.returncode == 1 and "disk_dac_relabel" in unsafe_dac.stderr

        actual.write_text(
            "<domain><devices><disk device='disk'><source file='/disk.qcow2'>"
            "<seclabel model='selinux' relabel='no'/></source></disk></devices></domain>",
            encoding="utf-8",
        )
        foreign_label = run(
            sys.executable,
            str(XML_CONTRACT),
            "--expected",
            str(expected),
            "--actual",
            str(actual),
            "--allow-legacy-missing-dac-relabel",
        )
        assert foreign_label.returncode == 1 and "disk_security_labels" in foreign_label.stderr

        expected.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='q35'>hvm</type>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        actual.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='pc-q35-11.0'>hvm</type>"
            "<firmware><feature enabled='yes' name='secure-boot'/>"
            "<feature enabled='no' name='enrolled-keys'/></firmware>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        canonical = run(sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual))
        assert canonical.returncode == 0, canonical.stderr

        actual.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='pc-i440fx-11.0'>hvm</type>"
            "<firmware><feature enabled='yes' name='secure-boot'/>"
            "<feature enabled='no' name='enrolled-keys'/></firmware>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        wrong_chipset = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert wrong_chipset.returncode == 1 and "machine" in wrong_chipset.stderr

        expected.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='pc-q35-10.0'>hvm</type>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        actual.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='pc-q35-11.0'>hvm</type>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        pinned_version = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert pinned_version.returncode == 1 and "machine" in pinned_version.stderr

        expected.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='q35'>hvm</type>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )

        actual.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='pc-q35-11.0'>hvm</type>"
            "<firmware><feature enabled='yes' name='secure-boot'/>"
            "<feature enabled='yes' name='enrolled-keys'/></firmware>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        secure_drift = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert secure_drift.returncode == 1 and "enrolled_keys" in secure_drift.stderr

        expected.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='q35'>hvm</type>"
            "<firmware><feature enabled='yes' name='secure-boot'/>"
            "<feature enabled='yes' name='enrolled-keys'/></firmware>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        actual.write_text(
            "<domain><os firmware='efi'><type arch='x86_64' machine='pc-q35-11.0'>hvm</type>"
            "<firmware><feature enabled='yes' name='secure-boot'/>"
            "<feature enabled='no' name='enrolled-keys'/></firmware>"
            "</os><devices/></domain>",
            encoding="utf-8",
        )
        secure_required = run(
            sys.executable, str(XML_CONTRACT), "--expected", str(expected), "--actual", str(actual)
        )
        assert secure_required.returncode == 1 and "enrolled_keys" in secure_required.stderr


def test_role_structure() -> None:
    role = ROOT / "roles/guest/tasks"
    text = "\n".join(path.read_text(encoding="utf-8") for path in role.glob("*.yml"))
    assert "ansible.builtin.shell" not in text
    assert "guest_confirm_destroy == guest_plan.name" in text
    assert "guest_confirm_reset == guest_plan.name" in text
    assert "guest_confirm_stop == guest_plan.name" in text
    create = (role / "create.yml").read_text(encoding="utf-8")
    validate = (role / "validate.yml").read_text(encoding="utf-8")
    state = (ROOT / "roles/guest/templates/state.yml.j2").read_text(encoding="utf-8")
    assert create.index("Require safe host-local SSH public keys") < create.index(
        "Validate an already-created guest instead of recreating it"
    )
    assert "cloud_init_user | default('')" in validate
    assert "cloud_init_ssh_public_keys | default([])" in validate
    assert "runtime key while reusing an old seed" in validate
    assert "cloud_init_ssh_public_keys:" in state
    zone_read = create.index("Read the hypervisor time zone for a new Machine")
    zone_check = create.index("Refuse an unknown time zone before any seed is written")
    assert zone_read < zone_check < create.index("Render secret-free cloud-init user data")
    zone_block = create[zone_read:zone_check]
    assert "follow: false" in zone_block
    assert "guest_create_new_transaction" in zone_block
    assert "'UTC' if not guest_host_localtime.stat.exists" in zone_block
    assert "guest_resolved_timezone is match(guest_timezone_pattern)" in create
    assert "'..' not in guest_resolved_timezone" in create
    assert "timezone" not in validate and "timezone" not in state
    admin_read = create.index("Resolve the administrator group of the new Machine's distribution")
    admin_check = create.index("Refuse a distribution without a reviewed administrator group")
    assert admin_read < admin_check < create.index("Render secret-free cloud-init user data")
    assert "guest_create_new_transaction" in create[admin_read:admin_check]
    assert "guest_admin_group" not in validate and "guest_admin_group" not in state
    guest_vars = yaml.safe_load((ROOT / "group_vars/all/guest.yml").read_text(encoding="utf-8"))
    admin_groups = guest_vars["guest_admin_groups"]
    assert admin_groups["archlinux"] == "wheel" and admin_groups["fedora"] == "wheel"
    assert admin_groups["debian"] == "sudo"
    assert "root" not in admin_groups.values()
    for manifest in sorted((ROOT / "images").glob("*.yml")):
        image = yaml.safe_load(manifest.read_text(encoding="utf-8"))
        if image.get("os_family") == "linux":
            family = re.sub(r"[0-9.]+$", "", image["os_variant"])
            assert family in admin_groups, f"{manifest.name}: no administrator group for {family}"
    assert guest_vars["guest_cloud_init_timezone"] == ""
    zone = re.compile(guest_vars["guest_timezone_pattern"].strip())
    for good in ("Europe/Rome", "UTC", "America/Argentina/Buenos_Aires", "Etc/GMT+1"):
        assert zone.fullmatch(good), good
    for bad in ("", "Europe/Rome\nruncmd: [x]", "/etc/passwd", "Europe/../x", "a b"):
        assert not zone.fullmatch(bad), bad
    assert "- -F\n              - qcow2" in create
    assert "guest_plan.base_path" not in "\n".join(
        line for line in create.splitlines() if "state: absent" in line
    )
    destroy = (role / "destroy.yml").read_text(encoding="utf-8")
    assert "guest_plan.base_path" not in destroy
    template = (ROOT / "roles/guest/templates/domain.xml.j2").read_text(encoding="utf-8")
    assert "<hostdev" in template
    assert "qemu:commandline" in template
    assert "guest_vfio.looking_glass_device" in template
    assert "org.qemu.guest_agent.0" in template
    main = (role / "main.yml").read_text(encoding="utf-8")
    assert "vfio.yml" in main
    assert "guest_plan.lock_path" in main
    start = (role / "start.yml").read_text(encoding="utf-8")
    assert "guest_plan.gpu_lock_path" in start
    assert "vfio-registry.yml" in start
    assert "guest_gpu_lock_release.rc != 0" in start


def main() -> int:
    tests = [
        test_standard_plan,
        test_vfio_plan,
        test_domain_templates,
        test_disposable_seed,
        test_disposable_start_proof,
        test_state_guard,
        test_memory,
        test_vfio_registry,
        test_xml_contract,
        test_role_structure,
    ]
    for test in tests:
        test()
    print("guest contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
