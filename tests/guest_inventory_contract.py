#!/usr/bin/env python3
"""Host-independent contract for managed guest runtime inventory.

ADR 0018: every new boot of a disposable Machine has new SSH host keys. The
public managed Start and Power Cycle playbooks run the inventory publisher
after such a boot, as the owner without become, so the pin and the runtime
inventory follow the boot that is running; an already-running target and
check mode publish nothing. Exercised with the real playbooks, a stub virsh
and real strict SSH over a pipe to `sshd -i` (no listening socket).
"""
from __future__ import annotations

import base64
import getpass
import importlib.util
import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

import guest_contract  # noqa: E402

TOOL_PATH = ROOT / "tools" / "guest_agent_address.py"
PUBLISHER = ROOT / "playbooks" / "vm-guest-inventory.yml"
NEW_BOOT = "guest_start_new_disposable_boot | default(false) | bool"
LOCKED_FIRST = "Check whether the operation lock already exists"
LOCKED_LAST = "Execute the selected operation under the lifecycle locks"
MACHINE = "srv-fix-01"
MAC = "52:54:00:6a:01:31"


def load_tool():
    spec = importlib.util.spec_from_file_location("guest_agent_address", TOOL_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_refusal(function, *args: str) -> None:
    try:
        function(*args)
    except ValueError:
        return
    raise AssertionError(f"expected refusal for {args!r}")


def ed25519_line(seed: int = 7) -> str:
    blob = b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes([seed]) * 32
    return "ssh-ed25519 " + base64.b64encode(blob).decode() + " root@dev-01"


def check_host_key_tool() -> None:
    spec = importlib.util.spec_from_file_location("guest_host_key", ROOT / "tools" / "guest_host_key.py")
    assert spec is not None and spec.loader is not None
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)

    line = ed25519_line()
    pinned = tool.known_hosts_line("10.10.3.131", line + "\n")
    assert pinned == "10.10.3.131 " + " ".join(line.split()[:2]), pinned
    expect_refusal(tool.known_hosts_line, "dev-01", line)
    expect_refusal(tool.known_hosts_line, "10.10.3.131", line + "\n" + ed25519_line(8))
    expect_refusal(tool.known_hosts_line, "10.10.3.131", "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAAB root@x")
    short = "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x10" + b"x" * 16).decode()
    expect_refusal(tool.known_hosts_line, "10.10.3.131", short)

    calls = []

    def agent(argv):
        assert argv[:5] == ["/usr/bin/virsh", "-c", "qemu:///system", "qemu-agent-command", "dev-01"]
        command = json.loads(argv[5])
        calls.append(command["execute"])
        if command["execute"] == "guest-file-open":
            assert command["arguments"] == {"path": "/etc/ssh/ssh_host_ed25519_key.pub", "mode": "r"}
            return json.dumps({"return": 5})
        if command["execute"] == "guest-file-read":
            return json.dumps({"return": {"count": len(line), "eof": True,
                                          "buf-b64": base64.b64encode(line.encode()).decode()}})
        return json.dumps({"return": {}})

    content = tool.read_guest_file(agent, Path("/usr/bin/virsh"), "dev-01", tool.HOST_KEY_PATH)
    assert content == line and calls == ["guest-file-open", "guest-file-read", "guest-file-close"]


