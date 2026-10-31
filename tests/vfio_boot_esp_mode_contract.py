#!/usr/bin/env python3
"""vfio_boot asks for the file mode the ESP keeps
(problems/vfio-boot-modes-on-vfat-esp.md).

arch-bootstrap mounts the ESP on /boot as vfat. A vfat file's mode comes
from the mount (fmask, showexec), and chmod cannot change it, so a fixed
0644 on the boot entries and loader.conf was a change on every run of the
Nitro, whose ESP gives 0755. The role now reads the mount of every /boot
directory it writes into with findmnt, and tools/esp_file_mode.py decides
the mode: the one vfat gives, or the role's 0644 on a filesystem that keeps
modes. Anything it cannot decide, or a mount that lets anyone but root
write a boot entry or create one in a boot directory (dmask), is a
refusal.

This contract runs the tool on findmnt documents, executes the four real
decision tasks under Ansible with synthetic observations, and reads the
role's tasks. No mount probe or boot write reaches the host.
"""
from __future__ import annotations

import json
import os
import posixpath
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/vfio_boot"
TOOL = ROOT / "tools/esp_file_mode.py"
NITRO_OPTIONS = ("rw,relatime,fmask=0022,dmask=0022,codepage=437,iocharset=ascii,"
                 "shortname=mixed,utf8,errors=remount-ro")
MODE_FACT = "{{ vfio_boot_loader_file_mode }}"
DECISION_NAMES = (
    "Read the mount of every directory the boot files go into",
    "Decide the file mode the ESP keeps",
    "Pin the boot files' mode",
    "Refuse a boot file mode that is not a 0NNN string",
)
EXPECTED_MODE_NAME = "Verify the executed ESP mode fact"
FIXTURE_GUARD_NAME = "Verify isolated ESP fixture dependencies"
DIRECTORIES = ("/boot/loader", "/boot/loader/entries")
EXPECTED_CALLS = [["-J", "-T", directory, "-o", "TARGET,FSTYPE,OPTIONS"]
                  for directory in DIRECTORIES]
CALLBACK = '''from ansible.plugins.callback import CallbackBase
import json


class CallbackModule(CallbackBase):
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = "stdout"
    CALLBACK_NAME = "esp_contract"

    def __init__(self):
        super().__init__()
        self.events = []

    def record(self, result, status):
        self.events.append({"task": result._task.get_name(), "status": status,
                            "host": result._host.get_name(), "result": result._result})

    def v2_runner_on_ok(self, result):
        self.record(result, "ok")

    def v2_runner_on_failed(self, result, ignore_errors=False):
        self.record(result, "failed")

    def v2_runner_on_skipped(self, result):
        self.record(result, "skipped")

    def v2_runner_on_unreachable(self, result):
        self.record(result, "unreachable")

    def v2_playbook_on_stats(self, stats):
        print(json.dumps({"events": self.events,
                          "stats": {host: stats.summarize(host) for host in stats.processed}}))
'''


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"vfio_boot ESP mode contract: {message}")


def findmnt(fstype: str, options: str, target: str = "/boot") -> str:
    return json.dumps({"filesystems": [{"target": target, "fstype": fstype, "options": options}]},
                      indent=3)


def run_tool(stdin: str, wanted: str = "0644") -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(TOOL), "--wanted", wanted], input=stdin,
                          capture_output=True, text=True, check=False)


def decided(documents: list[str], wanted: str = "0644") -> str:
    result = run_tool(json.dumps(documents), wanted)
    require(result.returncode == 0, f"the tool refused a mount it must decide: {result.stderr.strip()}")
    return result.stdout.strip()


def refused(stdin: str, reason: str, wanted: str = "0644") -> None:
    result = run_tool(stdin, wanted)
    details = (f"{reason}: rc={result.returncode} stdout={result.stdout!r} "
               f"stderr={result.stderr!r}")
    require(result.returncode == 2, f"the tool did not refuse {details} with exit 2")
    require(result.stdout == "", f"the tool wrote to stdout while refusing {details}")
    prefix = "esp_file_mode: "
    require(result.stderr.startswith(prefix) and result.stderr[len(prefix):].strip(),
            f"the tool broke the refusal diagnostic protocol for {details}")
    require("Traceback (most recent call last):" not in result.stderr,
            f"the tool emitted a traceback while refusing {details}")


