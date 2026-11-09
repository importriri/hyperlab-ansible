#!/usr/bin/env python3
"""Changed desktop code refreshes resident presentation, never a session."""
from __future__ import annotations

import ast
from contextlib import contextmanager
import configparser
import json
import os
from pathlib import Path
import re
import shlex
import signal
import socket
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from typing import Any, Iterator
from unittest.mock import Mock, patch

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMMON = ROOT / "roles/host_desktop_common"
SWAY = ROOT / "roles/host_desktop_sway"
HYPRLAND = ROOT / "roles/host_desktop_hyprland"
SCRIPT = COMMON / "handlers/refresh.py"
SHELL_NOTICE = "Refresh the running HyperLab shell"
GTK_NOTICE = "Retire the resident HyperLab Control Center"
UNIT = "hyperlab-quickshell.service"
APP_ID = "io.github.importriri.HyperlabControlCenter"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read_tasks(role: Path) -> list[dict[str, Any]]:
    return yaml.safe_load((role / "tasks/main.yml").read_text())


def deployment_contract() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    common, sway, hyprland = (read_tasks(role) for role in (COMMON, SWAY, HYPRLAND))
    reconcilers = []
    for role, tasks, notice, surface in (
            (COMMON, common, SHELL_NOTICE, "quickshell"),
            (SWAY, sway, GTK_NOTICE, "control-center")):
        matches = [task for task in tasks if task["name"] == notice]
        require(len(matches) == 1, "each deployment needs an unconditional resident-state reconciliation")
        task = matches[0]
        require(task.get("become") is True and task.get("become_user") == "{{ admin_user }}",
                "refresh must run as the configured desktop user")
        require(task.get("when") == "not ansible_check_mode",
                "reconciliation must retry unchanged copies and skip check mode")
        result = task.get("register")
        require(isinstance(result, str)
                and task.get("changed_when") == f"({result}.stdout | from_json).changed",
                "only an actual refresh may report changed")
        argv = shlex.split(task["ansible.builtin.script"]["cmd"].replace("{{ role_path }}", str(role)))
        require(len(argv) == 2 and Path(argv[0]).resolve() == SCRIPT and argv[1] == surface,
                "reconciliation must use the reviewed refresh script and surface")
        require(task["ansible.builtin.script"].get("executable") == "/usr/bin/python",
                "refresh interpreter changed")
        require(not any(key in task for key in ("ignore_errors", "failed_when", "check_mode")),
                "refresh errors or check mode suppressed")
        reconcilers.append(task)
    shell = []
    for task in common:
        for module in ("copy", "template", "file"):
            action = task.get("ansible.builtin." + module, {})
            dest = action.get("dest", action.get("path", ""))
            if not dest.startswith("{{ host_desktop_common_shell_stage.config_root }}"):
                continue
            # ShellState.qml's FileView watches this one runtime-data file live.
            if dest == "{{ host_desktop_common_shell_stage.config_root }}/features.json":
                continue
            require(common.index(task) < common.index(reconcilers[0]),
                    "shell config write has no subsequent resident-state reconciliation")
            require(set(task.get("tags", [])) <= set(reconcilers[0].get("tags", [])),
                    "a tagged apply can install shell code without reconciliation")
            shell.append(task)
    copies = [task for task in shell if task.get("ansible.builtin.copy", {}).get("src")
              == "quickshell/hyperlab/"]
    require(len(copies) == 1, "shared shell copy must be unique")
    helpers = next(task for task in sway if task["name"] == "Deploy the cockpit helpers")
    require(sum(item["src"] == "privatestack-hyperlab-domains.py"
                for item in helpers["loop"]) == 1, "recovery code needs one helper-loop copy")
    require(sway.index(helpers) < sway.index(reconcilers[1]), "GTK reconciliation precedes installation")
    require(set(helpers.get("tags", [])) <= set(reconcilers[1].get("tags", [])),
            "a tagged apply can install recovery code without reconciliation")
    # The Hyprland component stages only; v1 reconciles again after it.
    unit_copies = [task for task in hyprland if task.get("ansible.builtin.copy", {}).get("dest")
                   == "/etc/systemd/user/" + UNIT]
    require(len(unit_copies) == 1, "the shell unit needs one installed copy")
    require(Path(unit_copies[0]["ansible.builtin.copy"]["dest"]) == load_refresh().UNIT_PATH,
            "installed freshness does not compare the deployed unit")
    unit = configparser.ConfigParser(interpolation=None)
    unit.read(HYPRLAND / "files" / UNIT)
    require(unit["Service"]["Environment"] == "QS_DISABLE_FILE_WATCHER=1",
            "partial deployment can trigger a file-watcher reload")
    plays = yaml.safe_load((ROOT / "playbooks/v1-host.yml").read_text())
    final = [play for play in plays if "tasks" in play]
    require(len(final) == 1 and len(final[0]["tasks"]) == 1,
            "final reconciliation play must contain only the reviewed task")
    imports = [play.get("import_playbook") for play in plays]
    require(imports.index("host-desktop-hyprland.yml") < plays.index(final[0])
            < imports.index("host-sleep-guard.yml"), "unit deployment is not followed by reconciliation")
    task = final[0]["tasks"][0]
    expected = dict(reconcilers[0], register="host_desktop_common_final_resident_refresh",
                    changed_when="(host_desktop_common_final_resident_refresh.stdout | from_json).changed")
    expected["ansible.builtin.script"] = {
        "cmd": "{{ playbook_dir }}/../roles/host_desktop_common/handlers/refresh.py quickshell",
        "executable": "/usr/bin/python"}
    require(task == expected, "final shell reconciliation differs from the reviewed deployment task")
    require(unit["Service"]["Restart"] == "on-failure", "pinned replacement needs the existing restart policy")
    module = load_refresh()
    observer_paths = {command[0] for command in module.RESIDENT_OBSERVERS}
    deployed = set()
    observer_copies = []
    pipeline = [*common, *sway, *hyprland, task]
    for role_tasks in (common, sway, hyprland):
        for copy in role_tasks:
            action = copy.get("ansible.builtin.copy", {})
            for item in copy.get("loop", [{}]):
                if not isinstance(item, dict):
                    continue
                dest = action.get("dest", "").replace("{{ item.dest }}", item.get("dest", ""))
                if dest not in observer_paths and dest != str(module.CHECKOUT_POINTER):
                    continue
                boundary = reconcilers[0] if role_tasks is common else task
                require(pipeline.index(copy) < pipeline.index(boundary),
                        "observer copy has no subsequent resident-state reconciliation: " + dest)
                require(set(copy.get("tags", [])) <= set(boundary.get("tags", [])),
                        "tagged observer copy has no reconciliation: " + dest)
                if dest in observer_paths:
                    deployed.add(dest)
                    if copy is not helpers:
                        observer_copies.append(copy)
    require(deployed == observer_paths, "observer executable lacks a deployment copy")
    with tempfile.TemporaryDirectory(prefix="observer-generation-") as temporary:
        observer_generation_contract(module, Path(temporary))
    return [copies[0], helpers, unit_copies[0], *observer_copies], [*reconcilers, task]


def load_refresh() -> Any:
    module = ModuleType("desktop_refresh")
    exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), module.__dict__)
    return module