def entry_playbook(name: str, tmp: Path) -> list[dict[str, Any]]:
    """Run the public lifecycle and publisher with fixture hardware discovery."""
    source = yaml.safe_load((ROOT / "playbooks" / name).read_text(encoding="utf-8"))
    assert isinstance(source, list) and len(source) == 2, f"{name}: {source}"
    lifecycle, publish = source
    assert lifecycle["become"] is True and lifecycle["roles"][-1] == "guest", f"{name} lost its guest play"
    assert set(publish) == {"name", "ansible.builtin.import_playbook", "when"}, f"{name} changes how the publisher runs: {publish}"
    assert publish["ansible.builtin.import_playbook"] == "vm-guest-inventory.yml", f"{name} imports {publish['ansible.builtin.import_playbook']}"
    assert publish["when"] == NEW_BOOT, f"{name} publishes on {publish['when']!r}"
    # Run the real per-Machine locking of the guest role and the real shared
    # start tasks, including start/domstate, locks and readiness. Hardware
    # inspection and capacity discovery are fixtures; their own contracts
    # cover them. Every libvirt argv goes to the stub.
    task_dir = tmp / "lifecycle"
    task_dir.mkdir(exist_ok=True)
    main = yaml.safe_load((ROOT / "roles/guest/tasks/main.yml").read_text(encoding="utf-8"))
    names = [task.get("name") for task in main]
    guest_contract.write_yaml(task_dir / "locked.yml", main[names.index(LOCKED_FIRST):names.index(LOCKED_LAST) + 1])
    for filename in ("start.yml", "power-cycle.yml"):
        shutil.copy(ROOT / "roles/guest/tasks" / filename, task_dir / filename)
    guest_contract.write_yaml(task_dir / "validate.yml", [{
        "name": "Use the validated fixture domain", "ansible.builtin.assert": {
            "that": ["guest_plan.device_profile == 'standard'"]}}])
    guest_contract.write_yaml(task_dir / "memory.yml", [{
        "name": "Use the fixture capacity", "ansible.builtin.debug": {"msg": "capacity available"}}])
    guest_contract.write_yaml(task_dir / "inspect.yml", [{
        "name": "Observe the stopped fixture", "ansible.builtin.set_fact": {"guest_domain_state": "shut off"}}])
    return [
        {"name": lifecycle["name"], "hosts": lifecycle["hosts"], "gather_facts": False,
         "vars_files": [str(ROOT / "roles/guest/defaults/main.yml")],
         "vars": {"guest_operation": lifecycle["vars"]["guest_operation"]},
         "tasks": [{"name": "Exercise the lifecycle under its locks",
                    "ansible.builtin.include_tasks": str(task_dir / "locked.yml")}]},
        {**publish, "ansible.builtin.import_playbook": str(PUBLISHER)},
    ]


# Stands in for the publisher's Python: runs the real tool, then, after each
# tool named in PAUSE_AFTER, waits until the test releases it.
PAUSE_AFTER = ("plan_tool.py", "guest_host_key.py")
PAUSING_PYTHON = '''#!{python} -I
import subprocess
import sys
import time
from pathlib import Path

here = Path(__file__).resolve().parent
result = subprocess.run([{python!r}, *sys.argv[1:]], check=False)
for name in {pause_after!r}:
    if any(arg.endswith(name) for arg in sys.argv[1:]):
        (here / ("paused-" + name)).touch()
        deadline = time.monotonic() + 300
        while not (here / ("release-" + name)).exists() and time.monotonic() < deadline:
            time.sleep(0.1)
sys.exit(result.returncode)
'''


def boot_scenario(address: str, host_key: str) -> dict[str, list[dict[str, Any]]]:
    evidence = (" Name       MAC address          Protocol     Address\n"
                "-------------------------------------------------------------------------------\n"
                " lo         00:00:00:00:00:00    ipv4         127.0.0.1/8\n"
                f" enp1s0     {MAC}    ipv4         {address}/24\n")
    read = {"count": len(host_key), "eof": True, "buf-b64": base64.b64encode(host_key.encode()).decode()}
    return {
        "domifaddr": [{"stdout": evidence}],
        "guest-file-open": [{"stdout": json.dumps({"return": 5})}],
        "guest-file-read": [{"stdout": json.dumps({"return": read})}],
        "guest-file-close": [{"stdout": json.dumps({"return": {}})}],
    }