def check_tool() -> None:
    nitro = findmnt("vfat", NITRO_OPTIONS)
    require(decided([nitro, nitro]) == "0755",
            "the mode decided for the Nitro's ESP (fmask=0022) is not the 0755 its files read")
    require(decided([findmnt("vfat", "rw,fmask=0133,dmask=0022")]) == "0644",
            "fmask=0133 does not give 0644")
    require(decided([findmnt("vfat", "rw,fmask=0077,dmask=0077")]) == "0700",
            "fmask=0077 does not give 0700")
    require(decided([findmnt("vfat", "rw,fmask=0022,dmask=0022,showexec")]) == "0644",
            "showexec does not take the execute bits from a .conf file")
    for fstype in ("ext4", "btrfs", "xfs"):
        require(decided([findmnt(fstype, "rw,relatime")]) == "0644",
                f"{fstype} keeps modes but the role's 0644 was not kept")
    require(decided([findmnt("ext4", "rw")], wanted="0600") == "0600",
            "the wanted mode is not the one asked for on a filesystem that keeps modes")

    refused(json.dumps([findmnt("vfat", "rw,fmask=0000,dmask=0022")]),
            "fmask=0000, which lets everyone write a boot entry")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0002,dmask=0022")]), "fmask=0002 (others write)")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0020,dmask=0022")]), "fmask=0020 (group writes)")
    refused(json.dumps([findmnt("vfat", "rw,relatime,dmask=0022")]), "a vfat mount without fmask")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0022,fmask=0133,dmask=0022")]), "a duplicated fmask")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0x22,dmask=0022")]), "a fmask that is not octal")
    refused(json.dumps([findmnt("vfat", "rw,fmask=01022,dmask=0022")]), "a fmask beyond the permission bits")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0022,dmask=0000")]),
            "dmask=0000, which lets everyone create or replace a boot entry")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0022,dmask=0002")]), "dmask=0002 (others write)")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0022,dmask=0020")]), "dmask=0020 (group writes)")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0022")]), "a vfat mount without dmask")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0022,dmask=0022,dmask=0077")]), "a duplicated dmask")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0022,dmask=0x22")]), "a dmask that is not octal")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0022,dmask=01022")]), "a dmask beyond the permission bits")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0022,dmask=0022,uid=1000")]),
            "a vfat mount whose files belong to uid 1000, not root")
    refused(json.dumps([findmnt("vfat", "rw,fmask=0022,dmask=0022,gid=100")]),
            "a vfat mount whose files belong to gid 100, not root")
    for fstype in ("exfat", "ntfs3", "msdos", "nfs4", ""):
        refused(json.dumps([findmnt(fstype, "rw,fmask=0022")]), f"fstype {fstype!r}")
    refused(json.dumps([nitro, findmnt("vfat", NITRO_OPTIONS, target="/boot/loader")]),
            "two directories on different filesystems")
    refused(json.dumps([nitro, findmnt("vfat", "rw,fmask=0133,dmask=0022")]),
            "two documents with different options")
    refused(json.dumps([]), "no document")
    refused(json.dumps(nitro), "a document that is not in a list")
    refused("not json", "stdin that is not JSON")
    refused(json.dumps(["not json"]), "a document that is not JSON")
    refused(json.dumps([json.dumps({"filesystems": []})]), "a document without a filesystem")
    two = {"filesystems": [json.loads(nitro)["filesystems"][0]] * 2}
    refused(json.dumps([json.dumps(two)]), "a document with two filesystems")
    refused(json.dumps([findmnt("vfat", NITRO_OPTIONS, target="boot")]), "a relative target")
    for wanted in ("644", "0664", "0646", "0x1a4", "07777"):
        refused(json.dumps([findmnt("ext4", "rw")]), f"--wanted {wanted}", wanted=wanted)


def module_args(task: dict[str, Any]) -> dict[str, Any]:
    for key, value in task.items():
        if key.startswith("ansible.builtin.") and isinstance(value, dict):
            return value
    return {}