@contextmanager
def observer_sources(module: Any, directory: Path) -> Iterator[dict[str, Path]]:
    """Provide real installed observer files without using host paths."""
    directory.mkdir()
    paths = {argv[0]: directory / Path(argv[0]).name for argv in module.RESIDENT_OBSERVERS}
    for path in paths.values():
        path.write_text("observer one")
    checkout = directory / "checkout"
    (checkout / "tools").mkdir(parents=True)
    (checkout / "tools/surface_provenance.py").write_text("resolver one")
    pointer = directory / "checkout-pointer"
    pointer.write_text(str(checkout) + "\n")
    observers = frozenset((str(paths[argv[0]]), *argv[1:]) for argv in module.RESIDENT_OBSERVERS)
    with patch.object(module, "RESIDENT_OBSERVERS", observers), \
            patch.object(module, "COMPOSITOR_ADAPTER", str(paths[module.COMPOSITOR_ADAPTER])), \
            patch.object(module, "STATUS_BRIDGE", str(paths[module.STATUS_BRIDGE])), \
            patch.object(module, "CHECKOUT_POINTER", pointer):
        yield paths


def observer_generation_contract(module: Any, directory: Path) -> None:
    shell = directory / "shell"
    shell.mkdir()
    (shell / "shell.qml").write_text("shell")
    unit = directory / "unit"
    unit.write_text("unit")
    with observer_sources(module, directory / "observers") as paths, \
            patch.object(module, "SHELL_ROOT", shell), patch.object(module, "UNIT_PATH", unit):
        for original, path in sorted(paths.items()):
            generation = module.source_generation("quickshell")
            path.write_text("observer two")
            require(module.source_generation("quickshell") != generation,
                    "observer executable omitted from installed generation: " + original)
            path.unlink()
            refused(lambda: module.source_generation("quickshell"), "missing observer accepted: " + original)
            path.symlink_to(unit)
            refused(lambda: module.source_generation("quickshell"), "redirected observer accepted: " + original)
            path.unlink()
            path.write_text("observer one")
        pointer = module.CHECKOUT_POINTER
        checkout = Path(pointer.read_text().strip())
        resolver = checkout / "tools/surface_provenance.py"
        generation = module.source_generation("quickshell")
        resolver.write_text("resolver two")
        require(module.source_generation("quickshell") != generation,
                "checkout resolver omitted from installed generation")
        for invalid in (str(checkout) + "\n" + str(checkout) + "\n", "relative\n", ""):
            pointer.write_text(invalid)
            refused(lambda: module.source_generation("quickshell"), "invalid generation checkout pointer accepted")
        pointer.write_text(str(checkout) + "\n")
        resolver.unlink()
        refused(lambda: module.source_generation("quickshell"), "missing generation resolver accepted")
        resolver.symlink_to(unit)
        refused(lambda: module.source_generation("quickshell"), "redirected generation resolver accepted")
        resolver.unlink()
        resolver.write_text("resolver one")
        pointer.unlink()
        refused(lambda: module.source_generation("quickshell"), "missing generation checkout pointer accepted")
        pointer.symlink_to(unit)
        refused(lambda: module.source_generation("quickshell"), "redirected generation checkout pointer accepted")


def symlinked_checkout_contract(module: Any, directory: Path) -> None:
    """Hash the resolved checkout but recognize the observer's literal argv."""
    directory.mkdir()
    shell = directory / "shell"
    shell.mkdir()
    (shell / "shell.qml").write_text("shell")
    unit = directory / "unit"
    unit.write_text("unit")
    with observer_sources(module, directory / "observers"), \
            patch.object(module, "SHELL_ROOT", shell), patch.object(module, "UNIT_PATH", unit):
        pointer = module.CHECKOUT_POINTER
        checkout = Path(pointer.read_text().strip())
        resolver = checkout / "tools/surface_provenance.py"
        leaf = directory / "checkout-link"
        leaf.symlink_to(checkout, target_is_directory=True)
        ancestor = directory / "ancestor-link"
        ancestor.symlink_to(checkout.parent, target_is_directory=True)
        for literal in (leaf, ancestor / checkout.name):
            pointer.write_text(str(literal) + "\n")
            generation = module.source_generation("quickshell")
            resolver.write_text("resolver changed")
            require(module.source_generation("quickshell") != generation,
                    "symlinked checkout resolver omitted from installed generation")
            argv = ("/usr/bin/python3", "-I", "-B", str(literal / "tools/surface_provenance.py"),
                    "--repo", str(literal), "--proc-root", "/proc", "stream", "--registry",
                    f"/run/user/{os.getuid()}/hyperlab/surface-provenance.json")
            require(module.resident_observer(argv), "literal symlinked checkout observer rejected")
            for index in range(len(argv)):
                changed = tuple("unreviewed" if offset == index else value for offset, value in enumerate(argv))
                require(not module.resident_observer(changed), "arbitrary symlinked checkout observer accepted")
            canonical = list(argv)
            canonical[3], canonical[5] = str(resolver), str(checkout)
            require(not module.resident_observer(tuple(canonical)), "canonical checkout observer accepted as literal")
            missing = checkout.rename(directory / "unavailable-checkout")
            refused(lambda: module.source_generation("quickshell"), "missing symlinked checkout accepted")
            refused(lambda argv=argv: module.resident_observer(argv), "missing observer checkout accepted")
            missing.rename(checkout)
            resolver.unlink()
            refused(lambda: module.source_generation("quickshell"), "missing symlinked checkout resolver accepted")
            resolver.symlink_to(unit)
            refused(lambda: module.source_generation("quickshell"), "redirected symlinked checkout resolver accepted")
            refused(lambda argv=argv: module.resident_observer(argv), "redirected symlinked checkout observer accepted")
            resolver.unlink()
            resolver.write_text("resolver one")
            tools = checkout / "tools"
            real_tools = tools.rename(checkout / "real-tools")
            tools.symlink_to(real_tools, target_is_directory=True)
            refused(lambda: module.source_generation("quickshell"), "redirected checkout tools directory accepted")
            refused(lambda argv=argv: module.resident_observer(argv), "redirected observer tools directory accepted")
            tools.unlink()
            real_tools.rename(tools)


def runtime_contract(module: Any, directory: Path) -> None:
    runtime = directory / "runtime"
    uid = os.getuid()
    with patch.object(module, "runtime_path", return_value=runtime):
        require(module.session_environment() is None, "absent session was contacted")
        runtime.mkdir(mode=0o700)
        require(module.session_environment() is None, "absent user bus was contacted")
        with socket.socket(socket.AF_UNIX) as bus:
            bus.bind(str(runtime / "bus"))
            env = module.session_environment()
            require(env["XDG_RUNTIME_DIR"] == str(runtime)
                    and env["DBUS_SESSION_BUS_ADDRESS"] == "unix:path=" + str(runtime / "bus"),
                    "session address must come from the validated runtime")
            runtime.chmod(0o755)
            refused(lambda: module.session_environment(), "public runtime accepted")
            runtime.chmod(0o700)
            (runtime / "bus").rename(runtime / "real-bus")
            (runtime / "bus").symlink_to(runtime / "real-bus")
            refused(lambda: module.session_environment(), "redirected bus accepted")
            (runtime / "bus").unlink()
            (runtime / "bus").write_text("not a socket")
            refused(lambda: module.session_environment(), "regular file bus accepted")
        (runtime / "bus").unlink()
        original = runtime.rename(directory / "real-runtime")
        runtime.symlink_to(original, target_is_directory=True)
        refused(lambda: module.session_environment(), "redirected runtime accepted")
    with patch.object(module.os, "getuid", return_value=0):
        refused(module.runtime_path, "root session accepted")
    with patch.object(module.os, "getuid", return_value=4242), \
            patch.dict(module.os.environ, {"XDG_RUNTIME_DIR": "/untrusted"}):
        require(module.runtime_path() == Path("/run/user/4242"), "inherited runtime trusted")
    with patch.object(module.os, "getuid", return_value=uid + 1), \
            patch.object(module, "runtime_path", return_value=original):
        refused(module.session_environment, "foreign runtime accepted")