class Lab:
    """One operator home, runtime directory and Machine, all in a temporary tree."""

    def __init__(self, tmp: Path) -> None:
        self.tmp = tmp
        self.user = getpass.getuser()
        self.home = tmp / "home"
        (self.home / ".ssh").mkdir(parents=True, mode=0o700)
        self.known_hosts = self.home / ".ssh/known_hosts"
        self.known_hosts.write_text("", encoding="utf-8")
        self.run = tmp / "run"
        self.run.mkdir(mode=0o700)
        self.inventory = self.run / f"{MACHINE}.ini"
        self.stubs = tmp / "stub"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "operator",
                        "-f", str(self.home / ".ssh/hyperlab_ed25519")], check=True)
        authorized = tmp / "authorized_keys"
        shutil.copy(self.home / ".ssh/hyperlab_ed25519.pub", authorized)
        authorized.chmod(0o600)
        plan = {"name": MACHINE, "os_family": "linux", "cloud_init": True, "qemu_guest_agent": True,
                "lifecycle": "disposable", "network_profile": "lab", "owner": self.user, "mac": MAC,
                "device_profile": "standard", "capacity_lock_path": str(tmp / "capacity.lock"),
                "lock_path": str(tmp / f"{MACHINE}.lock")}
        (tmp / "plan.json").write_text(json.dumps(plan), encoding="utf-8")
        self.plan_tool = tmp / "plan_tool.py"
        self.plan_tool.write_text("import pathlib, sys\nsys.stdout.write((pathlib.Path(__file__).parent"
                                  " / 'plan.json').read_text())\n", encoding="utf-8")
        self.plan = plan

    def host_key(self, boot: int) -> Path:
        key = self.tmp / f"host-key-{boot}"
        if not key.exists():
            subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", f"root@boot-{boot}",
                            "-f", str(key)], check=True)
        return key

    @property
    def identity_lock(self) -> Path:
        """The owner's publication lock, held from before the boot until the pin."""
        return self.run / f"{MACHINE}.inventory.lock"

    def unlocked(self) -> bool:
        return not self.identity_lock.exists() and not Path(self.plan["lock_path"]).exists()

    def start(self, playbook: str, scenario: dict[str, list[dict[str, Any]]], *options: str,
              state: str = "shut off") -> tuple[subprocess.CompletedProcess[str], list[list[str]]]:
        argv, environment = self.invocation(playbook, scenario, *options, state=state, stubs=self.stubs)
        result = subprocess.run(argv, cwd=self.tmp, env=environment, text=True, capture_output=True, check=False)
        return result, guest_contract.stub_calls(self.stubs)

    def invocation(self, playbook: str, scenario: dict[str, list[dict[str, Any]]], *options: str,
                   state: str, stubs: Path, python: str = sys.executable,
                   host_key_tool: Path = ROOT / "tools/guest_host_key.py") -> tuple[list[str], dict[str, str]]:
        scenario = {**guest_contract.boot_result(), "guestinfo": [{"stdout": "hostname: fixture"}],
                    "guest-info": [guest_contract.agent_info(False)], "guest-exec": [guest_contract.EXEC_DISABLED],
                    "start": [{}], "domstate": [{"stdout": "running"}], "destroy": [{}], **scenario}
        if playbook == "vm-power-cycle.yml":
            scenario["domstate"] = [{"stdout": "shut off"}, {"stdout": "running"}]
        stub = guest_contract.write_stub_virsh(stubs, scenario)
        if playbook == PUBLISHER.name:
            plays = [{"name": "Publish on its own", "ansible.builtin.import_playbook": str(PUBLISHER)}]
        else:
            plays = entry_playbook(playbook, self.tmp)
            plays[0]["vars"]["guest_domain_state"] = state
        return guest_contract.playbook_invocation(self.tmp, plays, {
            "guest_spec": f"vm-specs/.generated/{MACHINE}.yml",
            "guest_plan": self.plan,
            "guest_cloud_init_user": self.user,
            "guest_repository_root": str(ROOT), "guest_python_bin": sys.executable,
            "guest_virsh_bin": str(stub), "guest_mkdir_bin": "/usr/bin/mkdir", "guest_rmdir_bin": "/usr/bin/rmdir",
            "guest_existing_state": {"memory_mb": 2048}, "guest_confirm_power_cycle": MACHINE,
            "guest_qga_timeout_seconds": 2, "guest_disposable_agent_poll_seconds": 1,
            "guest_wait_for_qga": True,
            "guest_inventory_plan_tool": str(self.plan_tool),
            "guest_inventory_python_bin": python,
            "guest_inventory_virsh_bin": str(stub),
            "guest_inventory_address_tool": str(ROOT / "tools/guest_agent_address.py"),
            "guest_inventory_host_key_tool": str(host_key_tool),
            "guest_inventory_operator_home": str(self.home),
            "guest_inventory_runtime_path": str(self.run),
            "guest_identity_lock_root": str(self.run),
        }, *options, inventory=ROOT / "inventory.ini")

    def boot_scenario(self, boot: int, address: str) -> dict[str, list[dict[str, Any]]]:
        public = self.host_key(boot).with_suffix(".pub").read_text(encoding="utf-8")
        scenario = boot_scenario(address, public)
        # The cloud-init result is read before the public host key.
        scenario["guest-file-open"] = [{"stdout": '{"return":5}'}] * 2
        scenario["guest-file-read"] = guest_contract.boot_result()["guest-file-read"] + scenario["guest-file-read"]
        return scenario

    def boot(self, playbook: str, boot: int, address: str) -> None:
        scenario = self.boot_scenario(boot, address)
        result, calls = self.start(playbook, scenario, state="running" if playbook == "vm-power-cycle.yml" else "shut off")
        assert result.returncode == 0, result.stdout + result.stderr
        assert self.unlocked(), f"{playbook} left a lock behind"
        commands = guest_contract.agent_calls(calls)
        assert commands == ["guest-file-open", "guest-file-read", "guest-file-close", "guest-info", "guest-exec",
                            "guest-file-open", "guest-file-read", "guest-file-close"], calls
        assert sum(argv[0] == "start" for argv in calls) == 1, calls
        if playbook == "vm-power-cycle.yml":
            assert calls[:2] == [["destroy", MACHINE], ["domstate", MACHINE]], calls
            assert calls.index(["destroy", MACHINE]) < calls.index(["start", MACHINE]), calls
        # The new boot's proof waits for the agent itself; nothing else does.
        assert not any(argv[0] == "guestinfo" for argv in calls), calls
        assert calls.index(["start", MACHINE]) < next(
            i for i, argv in enumerate(calls) if "qemu-agent-command" in argv), calls
        assert any(argv[1:3] == ["qemu:///system", "domifaddr"] for argv in calls), calls

    def pins(self) -> dict[str, list[str]]:
        pins: dict[str, list[str]] = {}
        for line in self.known_hosts.read_text(encoding="utf-8").splitlines():
            host, kind, key = line.split()[:3]
            pins.setdefault(host, []).append(f"{kind} {key}")
        return pins

    def record(self) -> dict[str, str]:
        lines = self.inventory.read_text(encoding="utf-8").splitlines()
        assert lines[0] == "[workstations]" and len(lines) == 2, lines
        fields = shlex.split(lines[1])
        assert fields[0] == MACHINE, fields
        return dict(field.split("=", 1) for field in fields[1:])

    def ssh(self, boot: int) -> subprocess.CompletedProcess[str]:
        """Strict SSH with the published inventory's own arguments, to a
        server that holds the given boot's host key."""
        sshd = shutil.which("sshd", path="/usr/sbin:/usr/bin:/sbin:/bin")
        assert sshd, "the strict-SSH proof needs OpenSSH's sshd (it serves one connection on a pipe)"
        config = self.tmp / f"sshd-{boot}.conf"
        config.write_text("\n".join([
            f"HostKey {self.host_key(boot)}", f"AuthorizedKeysFile {self.tmp / 'authorized_keys'}",
            "StrictModes no", "PasswordAuthentication no", "KbdInteractiveAuthentication no",
            "UsePAM no", "PidFile none", ""]), encoding="utf-8")
        record = self.record()
        argv = ["ssh", "-F", "/dev/null", *shlex.split(record["ansible_ssh_common_args"]),
                "-o", "GlobalKnownHostsFile=/dev/null", "-i", record["ansible_ssh_private_key_file"],
                "-o", f"ProxyCommand={sshd} -i -f {config} -E {self.tmp / 'sshd.log'}",
                "-l", record["ansible_user"], record["ansible_host"], "true"]
        environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(self.tmp), "LC_ALL": "C"}
        return subprocess.run(argv, env=environment, text=True, capture_output=True, check=False, timeout=60)