def source_yaml(path: Path) -> Any:
    """Refuse redirected inputs and duplicate keys before task selection."""
    current = ROOT
    for part in path.relative_to(ROOT).parts:
        current /= part
        require(not current.is_symlink(), f"redirected fixture source: {current}")
    require(path.is_file(), f"missing fixture source: {path}")

    class UniqueLoader(yaml.SafeLoader):
        def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
            self.flatten_mapping(node)
            pairs = self.construct_pairs(node, deep=deep)
            keys = [key for key, _ in pairs]
            require(len(keys) == len(set(keys)), f"duplicate YAML keys in {path}")
            return dict(pairs)

    return yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueLoader)


def decision_tasks() -> list[dict[str, Any]]:
    tasks = source_yaml(ROLE / "tasks/main.yml")
    require(isinstance(tasks, list) and all(isinstance(task, dict) for task in tasks),
            "vfio_boot tasks are not a list of task objects")
    selected = [task for task in tasks if task.get("name") in DECISION_NAMES]
    require([task.get("name") for task in selected] == list(DECISION_NAMES),
            "the four decision task names are missing, duplicated or out of production order")
    positions = [tasks.index(task) for task in selected]
    require(positions == list(range(positions[0], positions[0] + 4)),
            "the four decision tasks are no longer contiguous")
    modules = ("command", "command", "set_fact", "assert")
    # Only these two bounded command argv can execute. In particular, never
    # include the role, cryptsetup, boot writers, handlers or the brick stamp.
    task_keys = ({"loop", "register", "changed_when", "check_mode"},
                 {"register", "changed_when", "check_mode"}, set(), set())
    for task, module, extra_keys in zip(selected, modules, task_keys, strict=True):
        key = f"ansible.builtin.{module}"
        require(key in task and set(task) <= {"name", key} | extra_keys,
                f"unsafe decision task selection: {task!r}")
        require(isinstance(task[key], dict), f"invalid decision module arguments: {task!r}")
    read, decide, publish, shape = selected
    require(module_args(read) == {"argv": ["{{ vfio_boot_findmnt_bin }}", "-J", "-T", "{{ item }}",
                                           "-o", "TARGET,FSTYPE,OPTIONS"]},
            "unsafe findmnt command in the selected task")
    loop = read.get("loop")
    require(isinstance(loop, list) and 1 <= len(loop) <= 2
            and all(directory in DIRECTORIES for directory in loop),
            "findmnt loop is not restricted to the two boot directories")
    require(set(module_args(decide)) == {"argv", "stdin"}
            and module_args(decide)["argv"] == ["{{ vfio_boot_python_bin }}", "{{ vfio_boot_mode_tool }}",
                                                "--wanted", "{{ vfio_boot_file_mode }}"]
            and isinstance(module_args(decide)["stdin"], str),
            "unsafe mode tool command in the selected task")
    require(set(module_args(publish)) == {"vfio_boot_loader_file_mode"},
            "the selected publication sets facts other than the boot file mode")
    require(set(module_args(shape)) <= {"that", "fail_msg"}
            and isinstance(module_args(shape).get("that"), list),
            "the selected shape task is not a plain assertion")
    defaults = source_yaml(ROLE / "defaults/main.yml")
    require(defaults.get("vfio_boot_mode_tool")
            == "{{ (vfio_boot_repository_root, 'tools/esp_file_mode.py') | path_join }}",
            "the runtime fixture must execute this repository's mode tool")
    require(TOOL.is_file() and not TOOL.is_symlink() and not TOOL.parent.is_symlink(),
            "missing or redirected mode tool")
    return selected