def refused(action: Any, message: str) -> None:
    try:
        action()
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return
    raise AssertionError(message)


def properties(**changes: str) -> dict[str, str]:
    return dict({"LoadState": "loaded", "ActiveState": "active", "MainPID": "41",
                 "ControlGroup": "/user.slice/shell.service", "NeedDaemonReload": "no",
                 "Restart": "on-failure", "RestartPreventExitStatus": "", "SuccessExitStatus": ""}, **changes)


def refresh_contract(module: Any) -> None:
    env = {"XDG_RUNTIME_DIR": "/private/runtime", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/private/runtime/bus"}
    for active in ("active", "inactive", "failed", "activating"):
        for current in (False, True):
            with patch.object(module, "checkpoint") as store, \
                    patch.object(module, "shell_properties", return_value=properties(ActiveState=active)), \
                    patch.object(module, "source_generation", return_value="a" * 64), \
                    patch.object(module, "replace_shell", return_value=42) as replace:
                saved = store.return_value.__enter__.return_value
                saved.current.return_value = current
                if active == "activating":
                    refused(lambda: module.refresh_quickshell(env), "transitional service state accepted")
                    replace.assert_not_called()
                    continue
                result = module.refresh_quickshell(env)
                stale = active == "active" and not current
                require(result["changed"] is stale, "shell generation did not determine refresh")
                if stale:
                    replace.assert_called_once_with(env, properties())
                    require(saved.record.call_args.args[0] == "a" * 64
                            and saved.record.call_args.args[2] == 42, "replacement identity not recorded")
                else:
                    replace.assert_not_called()
                    saved.record.assert_not_called()
    with patch.object(module, "checkpoint"), \
            patch.object(module, "shell_properties", return_value=properties(LoadState="not-found")), \
            patch.object(module, "replace_shell") as replace:
        require(module.refresh_quickshell(env)["changed"] is False, "missing unit activated")
        replace.assert_not_called()
    with patch.object(module, "checkpoint") as store, \
            patch.object(module, "shell_properties", return_value=properties(NeedDaemonReload="yes")), \
            patch.object(module, "source_generation", return_value="a" * 64), \
            patch.object(module, "replace_shell", return_value=42) as replace:
        store.return_value.__enter__.return_value.current.return_value = True
        require(module.refresh_quickshell(env)["changed"] is True, "stale unit cache ignored")
        replace.assert_called_once()
    for failure in (RuntimeError("busy cgroup"), subprocess.TimeoutExpired("refresh", 30),
                    subprocess.CalledProcessError(1, ["reload"])):
        with patch.object(module, "checkpoint") as store, \
                patch.object(module, "shell_properties", return_value=properties()), \
                patch.object(module, "source_generation", return_value="a" * 64), \
                patch.object(module, "replace_shell", side_effect=failure):
            saved = store.return_value.__enter__.return_value
            saved.current.return_value = False
            refused(lambda: module.refresh_quickshell(env), "unsafe shell refresh accepted")
            saved.record.assert_not_called()
    with patch.object(module, "checkpoint") as store, \
            patch.object(module, "shell_properties", return_value=properties()), \
            patch.object(module, "source_generation", side_effect=["a" * 64, "b" * 64]), \
            patch.object(module, "replace_shell", return_value=42):
        saved = store.return_value.__enter__.return_value
        saved.current.return_value = False
        refused(lambda: module.refresh_quickshell(env), "concurrent source deployment accepted")
        saved.record.assert_not_called()
    for owners, current in (([False], False), ([True], True), ([True, False], False),
                            ([True, True, False], False)):
        with patch.object(module, "checkpoint") as store, \
                patch.object(module, "source_generation", return_value="a" * 64), \
                patch.object(module, "control_center_connection", return_value=object()), \
                patch.object(module, "control_center_running", side_effect=owners), \
                patch.object(module, "control_center_pid", return_value=42), \
                patch.object(module.subprocess, "run") as run, patch.object(module.time, "sleep"):
            saved = store.return_value.__enter__.return_value
            saved.current.return_value = current
            result = module.refresh_control_center(env)
            stale = owners[0] and not current
            require(result["changed"] is stale, "GTK generation did not determine retirement")
            if stale:
                run.assert_called_once_with(["/usr/bin/gapplication", "action", APP_ID, "quit"],
                                            check=True, timeout=15, env=env)
                saved.record.assert_called_once()
            else:
                run.assert_not_called()
    with patch.object(module, "checkpoint") as store, \
            patch.object(module, "source_generation", return_value="a" * 64), \
            patch.object(module, "control_center_connection", return_value=object()), \
            patch.object(module, "control_center_running", return_value=True), \
            patch.object(module, "control_center_pid", return_value=42), \
            patch.object(module.subprocess, "run"), \
            patch.object(module.time, "monotonic", side_effect=[0, 11]):
        saved = store.return_value.__enter__.return_value
        saved.current.return_value = False
        refused(lambda: module.refresh_control_center(env), "resident owner retained after quit")
        saved.record.assert_not_called()
    with patch.object(module, "checkpoint"), \
            patch.object(module, "control_center_connection", side_effect=RuntimeError("bus unavailable")):
        refused(lambda: module.refresh_control_center(env), "GTK bus failure ignored")
    for surface, function in (("quickshell", "refresh_quickshell"),
                              ("control-center", "refresh_control_center")):
        for session in (None, env):
            with patch.object(sys, "argv", ["refresh.py", surface]), \
                    patch.object(module, "session_environment", return_value=session), \
                    patch.object(module, "refresh_quickshell", return_value={"changed": True}) as shell, \
                    patch.object(module, "refresh_control_center", return_value={"changed": True}) as gtk, \
                    patch("builtins.print") as report:
                require(module.main() == 0, "refresh entrypoint failed")
                expected = shell if function == "refresh_quickshell" else gtk
                other = gtk if expected is shell else shell
                other.assert_not_called()
                require(json.loads(report.call_args.args[0])["changed"] is (session is not None),
                        "refresh entrypoint lost structured change status")
                if session is None:
                    expected.assert_not_called()
                else:
                    expected.assert_called_once_with(env)


def state_contract(module: Any, directory: Path) -> None:
    source = directory / "generations"
    source.mkdir()
    qml = source / "shell.qml"
    qml.write_text("one")
    unit = directory / UNIT
    unit.write_text("one")
    features = source / "features.json"
    features.write_text("{}")
    with observer_sources(module, directory / "state-observers"), \
            patch.object(module, "SHELL_ROOT", source), patch.object(module, "UNIT_PATH", unit):
        original = module.source_generation("quickshell")
        features.write_text('{"changed": true}')
        require(module.source_generation("quickshell") == original, "live-watched features trigger shell restart")
        unit.write_text("two")
        require(module.source_generation("quickshell") != original, "service unit omitted from installed generation")
        original = module.source_generation("quickshell")
        qml.write_text("two")
        os.utime(qml, ns=(1, 1))
        require(module.source_generation("quickshell") != original, "preserved file times hide new code")
        original = module.source_generation("quickshell")
        subtree = source / "new"
        subtree.mkdir()
        extra = subtree / "Extra.qml"
        extra.write_text("extra")
        require(module.source_generation("quickshell") != original, "new QML subtree not compared")
        extra.unlink()
        require(module.source_generation("quickshell") == original, "removed source was not compared")
        extra.symlink_to(unit)
        refused(lambda: module.source_generation("quickshell"), "redirected shell source accepted")
        extra.unlink()
        unit.unlink()
        refused(lambda: module.source_generation("quickshell"), "missing installed unit accepted")
    proc = directory / "proc"
    pid = proc / "41"
    pid.mkdir(parents=True)
    (pid / "stat").write_text("41 (shell ) worker) S " + "0 " * 18 + "120 0 0\n")
    with patch.object(module, "PROC_ROOT", proc), patch.object(module, "boot_ticks", return_value=1000):
        require(module.process_ticks(41) == 120, "process start ticks parsed incorrectly")
        (pid / "stat").write_text("malformed")
        refused(lambda: module.process_ticks(41), "malformed process identity accepted")
    cgroup_contract(module, directory)
    env = {"XDG_RUNTIME_DIR": "/private"}
    state = properties()
    with patch.object(module.subprocess, "run", return_value=SimpleNamespace(
            stdout="\n".join(key + "=" + value for key, value in state.items()))) as run:
        require(module.shell_properties(env) == state, "systemd properties not parsed")
        call = run.call_args
        require(call.args[0][:3] == ["/usr/bin/systemctl", "--user", "show"]
                and call.args[0][-1] == UNIT and call.kwargs["check"]
                and call.kwargs["timeout"] == 10 and call.kwargs["env"] == env,
                "unbounded or incorrect service-state probe")
    for text in ("MainPID=41\nMainPID=42", "ActiveState=active", "not a property",
                 "\n".join(key + "=" + ("unknown" if key == "NeedDaemonReload" else value)
                           for key, value in state.items())):
        with patch.object(module.subprocess, "run", return_value=SimpleNamespace(stdout=text)):
            refused(lambda: module.shell_properties(env), "missing or duplicate properties accepted")


def shell_observer_commands() -> set[tuple[str, ...]]:
    """Resolve every Process command in ShellState.qml to its literal argv."""
    qml = (COMMON / "files/quickshell/hyperlab/ShellState.qml").read_text()
    paths = dict(re.findall(r'readonly property string (\w+):\s*"([^"]+)"', qml))
    commands = set()
    for body in re.findall(r"\bcommand:\s*\[([^\]]*)\]", qml):
        argv = []
        for token in (part.strip() for part in body.split(",")):
            if token.startswith("state."):
                argv.append(paths[token.removeprefix("state.")])
            else:
                require(token.startswith('"') and token.endswith('"'), "unresolved shell command " + token)
                argv.append(json.loads(token))
        commands.add(tuple(argv))
    require(len(commands) >= 4, "shell observer commands not found")
    return commands


def cgroup_contract(module: Any, directory: Path) -> None:
    observers = shell_observer_commands()
    require(observers == module.RESIDENT_OBSERVERS,
            "refresh may end exactly the read-only observers ShellState.qml starts")
    others = set()
    for name in ("MachineActions.qml", "ShellActions.qml"):
        qml = (COMMON / "files/quickshell/hyperlab" / name).read_text()
        others.update(re.findall(r'"(/usr/[^"]+)"', qml))
    require(not others & {command[0] for command in observers},
            "an operation bridge is treated as a disposable observer")
    proc = directory / "cgroup-proc"
    cgroups = directory / "cgroups"
    group = cgroups / "user.slice/shell.service"
    group.mkdir(parents=True)
    trust = ("bash", "/usr/local/bin/privatestack-hyperlab", "watch", "trust")
    telemetry = ("/usr/bin/env", "python3", "/usr/local/bin/privatestack-telemetry", "snapshot")

    def process(pid: int, parent: int, argv: tuple[str, ...]) -> None:
        path = proc / str(pid)
        path.mkdir(parents=True, exist_ok=True)
        (path / "stat").write_text(f"{pid} (worker) S {parent} " + "0 " * 20 + "\n")
        (path / "cmdline").write_bytes(b"".join(os.fsencode(arg) + b"\0" for arg in argv))

    def members(*pids: int, child: tuple[int, ...] = ()) -> None:
        (group / "cgroup.procs").write_text("".join(f"{pid}\n" for pid in pids))
        if child:
            (group / "child").mkdir(exist_ok=True)
            (group / "child/cgroup.procs").write_text("".join(f"{pid}\n" for pid in child))
        elif (group / "child").exists():
            (group / "child/cgroup.procs").write_text("")

    properties = {"MainPID": "41", "ControlGroup": "/user.slice/shell.service"}
    process(41, 1, ("/usr/bin/qs", "-c", "hyperlab"))
    process(42, 41, trust)
    process(43, 42, ("hyprctl", "events"))
    process(44, 41, telemetry)
    process(50, 41, ("/usr/bin/gio", "launch", "foot.desktop"))
    process(51, 41, ("bash", "/usr/local/bin/privatestack-hyperlab", "power", "off"))
    process(52, 1, trust)
    process(53, 41, ("bash", "-c", " ".join(trust)))
    process(54, 50, ("foot",))
    clock = [0.0]

    def advance(seconds: float) -> None:
        clock[0] += seconds

    with patch.object(module, "CGROUP_ROOT", cgroups), patch.object(module, "PROC_ROOT", proc), \
            patch.object(module.time, "monotonic", side_effect=lambda: clock[0]), \
            patch.object(module.time, "sleep", side_effect=advance):
        members(41)
        module.require_idle_cgroup(properties)
        # Instantiate every original command and its supported interpreter shapes.
        for command in observers:
            for interpreter in module.INTERPRETERS:
                process(45, 41, interpreter + command)
                members(41, 45)
                module.require_idle_cgroup(properties)
        # The post-exec resolver must be a direct shell child, too.
        checkout = directory / "checkout"
        pointer = directory / "checkout-pointer"
        resolver = ("/usr/bin/python3", "-I", "-B", str(checkout / "tools/surface_provenance.py"),
                    "--repo", str(checkout), "--proc-root", "/proc", "stream", "--registry",
                    f"/run/user/{os.getuid()}/hyperlab/surface-provenance.json")
        with patch.object(module, "CHECKOUT_POINTER", pointer):
            process(46, 41, resolver)
            members(41, 46)
            module.require_idle_cgroup(properties)
            process(46, 1, resolver)
            require(module.busy_members(properties) == [46], "foreign resolver parent accepted")
        # Permanent watchers, their helpers and slow polls are recreated by the new shell.
        members(41, 42, 44, child=(43,))
        module.require_idle_cgroup(properties)
        for busy in ((50,), (51,), (52,), (53,), (50, 54), (99,)):
            members(41, 42, child=busy)
            clock[0] = 0.0
            refused(lambda: module.require_idle_cgroup(properties), "shell cgroup child would be killed")
            require(clock[0] >= 5, "busy shell refused without waiting for short work to finish")
        # A short operation that ends while the refresh waits does not block it.
        samples = iter(((41, 51), (41, 51), (41,)))
        with patch.object(module, "control_group_members", side_effect=lambda _: set(next(samples))):
            clock[0] = 0.0
            module.require_idle_cgroup(properties)
        members(42)
        refused(lambda: module.require_idle_cgroup(properties), "shell outside its control group accepted")
        (proc / "51").chmod(0o000)
        members(41, child=(51,))
        clock[0] = 0.0
        refused(lambda: module.require_idle_cgroup(properties), "unreadable shell child accepted")
        (proc / "51").chmod(0o755)
        (group / "cgroup.procs").unlink()
        refused(lambda: module.require_idle_cgroup(properties), "missing cgroup membership accepted")
        for invalid in ("", "/", "/../escape"):
            refused(lambda invalid=invalid: module.require_idle_cgroup(dict(properties, ControlGroup=invalid)),
                    "invalid cgroup path accepted")


def gtk_transport_contract(module: Any) -> None:
    """Check the real query shape and the existing application's quit action."""
    cancellable = Mock()
    gio = SimpleNamespace(
        Cancellable=SimpleNamespace(new=Mock(return_value=cancellable)),
        DBusConnection=SimpleNamespace(new_for_address_sync=Mock(return_value="connection")),
        DBusConnectionFlags=SimpleNamespace(AUTHENTICATION_CLIENT=1, MESSAGE_BUS_CONNECTION=2),
        DBusCallFlags=SimpleNamespace(NO_AUTO_START=1))
    glib = SimpleNamespace(Variant=lambda kind, values: (kind, values),
                           VariantType=SimpleNamespace(new=lambda kind: kind))
    with patch.dict(sys.modules, {"gi.repository": SimpleNamespace(Gio=gio, GLib=glib)}), \
            patch("threading.Timer") as timer:
        env = {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/private/bus"}
        require(module.control_center_connection(env) == "connection", "user bus not selected")
        timer.assert_called_once_with(5, cancellable.cancel)
        timer.return_value.start.assert_called_once_with()
        timer.return_value.cancel.assert_called_once_with()
        gio.DBusConnection.new_for_address_sync.assert_called_once_with(env["DBUS_SESSION_BUS_ADDRESS"],
                                                                       3, None, cancellable)
        gio.DBusConnection.new_for_address_sync.side_effect = RuntimeError("authentication failed")
        refused(lambda: module.control_center_connection(env), "connection failure ignored")
        require(timer.return_value.cancel.call_count == 2, "connection failure leaked its deadline")
        connection = Mock()
        connection.call_sync.return_value.unpack.return_value = (True,)
        require(module.control_center_running(connection) is True, "owner query result lost")
        connection.call_sync.assert_called_once_with(
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "NameHasOwner", ("(s)", (APP_ID,)), "(b)", 1, 5000, None)
        connection.reset_mock()
        connection.call_sync.side_effect = [
            SimpleNamespace(unpack=lambda: (":1.42",)), SimpleNamespace(unpack=lambda: (42,))]
        require(module.control_center_pid(connection) == 42, "GTK owner PID lost")
        require(connection.call_sync.call_args_list[0].args == (
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "GetNameOwner", ("(s)", (APP_ID,)), "(s)", 1, 5000, None), "GTK unique owner not queried")
        require(connection.call_sync.call_args_list[1].args == (
            "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
            "GetConnectionUnixProcessID", ("(s)", (":1.42",)), "(u)", 1, 5000, None),
            "GTK start time did not use the unique bus owner's PID")
    tree = ast.parse((SWAY / "files/privatestack-hyperlab-domains.py").read_text())
    identifier = next(node.value for node in tree.body if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == "APP_ID"
                              for target in node.targets))
    require(ast.literal_eval(identifier) == APP_ID, "GTK application identity drift")
    application = next(node for node in tree.body if isinstance(node, ast.ClassDef)
                       and node.name == "HyperlabApplication")
    startup = next(node for node in application.body if isinstance(node, ast.FunctionDef)
                   and node.name == "do_startup")
    action, owner = Mock(), Mock()
    namespace = {"Gtk": SimpleNamespace(Application=SimpleNamespace(do_startup=Mock())),
                 "Gio": SimpleNamespace(SimpleAction=SimpleNamespace(new=Mock(return_value=action)))}
    exec(compile(ast.Module(body=[startup], type_ignores=[]), "<GTK startup>", "exec"), namespace)
    namespace["do_startup"](owner)
    namespace["Gio"].SimpleAction.new.assert_called_once_with("quit", None)
    owner.add_action.assert_called_once_with(action)
    signal, callback = action.connect.call_args.args
    require(signal == "activate", "GTK quit action disconnected")
    callback()
    owner.quit.assert_called_once_with()


def ansible_contract(tasks: list[dict[str, Any]], reconcilers: list[dict[str, Any]], directory: Path) -> None:
    """Run real copy scheduling and real freshness decisions with inert session transports."""
    source = directory / "source"
    source.mkdir()
    shell = source / "shell"
    shell.mkdir()
    (shell / "shell.qml").write_text("entry one")
    (shell / "IsolationGlyph.qml").write_text("symbol one")
    manager = next(item for item in tasks[1]["loop"] if item["src"] == "privatestack-hyperlab-domains.py")
    helper = next(item for item in tasks[1]["loop"] if item["src"] != manager["src"])
    status = next(item for item in tasks[1]["loop"]
                  if item["dest"] == Path(load_refresh().STATUS_BRIDGE).name)
    for item in (manager, helper, status):
        (source / item["src"]).write_text(item["src"] + " one")
    (source / UNIT).write_text("unit one")
    for task in tasks[3:]:
        (source / task["ansible.builtin.copy"]["src"]).write_text("observer one")
    installed = directory / "installed"
    installed.mkdir()
    checkout = installed / "checkout"
    (checkout / "tools").mkdir(parents=True)
    (checkout / "tools/surface_provenance.py").write_text("resolver one")
    (installed / "checkout-pointer").write_text(str(checkout) + "\n")
    log, running = directory / "refreshes", directory / "running.json"
    fail_refresh = directory / "fail-refresh"
    running.write_text(json.dumps({"quickshell": 1, "control-center": 1}))
    probe = directory / "probe.py"
    # The production comparison and restart/quit decision execute unchanged.
    # Only session discovery, process start timestamps and external calls are fake.
    probe.write_text("import json, pathlib, runpy, sys\n"
                     "from unittest.mock import patch\n"
                     f"m = runpy.run_path({str(SCRIPT)!r})\n"
                     f"root = pathlib.Path({str(installed)!r})\n"
                     f"state_path = pathlib.Path({str(running)!r})\n"
                     "state = json.loads(state_path.read_text())\n"
                     "surface = sys.argv[1]\n"
                     "owner = [True]\n"
                     "def refreshed():\n"
                     f"    if pathlib.Path({str(fail_refresh)!r}).exists():\n"
                     "        raise RuntimeError('injected refresh failure')\n"
                     "    state[surface] = m['boot_ticks']() + 1\n"
                     "    state_path.write_text(json.dumps(state))\n"
                     "    owner[0] = False\n"
                     f"    with open({str(log)!r}, 'a') as stream: stream.write(surface + '\\n')\n"
                     "    return 42\n"
                     "m.update(SHELL_ROOT=root / 'shell', UNIT_PATH=root / 'unit', "
                     f"CONTROL_CENTER_PATH=root / {manager['dest']!r})\n"
                     "m.update(RESIDENT_OBSERVERS=frozenset((str(root / pathlib.Path(argv[0]).name), *argv[1:])\n"
                     "         for argv in m['RESIDENT_OBSERVERS']),\n"
                     "         COMPOSITOR_ADAPTER=str(root / pathlib.Path(m['COMPOSITOR_ADAPTER']).name),\n"
                     "         STATUS_BRIDGE=str(root / pathlib.Path(m['STATUS_BRIDGE']).name),\n"
                     "         CHECKOUT_POINTER=root / 'checkout-pointer')\n"
                     "m.update(process_ticks=lambda pid: state[surface],\n"
                     "         replace_shell=lambda env, properties: refreshed(),\n"
                     "         control_center_connection=lambda env: object(),\n"
                     "         control_center_running=lambda connection: owner[0],\n"
                     "         control_center_pid=lambda connection: 42,\n"
                     "         shell_properties=lambda env: dict(LoadState='loaded', ActiveState='active',\n"
                     "             MainPID='42', ControlGroup='/shell', NeedDaemonReload='no'))\n"
                     "for name, value in m.items():\n"
                     "    if callable(value) and hasattr(value, '__globals__'): value.__globals__.update(m)\n"
                     "with patch('subprocess.run', side_effect=lambda *args, **kwargs: refreshed()):\n"
                     "    result = m['refresh_quickshell' if surface == 'quickshell' "
                     "else 'refresh_control_center']({'XDG_RUNTIME_DIR': str(root)})\n"
                     "print(json.dumps(result))\n")
    copies = [
        {"name": tasks[0]["name"],
         "ansible.builtin.copy": {"src": str(shell) + "/", "dest": str(installed / "shell") + "/", "mode": "0644"}},
        {"name": tasks[1]["name"], "loop": [manager, helper, status],
         "ansible.builtin.copy": {"src": str(source) + "/{{ item.src }}",
                                  "dest": str(installed) + "/{{ item.dest }}", "mode": "0755"}},
        {"name": tasks[2]["name"],
         "ansible.builtin.copy": {"src": str(source / UNIT), "dest": str(installed / "unit"), "mode": "0644"}},
    ]
    observers = [
        {"name": task["name"], "ansible.builtin.copy": {
            "src": str(source / task["ansible.builtin.copy"]["src"]),
            "dest": str(installed / Path(task["ansible.builtin.copy"]["dest"]).name), "mode": "0755"}}
        for task in tasks[3:]
    ]
    fixture_reconcilers = [
        {"name": task["name"], "when": task["when"], "register": task["register"],
         "ansible.builtin.command": {"argv": [sys.executable, str(probe), surface]},
         "changed_when": task["changed_when"]}
        for task, surface in zip(reconcilers, ("quickshell", "control-center", "quickshell"), strict=True)
    ]
    playbook = directory / "contract.yml"
    env = dict(os.environ, ANSIBLE_LOCAL_TEMP=str(directory / "local"),
               ANSIBLE_REMOTE_TEMP=str(directory / "remote"), ANSIBLE_NOCOLOR="1")

    def apply(expected: list[str], changed: bool = True, check: bool = False, fail_later: bool = False,
              success: bool = True) -> None:
        log.write_text("")
        failure = [{"name": "Injected later failure", "ansible.builtin.fail": {"msg": "injected"}}] if fail_later else []
        playbook.write_text(yaml.safe_dump([{"name": "Isolated desktop refresh", "hosts": "localhost",
                                           "gather_facts": False, "become": False,
                                           "tasks": copies[:2] + observers + failure + fixture_reconcilers[:2]
                                           + copies[2:] + fixture_reconcilers[2:]}]))
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook),
                                 *(["--check"] if check else [])], env=env, capture_output=True,
                                text=True, check=False, timeout=60)
        require((result.returncode == 0) is success,
                "isolated Ansible fixture unexpected result: " + result.stdout + result.stderr)
        require(sorted(log.read_text().splitlines()) == sorted(expected),
                "unexpected refresh execution: " + result.stdout + result.stderr)
        if not changed:
            require("changed=0" in result.stdout, "second apply was not idempotent")

    # Fresh install has no unit until the later play: stage the old unit first.
    (installed / "unit").write_text("unit one")
    apply(["quickshell", "control-center"])
    apply([], changed=False)
    adapter = next(task["ansible.builtin.copy"]["src"] for task in tasks[3:]
                   if task["ansible.builtin.copy"]["dest"] == load_refresh().COMPOSITOR_ADAPTER)
    (source / adapter).write_text("adapter two")
    apply(["quickshell"])
    apply([], changed=False)
    (source / helper["src"]).write_text("helper two")
    apply([])
    (shell / "IsolationGlyph.qml").write_text("symbol two")
    (shell / "shell.qml").write_text("entry two")
    apply([], fail_later=True, success=False)
    apply(["quickshell"])
    apply([], changed=False)
    (source / manager["src"]).write_text("manager two")
    apply([], check=True)
    apply([], fail_later=True, success=False)
    apply(["control-center"])
    (shell / "shell.qml").write_text("entry three")
    fail_refresh.touch()
    apply([], success=False)
    fail_refresh.unlink()
    apply(["quickshell"])
    # The final check follows unit deployment; the immediate next apply is inert.
    (source / UNIT).write_text("unit two")
    apply(["quickshell"])
    apply([], changed=False)
    # Already stale residents are detected even when both copies are unchanged.
    running.write_text(json.dumps({"quickshell": 1, "control-center": 1}))
    apply(["quickshell", "control-center"])
    apply([], changed=False)