def check_publisher_entries() -> None:
    """Only Start and Power Cycle publish; Create and Reset keep the explicit inventory step."""
    for name in ("vm-create.yml", "vm-reset.yml"):
        plays = yaml.safe_load((ROOT / "playbooks" / name).read_text(encoding="utf-8"))
        assert [play.get("ansible.builtin.import_playbook") for play in plays] == [None], (
            f"{name} imports a playbook; docs/first-machine.md says it needs the inventory step")
        assert plays[0]["roles"][-1] == "guest", f"{name} lost its guest play"


def check_disposable_repin() -> None:
    with tempfile.TemporaryDirectory() as td:
        lab = Lab(Path(td))

        def public(boot: int) -> str:
            return " ".join(lab.host_key(boot).with_suffix(".pub").read_text().split()[:2])

        lab.boot("vm-start.yml", 1, "10.10.4.31")
        assert lab.pins() == {"10.10.4.31": [public(1)]}, lab.pins()
        assert lab.ssh(1).returncode == 0, lab.ssh(1).stderr

        # The second start of the same Machine: same address, new host key.
        lab.boot("vm-start.yml", 2, "10.10.4.31")
        assert lab.pins() == {"10.10.4.31": [public(2)]}, f"the second boot was not pinned: {lab.pins()}"
        record = lab.record()
        assert record["ansible_host"] == "10.10.4.31" and "StrictHostKeyChecking=yes" in record["ansible_ssh_common_args"]
        assert lab.ssh(2).returncode == 0, f"strict SSH to the second boot failed: {lab.ssh(2).stderr}"
        stale = lab.ssh(1)
        assert stale.returncode == 255 and "Host key verification failed" in stale.stderr, (
            f"strict SSH accepted the first boot's key: {stale.returncode} {stale.stderr}")

        # A power cycle is a new boot too; here its lease moved.
        lab.boot("vm-power-cycle.yml", 3, "10.10.4.32")
        assert lab.pins()["10.10.4.32"] == [public(3)], f"the power-cycled boot was not pinned: {lab.pins()}"
        assert lab.record()["ansible_host"] == "10.10.4.32", "the inventory names the earlier boot's address"
        assert lab.ssh(3).returncode == 0, lab.ssh(3).stderr
        assert lab.ssh(2).returncode == 255, "strict SSH accepted the second boot's key after the power cycle"

        before = (lab.known_hosts.read_text(), lab.inventory.read_text())
        # A boot whose key cannot be read through the agent fails the start
        # and leaves the pin alone; nothing reads a key from the network.
        failing = boot_scenario("10.10.4.32", "")
        failing["guest-file-open"] = [{"stdout": '{"return":5}'},
                                      {"rc": 1, "stderr": "error: Guest agent is not responding\n"}]
        failing["guest-file-read"] = guest_contract.boot_result()["guest-file-read"]
        result, _ = lab.start("vm-start.yml", failing)
        assert result.returncode != 0, "a start whose host key could not be pinned succeeded"
        assert "Read the guest SSH host key through QEMU Guest Agent" in result.stdout, result.stdout
        assert (lab.known_hosts.read_text(), lab.inventory.read_text()) == before, "a failed pin changed the pin"
        assert lab.unlocked(), "a failed key read left a lock behind"

        failing["domifaddr"] = [{"stdout": "no managed IPv4 address"}]
        result, _ = lab.start("vm-start.yml", failing)
        assert result.returncode != 0, "a start whose address could not be discovered succeeded"
        assert "Resolve the unique managed guest address through QEMU Guest Agent" in result.stdout
        assert (lab.known_hosts.read_text(), lab.inventory.read_text()) == before, "failed discovery changed the pin"
        assert lab.unlocked(), "failed discovery left a lock behind"

        # Not a new boot: no discovery, no pin, no inventory.
        for label, playbook, options, state in (
            ("already running", "vm-start.yml", (), "running"),
            ("check mode", "vm-start.yml", ("--check",), "shut off"),
            ("check mode", "vm-power-cycle.yml", ("--check",), "running"),
        ):
            result, calls = lab.start(playbook, boot_scenario("10.10.4.33", public(4)), *options, state=state)
            assert result.returncode == 0, f"{label} {playbook}: {result.stdout}{result.stderr}"
            assert not any("qemu-agent-command" in argv or "domifaddr" in argv or argv[0] in ("start", "destroy")
                           for argv in calls), f"{label} {playbook}: boot or publisher ran ({calls})"
            assert lab.unlocked(), f"{label} {playbook}: a lock was left behind"
        assert (lab.known_hosts.read_text(), lab.inventory.read_text()) == before, "a start that made no boot repinned"