def run_decision_play(tasks: list[dict[str, Any]], documents: list[str],
                      expected: str, check: bool, wanted: str | None) -> tuple[int, dict[str, Any], list[Any]]:
    executable = shutil.which("ansible-playbook")
    require(executable is not None, "ansible-playbook is required for the runtime fixture")
    with tempfile.TemporaryDirectory(prefix="esp-mode-contract-") as temporary:
        workspace = Path(temporary)
        callbacks = workspace / "callbacks"
        callbacks.mkdir()
        (callbacks / "esp_contract.py").write_text(CALLBACK, encoding="utf-8")
        trace = workspace / "findmnt.jsonl"
        fake = workspace / "findmnt"
        fake.write_text(f'''#!{sys.executable}
import json
import sys
from pathlib import Path

argv = sys.argv[1:]
with Path({str(trace)!r}).open("a", encoding="utf-8") as stream:
    stream.write(json.dumps(argv) + "\\n")
if argv not in {EXPECTED_CALLS!r}:
    sys.exit("unexpected findmnt argv")
documents = {dict(zip(DIRECTORIES, documents, strict=True))!r}
print(documents[argv[2]])
''', encoding="utf-8")
        fake.chmod(0o700)
        configuration = workspace / "ansible.cfg"
        configuration.write_text(f"[defaults]\nstdout_callback = esp_contract\n"
                                 f"callback_plugins = {callbacks}\nretry_files_enabled = False\n",
                                 encoding="utf-8")
        variables = {"vfio_boot_repository_root": str(ROOT), "vfio_boot_python_bin": sys.executable,
                     "vfio_boot_findmnt_bin": str(fake), "ansible_python_interpreter": sys.executable}
        if wanted is not None:
            variables["vfio_boot_file_mode"] = wanted
        overrides = workspace / "overrides.json"
        overrides.write_text(json.dumps(variables), encoding="utf-8")
        # vars_files outrank play vars. Check the effective dependency paths
        # under Ansible before either command can run, even if overrides break.
        guard = {"name": FIXTURE_GUARD_NAME, "ansible.builtin.assert": {"that": [
            f"{key} == {json.dumps(value)}" for key, value in variables.items()
        ] + [f"vfio_boot_mode_tool == {json.dumps(str(TOOL))}"]}}
        assertion = {"name": EXPECTED_MODE_NAME, "ansible.builtin.assert": {"that": [
            "vfio_boot_loader_file_mode is string", f"vfio_boot_loader_file_mode == '{expected}'"]}}
        play = [{"name": "Execute the ESP mode decision", "hosts": "localhost", "connection": "local",
                 "gather_facts": False, "become": False,
                 "vars_files": [str(ROLE / "defaults/main.yml")], "pre_tasks": [guard],
                 "tasks": [*tasks, assertion]}]
        play_path = workspace / "decision.yml"
        play_path.write_text(yaml.safe_dump(play, sort_keys=False), encoding="utf-8")
        # No inherited Ansible configuration, inventory, callbacks or user state.
        environment = {"PATH": os.environ.get("PATH", os.defpath), "HOME": temporary,
                       "TMPDIR": temporary, "ANSIBLE_HOME": str(workspace / "ansible"),
                       "ANSIBLE_CONFIG": str(configuration), "ANSIBLE_NOCOLOR": "1",
                       "ANSIBLE_LOCAL_TEMP": str(workspace / "local"),
                       "ANSIBLE_REMOTE_TEMP": str(workspace / "remote"), "PYTHONDONTWRITEBYTECODE": "1"}
        argv = [executable, "-i", "localhost,", "--connection", "local",
                "--extra-vars", f"@{overrides}", str(play_path)]
        if check:
            argv.append("--check")
        with subprocess.Popen(argv, cwd=workspace, env=environment, stdin=subprocess.DEVNULL,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                              start_new_session=True) as process:
            try:
                stdout, stderr = process.communicate(timeout=45)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                stdout, stderr = process.communicate()
                require(False, f"runtime ansible-playbook timed out: {stdout}\n{stderr}")
        try:
            report = json.loads(stdout)
        except json.JSONDecodeError:
            require(False, f"runtime ansible-playbook produced no JSON report: rc={process.returncode}\n"
                    f"{stdout}\n{stderr}")
        require(isinstance(report, dict), f"invalid runtime report: {report!r}")
        calls = [json.loads(line) for line in trace.read_text(encoding="utf-8").splitlines()] if trace.exists() else []
        return process.returncode, report, calls