def clock_step_contract(module: Any, directory: Path) -> None:
    for surface in ("quickshell", "control-center"):
        for step in (-3600, 3600):
            root = directory / f"clock-{surface}-{step}"
            root.mkdir(mode=0o700)
            shell = root / "shell"
            shell.mkdir()
            code = shell / "shell.qml"
            code.write_text("old code")
            unit = root / "unit"
            unit.write_text("unit")
            env = {"XDG_RUNTIME_DIR": str(root)}
            boot, owner, pid, realtime = [500], [True], [41], [0]
            ticks = {41: 150, 42: 501}
            function = module.refresh_quickshell if surface == "quickshell" else module.refresh_control_center

            def refreshed(*args: Any, boot: list[int] = boot, owner: list[bool] = owner,
                          pid: list[int] = pid, **kwargs: Any) -> int:
                boot[0] = 502
                owner[0] = False
                pid[0] = 42
                return 42

            with observer_sources(module, root / "observers"), \
                    patch.object(module, "SHELL_ROOT", shell), patch.object(module, "UNIT_PATH", unit), \
                    patch.object(module, "CONTROL_CENTER_PATH", code), \
                    patch.object(module, "boot_ticks", side_effect=lambda boot=boot: boot[0]), \
                    patch.object(module, "process_ticks", side_effect=lambda value, ticks=ticks: ticks[value]), \
                    patch.object(module, "shell_properties", side_effect=lambda _, pid=pid: properties(MainPID=str(pid[0]))), \
                    patch.object(module, "control_center_connection", return_value=object()), \
                    patch.object(module, "control_center_pid", side_effect=lambda _, pid=pid: pid[0]), \
                    patch.object(module, "control_center_running", side_effect=lambda _, owner=owner: owner[0]), \
                    patch.object(module.time, "time_ns", side_effect=lambda realtime=realtime: realtime[0]):
                with module.checkpoint(env, surface) as saved:
                    saved.record(module.source_generation(surface), 100, 41)
                checkpoint_path = root / ("hyperlab-resident-" + surface + ".json")
                before = checkpoint_path.read_bytes()
                code.write_text("new code")
                realtime[0] += step * 1_000_000_000
                # Installation is unchanged on retry, and realtime has stepped.
                with patch.object(module, "replace_shell", side_effect=RuntimeError("refresh failed")), \
                        patch.object(module.subprocess, "run", side_effect=RuntimeError("quit failed")):
                    refused(lambda function=function, env=env: function(env), "clock step hid a stale resident")
                require(checkpoint_path.read_bytes() == before, "failed refresh advanced generation")
                with patch.object(module, "replace_shell", side_effect=refreshed), \
                        patch.object(module.subprocess, "run", side_effect=refreshed):
                    require(function(env)["changed"] is True, "clock-step retry lost installed update")
                owner[0] = True  # A later normal open loads the installed GTK code.
                with patch.object(module, "replace_shell") as replace, patch.object(module.subprocess, "run") as run:
                    require(function(env)["changed"] is False, "clock-step second pass refreshed again")
                    replace.assert_not_called()
                    run.assert_not_called()