def failed_task(output: str) -> str | None:
    """The name of the task whose result was the run's first fatal one."""
    task = None
    for line in output.splitlines():
        if line.startswith("TASK [") and "]" in line:
            task = line[len("TASK ["):line.rindex("]")]
        elif line.startswith("fatal:"):
            return task
    return None


def check_pin_failure() -> None:
    """Discovery succeeds, but replacing the pin fails: the start fails and nothing is published."""
    with tempfile.TemporaryDirectory() as td:
        lab = Lab(Path(td))
        lab.boot("vm-start.yml", 1, "10.10.4.31")
        before = (lab.known_hosts.read_text(), lab.inventory.read_text())
        # A key tool that succeeds with a line for another address: the
        # known_hosts module refuses it, also when the contract runs as root.
        public = " ".join(lab.host_key(2).with_suffix(".pub").read_text().split()[:2])
        tool = lab.tmp / "other_host_key.py"
        tool.write_text(f"print({('10.10.4.99 ' + public)!r})\n", encoding="utf-8")
        argv, environment = lab.invocation("vm-start.yml", lab.boot_scenario(2, "10.10.4.31"), state="shut off",
                                           stubs=lab.stubs, host_key_tool=tool)
        result = subprocess.run(argv, cwd=lab.tmp, env=environment, text=True, capture_output=True, check=False)
        assert result.returncode != 0, "a start whose pin could not be replaced succeeded"
        assert failed_task(result.stdout) == "Pin the guest SSH host key for strict checking", result.stdout
        assert (lab.known_hosts.read_text(), lab.inventory.read_text()) == before, (
            "a failed pin replacement still changed the pin or published inventory")
        assert lab.unlocked(), "a failed pin replacement left a lock behind"