def check_runtime() -> None:
    selected = decision_tasks()
    nitro = findmnt("vfat", NITRO_OPTIONS)
    cases = [
        ("vfat", [nitro, nitro], "0755", None, None),
        ("ext4-default", [findmnt("ext4", "rw,relatime")] * 2, "0644", None, None),
        ("ext4-custom", [findmnt("ext4", "rw")] * 2, "0600", "0600", None),
        ("unsafe-dmask", [findmnt("vfat", "rw,fmask=0022,dmask=0000")] * 2, "0755", None,
         "esp_file_mode: directories there would read 0777: a user other than root "
         "could create or replace a boot entry"),
        ("different-mounts", [nitro, findmnt("vfat", NITRO_OPTIONS, "/boot/loader")],
         "0755", None, "esp_file_mode: the directories are not on one filesystem with one set of options"),
        ("different-options", [nitro, findmnt("vfat", "rw,fmask=0133,dmask=0022")],
         "0755", None, "esp_file_mode: the directories are not on one filesystem with one set of options"),
    ]
    for check in (False, True):
        for name, documents, expected, wanted, refusal in cases:
            context = f"runtime {name} ({'--check' if check else 'normal'})"
            rc, report, calls = run_decision_play(selected, documents, expected, check, wanted)
            recorded = report.get("events", [])
            require(recorded and recorded[0].get("task") == FIXTURE_GUARD_NAME
                    and recorded[0].get("status") == "ok" and recorded[0].get("host") == "localhost",
                    f"{context}: isolated dependency guard failed before commands: {recorded!r}")
            events = recorded[1:]
            outcomes = [{"task": event.get("task"), "status": event.get("status"),
                         "failure": event.get("result") if event.get("status") != "ok" else None}
                        for event in events]
            expected_names = list(DECISION_NAMES[:2] if refusal else (*DECISION_NAMES, EXPECTED_MODE_NAME))
            require([event.get("task") for event in events] == expected_names,
                    f"{context}: unexpected executed tasks: {outcomes!r}")
            require(calls == EXPECTED_CALLS,
                    f"{context}: findmnt call trace {calls!r}, expected {EXPECTED_CALLS!r}")
            require(all(event.get("host") == "localhost" for event in events),
                    f"{context}: execution escaped localhost")
            expected_statuses = ["ok", "failed"] if refusal else ["ok"] * 5
            require([event.get("status") for event in events] == expected_statuses,
                    f"{context}: unexpected task results: {outcomes!r}")
            stats = report.get("stats", {})
            require(set(stats) == {"localhost"}, f"{context}: missing localhost recap: {stats!r}")
            summary = stats["localhost"]
            for key, value in {"changed": 0, "unreachable": 0, "skipped": 0, "rescued": 0,
                               "ignored": 0, "failures": int(refusal is not None),
                               "ok": 2 if refusal else 6}.items():
                require(summary.get(key) == value, f"{context}: recap {key} is not {value}: {summary!r}")
            decision = events[1]["result"]
            if refusal:
                require(rc == 2 and decision.get("rc") == 2 and decision.get("stdout") == ""
                        and decision.get("stderr", "").strip() == refusal,
                        f"{context}: expected deliberate refusal at {DECISION_NAMES[1]!r}, "
                        f"got process rc={rc}, result={decision!r}")
            else:
                require(rc == 0 and decision.get("rc") == 0,
                        f"{context}: ansible-playbook did not complete successfully: {decision!r}")
                fact = events[2]["result"].get("ansible_facts", {}).get("vfio_boot_loader_file_mode")
                require(isinstance(fact, str) and fact == expected,
                        f"{context}: published fact is {fact!r} ({type(fact).__name__}), expected string {expected!r}")
            print(f"{context}: {'deliberate rc=2 refusal' if refusal else 'string ' + expected}, "
                  "changed=0, two findmnt calls")