def checkpoint_contract(module: Any, directory: Path) -> None:
    runtime = directory / "checkpoint-runtime"
    runtime.mkdir(mode=0o700)
    env = {"XDG_RUNTIME_DIR": str(runtime)}
    ticks = [50]
    for surface in ("quickshell", "control-center"):
        path = runtime / ("hyperlab-resident-" + surface + ".json")
        with patch.object(module, "boot_ticks", return_value=200), \
                patch.object(module, "process_ticks", side_effect=lambda _: ticks[0]):
            with module.checkpoint(env, surface) as saved:
                require(not saved.current("a" * 64, 41), "unknown resident assumed current")
                saved.record("a" * 64, 100, 41)
                ticks[0] = 60
                require(not saved.current("a" * 64, 41), "reused PID accepted as recorded resident")
                ticks[0] = 50
            for step in (-3_600_000_000_000, 3_600_000_000_000):
                with patch.object(module.time, "time_ns", return_value=step):
                    with module.checkpoint(env, surface) as saved:
                        require(saved.current("a" * 64, 41), "clock step invalidated known resident")
                        require(not saved.current("b" * 64, 41), "clock step hides changed source")
                    # Unchanged retries of the installed new generation stay stale.
                    with module.checkpoint(env, surface) as saved:
                        require(not saved.current("b" * 64, 41), "unchanged retry forgot stale generation")
            with module.checkpoint(env, surface) as saved:
                saved.record("b" * 64, 100)
                require(not saved.current("b" * 64, 41), "older resident crossed checkpoint boundary")
                ticks[0] = 110
                require(saved.current("b" * 64, 42), "new owner did not inherit installed generation")
                saved.state["boot_id"] = "00000000-0000-0000-0000-000000000000"
                require(not saved.current("b" * 64, 42), "different boot reused checkpoint")
            ticks[0] = 50
            original = path.read_bytes()
            for invalid in (original.replace(b'"boundary": 100', b'"boundary": 100, "boundary": 100'),
                            b'{"boot_id":"x","boot_id":"y"}', b'{"unexpected":true}',
                            b'null', b'{', original.replace(b'"boundary": 100', b'"boundary": 999999')):
                path.write_bytes(invalid)
                refused(lambda surface=surface: open_checkpoint(module, env, surface), "invalid checkpoint accepted")
            path.write_bytes(original + b" " * 9000)
            refused(lambda surface=surface: open_checkpoint(module, env, surface), "oversized checkpoint accepted")
            path.write_bytes(original)
            path.chmod(0o644)
            refused(lambda surface=surface: open_checkpoint(module, env, surface), "public checkpoint accepted")
            path.chmod(0o600)
            real = path.rename(path.with_suffix(".real"))
            path.symlink_to(real)
            refused(lambda surface=surface: open_checkpoint(module, env, surface), "redirected checkpoint accepted")
            path.unlink()
            os.link(real, path)
            refused(lambda surface=surface: open_checkpoint(module, env, surface), "hardlinked checkpoint accepted")
            path.unlink()
            real.rename(path)
            with module.checkpoint(env, surface):
                refused(lambda surface=surface: open_checkpoint(module, env, surface), "concurrent reconciliation accepted")