def check_concurrent_publication() -> None:
    """A Power Cycle cannot cross its stop/start boundary while a Start is still pinning."""
    with tempfile.TemporaryDirectory() as td:
        lab = Lab(Path(td))
        pause = lab.tmp / "pause"
        pause.mkdir()
        python = pause / "python"
        python.write_text(PAUSING_PYTHON.format(python=sys.executable, pause_after=PAUSE_AFTER), encoding="utf-8")
        python.chmod(0o700)
        argv, environment = lab.invocation("vm-start.yml", lab.boot_scenario(1, "10.10.4.31"), state="shut off",
                                           stubs=lab.tmp / "stub-a", python=str(python))
        first = subprocess.Popen(argv, cwd=lab.tmp, env=environment, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            # Start A pauses twice: as its publisher begins, after the
            # lifecycle play ended (before the publisher takes anything), and
            # after it read boot 1's key, before that key is pinned.
            for attempt, name in enumerate(PAUSE_AFTER):
                deadline = time.monotonic() + 300
                while not (pause / f"paused-{name}").exists():
                    assert first.poll() is None, f"the first start ended before its pin: {first.communicate()[0]}"
                    assert time.monotonic() < deadline, f"the first start never reached {name}"
                    time.sleep(0.1)
                stubs = lab.tmp / f"stub-b{attempt}"
                argv, environment = lab.invocation("vm-power-cycle.yml", lab.boot_scenario(2, "10.10.4.31"),
                                                   state="running", stubs=stubs)
                second = subprocess.run(argv, cwd=lab.tmp, env=environment, text=True, capture_output=True,
                                        check=False)
                calls = guest_contract.stub_calls(stubs)
                assert second.returncode != 0, f"after {name}: a power cycle ran while another start was still pinning"
                assert not any(argv[0] in ("destroy", "start") for argv in calls), (
                    f"after {name}: the power cycle crossed its stop/start boundary during the other publication: {calls}")
                assert "is still publishing" in second.stdout, second.stdout
                assert lab.identity_lock.is_dir(), f"after {name}: the refused power cycle released the other lock"
                (pause / f"release-{name}").touch()
        finally:
            for name in PAUSE_AFTER:
                (pause / f"release-{name}").touch()
            output = first.communicate(timeout=300)[0]
        assert first.returncode == 0, output
        assert lab.unlocked(), "the first start left a lock behind"
        assert lab.ssh(1).returncode == 0, lab.ssh(1).stderr

        # Once the first publication is done, the power cycle goes through
        # and its boot is the one pinned.
        lab.boot("vm-power-cycle.yml", 2, "10.10.4.31")
        public = " ".join(lab.host_key(2).with_suffix(".pub").read_text().split()[:2])
        assert lab.pins() == {"10.10.4.31": [public]}, lab.pins()
        assert lab.ssh(2).returncode == 0, lab.ssh(2).stderr
        stale = lab.ssh(1)
        assert stale.returncode == 255 and "Host key verification failed" in stale.stderr, stale.stderr

        # Run on its own, the publisher takes the same lock: it refuses while
        # a start holds it and leaves none behind when it is done.
        public = lab.host_key(2).with_suffix(".pub").read_text(encoding="utf-8")
        lab.identity_lock.mkdir()
        result, _ = lab.start(PUBLISHER.name, boot_scenario("10.10.4.31", public))
        assert result.returncode != 0, "the publisher ran on its own while a start held the lock"
        assert "is being started or published" in result.stdout, result.stdout
        assert lab.identity_lock.is_dir(), "the refused publisher removed a lock it did not take"
        lab.identity_lock.rmdir()
        result, _ = lab.start(PUBLISHER.name, boot_scenario("10.10.4.31", public))
        assert result.returncode == 0, result.stdout + result.stderr
        assert lab.unlocked(), "the publisher on its own left its lock behind"
        assert lab.ssh(2).returncode == 0, lab.ssh(2).stderr


def main() -> int:
    tool = load_tool()

    assert tool.LIBVIRT_URI == "qemu:///system"
    assert tool.domifaddr_argv(
        Path("/usr/bin/virsh"),
        "arch-dev-vfio",
    ) == [
        "/usr/bin/virsh",
        "-c",
        "qemu:///system",
        "domifaddr",
        "arch-dev-vfio",
        "--source",
        "agent",
        "--full",
    ]

    evidence = """\
 Name       MAC address          Protocol     Address
-------------------------------------------------------------------------------
 lo         00:00:00:00:00:00    ipv4         127.0.0.1/8
 enp1s0     52:54:00:d4:21:89    ipv4         10.10.3.198/24
 enp1s0     52:54:00:d4:21:89    ipv6         fe80::5054:ff:fed4:2189/64
"""
    assert (
        tool.resolve_address(evidence, "52:54:00:d4:21:89", "10.10.3.0/24")
        == "10.10.3.198"
    )
    expect_refusal(
        tool.resolve_address,
        evidence,
        "52:54:00:d4:21:89",
        "10.10.5.0/24",
    )
    expect_refusal(
        tool.resolve_address,
        evidence + "enp1s0 52:54:00:d4:21:89 ipv4 10.10.3.199/24\n",
        "52:54:00:d4:21:89",
        "10.10.3.0/24",
    )
    expect_refusal(
        tool.resolve_address,
        evidence,
        "not-a-mac",
        "10.10.3.0/24",
    )

    check_host_key_tool()

    playbook = yaml.safe_load(
        (ROOT / "playbooks" / "vm-guest-inventory.yml").read_text(
            encoding="utf-8"
        )
    )
    assert isinstance(playbook, list) and len(playbook) == 1
    play = playbook[0]
    assert play["hosts"] == "hypervisor"
    assert play["become"] is False, (
        "runtime guest inventory must remain unprivileged"
    )
    tasks = play["tasks"]
    names = [task["name"] for task in tasks]
    assert "Resolve the unique managed guest address through QEMU Guest Agent" in names
    assert "Publish the strict runtime workstation inventory" in names
    read = names.index("Read the guest SSH host key through QEMU Guest Agent")
    pin = names.index("Pin the guest SSH host key for strict checking")
    resolve = names.index("Resolve the unique managed guest address through QEMU Guest Agent")
    assert resolve < read < pin < names.index("Build the strict runtime workstation inventory record")
    pin_task = tasks[pin]["ansible.builtin.known_hosts"]
    assert pin_task["state"] == "present" and pin_task["hash_host"] is False
    assert pin_task["name"] == "{{ guest_inventory_address.stdout }}"
    assert "ssh-keyscan" not in (ROOT / "playbooks" / "vm-guest-inventory.yml").read_text(), (
        "a host key is never accepted from the network"
    )

    rendered_source = (ROOT / "playbooks" / "vm-guest-inventory.yml").read_text(
        encoding="utf-8"
    )
    assert "guest_agent_address.py" in rendered_source
    assert "guest_inventory_effective_uid" in rendered_source
    assert "[workstations]" in rendered_source
    assert "StrictHostKeyChecking=yes" in rendered_source
    assert "UserKnownHostsFile=" in rendered_source
    assert "IdentitiesOnly=yes" in rendered_source
    assert "ansible_ssh_use_tty=false" in rendered_source, (
    "runtime guest inventory must disable SSH pseudo-TTY allocation"
)
    assert "mode: '0600'" in rendered_source
    vm_source = (
        ROOT
        / "tools"
        / "hyperlabctl"
        / "hyperlabctl"
        / "commands"
        / "vm.py"
    ).read_text(encoding="utf-8")

    assert 'sub.add_parser(\n            "inventory"' in vm_source
    assert 'target_choices("spec", repo_root)' in vm_source
    assert "playbooks/vm-guest-inventory.yml" in vm_source
    assert '"guest_spec=%s" % args.spec' in vm_source
    assert '"-K"' not in vm_source

    opener_source = (
        ROOT
        / "tools"
        / "hyperlabctl"
        / "hyperlabctl"
        / "commands"
        / "open.py"
    ).read_text(encoding="utf-8")

    assert "def _runtime_inventory(ctx, domain):" in opener_source
    assert (
        "return _publish_runtime_inventory(ctx, domain, inventory)"
        in opener_source
    )
    assert (
        "runtime_inventory = _runtime_inventory(ctx, domain)"
        in opener_source
    )
    assert "stat.S_ISLNK" in opener_source
    assert "stat.S_ISREG" in opener_source
    assert "stat.S_IMODE(info.st_mode) != 0o600" in opener_source

    publish = opener_source.split(
        "def _publish_runtime_inventory(ctx, domain, inventory):",
        1,
    )[1].split(
        "\n\ndef _runtime_inventory(ctx, domain):",
        1,
    )[0]

    assert '_executable("hyperlabctl")' in publish
    assert '"vm",' in publish
    assert '"inventory",' in publish
    assert '"--repo",' in publish
    assert "ansible-playbook" not in publish

    registry_source = (
        ROOT
        / "tools"
        / "hyperlabctl"
        / "hyperlabctl"
        / "registry.py"
    ).read_text(encoding="utf-8")

    inventory_action = registry_source.split(
        '"id": "vm.inventory"',
        1,
    )[1].split(
        "\n    },",
        1,
    )[0]

    assert (
        '["hyperlabctl", "vm", "inventory", "{spec}"]'
        in inventory_action
    )
    assert '"privileged": False' in inventory_action
    assert '"requires": None' in inventory_action

    check_publisher_entries()
    check_disposable_repin()
    check_pin_failure()
    check_concurrent_publication()
    print("managed guest inventory contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