def check_role() -> None:
    tasks = yaml.safe_load((ROLE / "tasks/main.yml").read_text(encoding="utf-8"))
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text(encoding="utf-8"))
    require(defaults.get("vfio_boot_file_mode") == "0644",
            "the mode wanted where the filesystem keeps modes is not 0644")
    require(defaults.get("vfio_boot_findmnt_bin") == "/usr/bin/findmnt",
            "vfio_boot does not name findmnt by its absolute path")
    require(defaults.get("vfio_boot_python_bin") == "/usr/bin/python",
            "vfio_boot does not name python by its absolute path")
    require(defaults.get("vfio_boot_mode_tool")
            == "{{ (vfio_boot_repository_root, 'tools/esp_file_mode.py') | path_join }}"
            and defaults.get("vfio_boot_repository_root") == "{{ playbook_dir | dirname }}",
            "vfio_boot does not run this repository's tools/esp_file_mode.py")

    writers: list[tuple[int, str]] = []
    for index, task in enumerate(tasks):
        args = module_args(task)
        target = str(args.get("dest", args.get("path", "")))
        if target.startswith("/boot/") and "mode" in args:
            require(args["mode"] == MODE_FACT,
                    f"'{task['name']}' writes {target} with a fixed mode {args['mode']!r}, "
                    "not the one the ESP keeps")
            writers.append((index, target))
    require(len(writers) >= 2, "vfio_boot no longer writes the boot entries and loader.conf with the decided mode")
    directories = sorted({posixpath.dirname(target) for _, target in writers})

    names = [task["name"] for task in tasks]
    read = [i for i, task in enumerate(tasks)
            if module_args(task).get("argv", [None])[0] == "{{ vfio_boot_findmnt_bin }}"]
    require(len(read) == 1, "vfio_boot does not read the ESP's mount with findmnt exactly once")
    read_task = tasks[read[0]]
    require(module_args(read_task)["argv"] == ["{{ vfio_boot_findmnt_bin }}", "-J", "-T", "{{ item }}",
                                               "-o", "TARGET,FSTYPE,OPTIONS"],
            f"findmnt is not asked for one target's TARGET,FSTYPE,OPTIONS: {module_args(read_task)['argv']}")
    looped = sorted(read_task.get("loop", []))
    for directory in directories:
        require(directory in looped, f"vfio_boot does not inspect {directory}, where it writes")
    require(looped == directories, f"findmnt inspects {looped}, not exactly {directories}")

    decide = [i for i, task in enumerate(tasks)
              if module_args(task).get("argv", [None, None])[1:2] == ["{{ vfio_boot_mode_tool }}"]]
    require(len(decide) == 1, "vfio_boot does not run tools/esp_file_mode.py exactly once")
    decide_task = tasks[decide[0]]
    require(module_args(decide_task)["argv"] == ["{{ vfio_boot_python_bin }}", "{{ vfio_boot_mode_tool }}",
                                                 "--wanted", "{{ vfio_boot_file_mode }}"],
            f"the tool is not asked for the role's wanted mode: {module_args(decide_task)['argv']}")
    require(module_args(decide_task).get("stdin")
            == "{{ %s.results | map(attribute='stdout') | list | to_json }}" % read_task["register"],
            "the tool does not read every findmnt document the role collected")
    for task in (read_task, decide_task):
        require(task.get("check_mode") is False,
                f"'{task['name']}' only reads, but does not run in check mode, so --check --diff "
                "cannot compare the mode")
        require(task.get("changed_when") is False, f"'{task['name']}' only reads but may report a change")

    publish = [i for i, task in enumerate(tasks)
               if "vfio_boot_loader_file_mode" in task.get("ansible.builtin.set_fact", {})]
    require(len(publish) == 1 and tasks[publish[0]]["ansible.builtin.set_fact"]["vfio_boot_loader_file_mode"]
            == "{{ %s.stdout }}" % decide_task["register"],
            "vfio_boot_loader_file_mode is not the tool's answer")
    shape = [i for i, task in enumerate(tasks)
             if "ansible.builtin.assert" in task
             and module_args(task).get("that") == ["vfio_boot_loader_file_mode is string",
                                                    "vfio_boot_loader_file_mode is match('^0[0-7]{3}$')"]]
    require(len(shape) == 1, "vfio_boot does not refuse a decided mode that is not a 0NNN string")
    first_write = min(index for index, _ in writers)
    require(read[0] < decide[0] < publish[0] < shape[0] < first_write,
            "the mode is decided after '%s' writes under /boot" % names[first_write])


def main() -> int:
    check_runtime()
    check_tool()
    check_role()
    print("vfio_boot ESP mode contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