def open_checkpoint(module: Any, env: dict[str, str], surface: str) -> None:
    with module.checkpoint(env, surface):
        pass


def replacement_contract(module: Any, directory: Path) -> None:
    env = {"XDG_RUNTIME_DIR": "/private"}
    events = []
    paused = Mock()
    paused.terminate.side_effect = lambda: events.append("kill")

    @contextmanager
    def pause(*args: Any) -> Any:
        events.append("stop")
        try:
            yield paused
        finally:
            events.append("leave")

    def reload(argv: list[str], **kwargs: Any) -> None:
        require(argv == ["/usr/bin/systemctl", "--user", "daemon-reload"], "unsafe refresh command")
        require(kwargs == {"check": True, "timeout": 30, "env": env}, "refresh failure/deadline lost")
        events.append("reload")

    def wait_idle(state: Any) -> None:
        require(events == ["reload"], "idle waiting must precede the shell pause")
        events.append("idle")

    def inspect(state: Any) -> list[int]:
        require(events == ["reload", "idle", "stop"], "final inspection did not prevent launches")
        events.append("inspect")
        return []

    with patch.object(module, "shell_properties", side_effect=[properties(), properties(MainPID="42")]), \
            patch.object(module, "process_ticks", return_value=50), \
            patch.object(module, "paused_shell", side_effect=pause), \
            patch.object(module, "require_idle_cgroup", side_effect=wait_idle), \
            patch.object(module, "busy_members", side_effect=inspect), \
            patch.object(module.subprocess, "run", side_effect=reload):
        require(module.replace_shell(env, properties()) == 42, "new shell identity not verified")
        require(events == ["reload", "idle", "stop", "inspect", "kill", "leave"], "unsafe refresh sequence")
    # The review's reproduction: daemon-reload introduces a busy child.
    with patch.object(module, "shell_properties", return_value=properties()), \
            patch.object(module, "process_ticks", return_value=50), \
            patch.object(module, "paused_shell", side_effect=AssertionError("busy shell reached pause")) as pause_mock, \
            patch.object(module, "require_idle_cgroup", side_effect=RuntimeError("late busy child")), \
            patch.object(module.subprocess, "run"):
        paused.reset_mock()
        refused(lambda: module.replace_shell(env, properties()), "child created during reload was killed")
        paused.terminate.assert_not_called()
        pause_mock.assert_not_called()
    for state in (properties(MainPID="99"), properties(Restart="no"),
                  properties(RestartPreventExitStatus="9"), properties(SuccessExitStatus="9"),
                  properties(NeedDaemonReload="yes"),
                  properties(ActiveState="inactive")):
        with patch.object(module, "shell_properties", return_value=state), \
                patch.object(module, "paused_shell", side_effect=AssertionError("unsafe policy reached pause")) as pause_mock, \
                patch.object(module, "process_ticks", return_value=50), patch.object(module.subprocess, "run"):
            refused(lambda: module.replace_shell(env, properties()), "unsafe effective unit policy accepted")
            pause_mock.assert_not_called()
    with patch.object(module, "shell_properties", return_value=properties()), \
            patch.object(module, "process_ticks", return_value=50), \
            patch.object(module, "paused_shell", side_effect=pause), \
            patch.object(module, "require_idle_cgroup"), \
            patch.object(module, "busy_members", return_value=[]), patch.object(module.subprocess, "run"), \
            patch.object(module.time, "monotonic", side_effect=[0, 31]):
        refused(lambda: module.replace_shell(env, properties()), "unchanged resident identity accepted")
    for started, states in ((51, [["S"], ["T"]]), (50, [["T"]])):
        with patch.object(module.os, "pidfd_open", return_value=123), \
                patch.object(module.os, "close"), \
                patch.object(module, "process_ticks", return_value=started), \
                patch.object(module, "thread_states", side_effect=states), \
                patch.object(module.signal, "pidfd_send_signal") as send:
            def enter_pause() -> None:
                with module.paused_shell(41, 50):
                    pass
            refused(enter_pause, "changed identity or already stopped shell accepted")
            send.assert_not_called()
    # No sleep or monotonic deadline is permitted while the pinned shell is stopped.
    # A busy child first seen after SIGSTOP causes an immediate, single-sample refusal.
    for outcome in ("idle", "late-busy", "not-all-stopped"):
        signals = []
        stopped = [False]

        def send_signal(descriptor: int, sent: int, signals: list[tuple[int, int]] = signals,
                        stopped: list[bool] = stopped) -> None:
            signals.append((descriptor, sent))
            stopped[0] = sent == signal.SIGSTOP

        def no_paused_wait(*args: Any, stopped: list[bool] = stopped) -> float:
            require(not stopped[0], "sleep or monotonic wait while the shell is paused")
            return 0.0

        samples = []

        def members(state: Any, samples: list[bool] = samples, stopped: list[bool] = stopped,
                    outcome: str = outcome) -> list[int]:
            samples.append(stopped[0])
            return [99] if stopped[0] and outcome == "late-busy" else []

        states = [["S", "S"], ["T", "S"] if outcome == "not-all-stopped" else ["T", "T"]]
        with patch.object(module.os, "pidfd_open", return_value=123) as pin, \
                patch.object(module.os, "close") as close, \
                patch.object(module, "process_ticks", return_value=50), \
                patch.object(module, "thread_states", side_effect=states) as threads, \
                patch.object(module, "shell_properties", side_effect=[properties(), properties(MainPID="42")]), \
                patch.object(module, "busy_members", side_effect=members), \
                patch.object(module.subprocess, "run", side_effect=reload), \
                patch.object(module.time, "monotonic", side_effect=no_paused_wait), \
                patch.object(module.time, "sleep", side_effect=no_paused_wait) as sleep, \
                patch.object(module.signal, "pidfd_send_signal", side_effect=send_signal):
            if outcome == "idle":
                require(module.replace_shell(env, properties()) == 42, "idle shell did not refresh")
            else:
                refused(lambda: module.replace_shell(env, properties()), "late child or running thread was killed")
            require(threads.call_count == 2, "stopped threads must be checked once without polling")
            require(samples == ([False] if outcome == "not-all-stopped" else [False, True]),
                    "refresh needs one live and one paused cgroup inspection")
            sleep.assert_not_called()
            pin.assert_called_once_with(41)
            close.assert_called_once_with(123)
            require(signals == [(123, signal.SIGSTOP),
                                (123, signal.SIGKILL if outcome == "idle" else signal.SIGCONT)],
                    "paused shell resumed before termination or not resumed on refusal")
    # A real inert launcher is asked to fork AFTER the final inspection.
    # SIGSTOP prevents that request executing before the pinned SIGKILL.
    marker = directory / "late-child-ran"
    program = ("import pathlib, subprocess, sys\nprint('ready', flush=True)\n"
               "input()\nsubprocess.run([sys.executable, '-c', "
               "'import pathlib, sys; pathlib.Path(sys.argv[1]).touch()', sys.argv[1]], check=True)\n")
    with subprocess.Popen([sys.executable, "-c", program, str(marker)], stdin=subprocess.PIPE,
                          stdout=subprocess.PIPE, text=True) as launcher:
        require(launcher.stdout.readline().strip() == "ready", "inert launcher did not start")
        try:
            started = module.process_ticks(launcher.pid)
            with module.paused_shell(launcher.pid, started) as process:
                require(all(state == "T" for state in module.thread_states(launcher.pid)), "launcher not stopped")
                launcher.stdin.write("launch\n")
                launcher.stdin.flush()
                process.terminate()
            launcher.wait(timeout=5)
            require(not marker.exists(), "non-observer appeared after the final inspection")
        finally:
            if launcher.poll() is None:
                launcher.kill()
                launcher.wait(timeout=5)
    # Refusal resumes the shell and leaves an existing unrelated process alive.
    with subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as child, \
            subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"]) as shell:
        try:
            def members(state: Any) -> list[int]:
                return [child.pid] if "T" in module.thread_states(shell.pid) else []

            with patch.object(module, "busy_members", side_effect=members), \
                    patch.object(module, "shell_properties", return_value=properties(MainPID=str(shell.pid))), \
                    patch.object(module.subprocess, "run"):
                refused(lambda: module.replace_shell(env, properties(MainPID=str(shell.pid))),
                        "existing non-observer was killed")
            require(child.poll() is None and "T" not in module.thread_states(shell.pid),
                    "busy refusal killed a child or left shell stopped")
        finally:
            child.terminate()
            shell.terminate()
            child.wait(timeout=5)
            shell.wait(timeout=5)


def review_regressions(module: Any, directory: Path) -> None:
    checkout = directory / "checkout"
    (checkout / "tools").mkdir(parents=True)
    (checkout / "tools/surface_provenance.py").write_text("resolver")
    pointer = directory / "checkout-pointer"
    pointer.write_text(str(checkout) + "\n")
    argv = ("/usr/bin/python3", "-I", "-B", str(checkout / "tools/surface_provenance.py"),
            "--repo", str(checkout), "--proc-root", "/proc", "stream", "--registry",
            f"/run/user/{os.getuid()}/hyperlab/surface-provenance.json")
    with patch.object(module, "CHECKOUT_POINTER", pointer):
        require(module.resident_observer(argv), "actual post-exec provenance resolver rejected")
        for index in range(len(argv)):
            changed = tuple("unreviewed" if offset == index else value for offset, value in enumerate(argv))
            require(not module.resident_observer(changed), "arbitrary resolver argv accepted")
        pointer.write_text(str(checkout) + "\n" + str(checkout) + "\n")
        refused(lambda: module.resident_observer(argv), "duplicated checkout pointer accepted")
        pointer.write_text(str(checkout) + "\n")
        resolver = checkout / "tools/surface_provenance.py"
        resolver.rename(resolver.with_suffix(".real"))
        resolver.symlink_to(resolver.with_suffix(".real"))
        refused(lambda: module.resident_observer(argv), "redirected resolver accepted")
        resolver.unlink()
        resolver.with_suffix(".real").rename(resolver)
    plays = yaml.safe_load((ROOT / "playbooks/v1-host.yml").read_text())
    require(any("tasks" in play and any(task.get("name") == SHELL_NOTICE
                for task in play["tasks"]) for play in plays),
            "unit deployment needs a final reconciliation in the same apply")


def main() -> int:
    tasks, handlers = deployment_contract()
    module = load_refresh()
    with tempfile.TemporaryDirectory(prefix="shell-refresh-") as temporary:
        directory = Path(temporary)
        review_regressions(module, directory)
        symlinked_checkout_contract(module, directory / "symlinked-checkouts")
        runtime_contract(module, directory)
        refresh_contract(module)
        state_contract(module, directory)
        checkpoint_contract(module, directory)
        clock_step_contract(module, directory)
        replacement_contract(module, directory)
        gtk_transport_contract(module)
        ansible_contract(tasks, handlers, directory)
    print("Shell reload after apply contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
