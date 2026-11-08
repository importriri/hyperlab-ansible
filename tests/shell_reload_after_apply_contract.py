#!/usr/bin/env python3
"""Changed desktop code refreshes resident presentation, never a session."""
from __future__ import annotations

import ast
import configparser
import json
import os
from pathlib import Path
import re
import shlex
import socket
import subprocess
import sys
import tempfile
from types import ModuleType, SimpleNamespace
from typing import Any
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
    # The Hyprland component stays inactive and runs nothing, and its play
    # follows the common role. Its unit copy is part of the installed time
    # that the next shell check compares, so a unit change refreshes then.
    unit_copies = [task for task in hyprland if task.get("ansible.builtin.copy", {}).get("dest")
                   == "/etc/systemd/user/" + UNIT]
    require(len(unit_copies) == 1, "the shell unit needs one installed copy")
    require(Path(unit_copies[0]["ansible.builtin.copy"]["dest"]) == load_refresh().UNIT_PATH,
            "installed freshness does not compare the deployed unit")
    unit = configparser.ConfigParser(interpolation=None)
    unit.read(HYPRLAND / "files" / UNIT)
    require(unit["Service"]["Environment"] == "QS_DISABLE_FILE_WATCHER=1",
            "partial deployment can trigger a file-watcher reload")
    return [copies[0], helpers, unit_copies[0]], reconcilers


def load_refresh() -> Any:
    module = ModuleType("desktop_refresh")
    exec(compile(SCRIPT.read_text(), str(SCRIPT), "exec"), module.__dict__)
    return module


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


def refresh_contract(module: Any) -> None:
    env = {"XDG_RUNTIME_DIR": "/private/runtime", "DBUS_SESSION_BUS_ADDRESS": "unix:path=/private/runtime/bus"}
    state = {"LoadState": "loaded", "ActiveState": "active", "MainPID": "41",
             "ControlGroup": "/user.slice/shell.service", "NeedDaemonReload": "no"}
    for active in ("active", "inactive", "failed", "activating"):
        for installed in (90, 110):
            properties = dict(state, ActiveState=active)
            with patch.object(module, "shell_properties", return_value=properties), \
                    patch.object(module, "process_started_ns", return_value=100), \
                    patch.object(module, "installed_shell_ns", return_value=installed), \
                    patch.object(module, "require_idle_cgroup") as guard, \
                    patch.object(module.subprocess, "run") as run:
                if active == "activating":
                    refused(lambda: module.refresh_quickshell(env), "transitional service state accepted")
                    run.assert_not_called()
                    continue
                result = module.refresh_quickshell(env)
                stale = active == "active" and installed >= 100
                require(result["changed"] is stale, "shell age did not determine refresh")
                if stale:
                    guard.assert_called_once_with(properties)
                    require(run.call_args_list[0].args[0] ==
                            ["/usr/bin/systemctl", "--user", "daemon-reload"], "unit cache not reloaded")
                    require(run.call_args_list[1].args[0] ==
                            ["/usr/bin/systemctl", "--user", "try-restart", UNIT], "unsafe restart argv")
                    require(run.call_args_list[2].args[0] ==
                            ["/usr/bin/systemctl", "--user", "is-active", "--quiet", UNIT], "restart not checked")
                    for call in run.call_args_list:
                        require(call.kwargs["check"] is True and call.kwargs["env"] == env
                                and 0 < call.kwargs["timeout"] <= 30, "refresh failure/deadline lost")
                else:
                    guard.assert_not_called()
                    run.assert_not_called()
    with patch.object(module, "shell_properties", return_value=dict(state, LoadState="not-found")), \
            patch.object(module.subprocess, "run") as run:
        require(module.refresh_quickshell(env)["changed"] is False, "missing unit activated")
        run.assert_not_called()
    with patch.object(module, "shell_properties", return_value=dict(state, NeedDaemonReload="yes")), \
            patch.object(module, "process_started_ns", return_value=100), \
            patch.object(module, "installed_shell_ns", return_value=90), \
            patch.object(module, "require_idle_cgroup"), \
            patch.object(module.subprocess, "run") as run:
        require(module.refresh_quickshell(env)["changed"] is True, "stale unit cache ignored")
        require(run.call_count == 3, "unit cache refresh skipped restart verification")
    for failure in (RuntimeError("busy cgroup"), subprocess.TimeoutExpired("refresh", 30),
                    subprocess.CalledProcessError(1, ["restart"])):
        with patch.object(module, "shell_properties", return_value=state), \
                patch.object(module, "process_started_ns", return_value=100), \
                patch.object(module, "installed_shell_ns", return_value=110), \
                patch.object(module, "require_idle_cgroup", side_effect=failure), \
                patch.object(module.subprocess, "run") as run:
            refused(lambda: module.refresh_quickshell(env), "unsafe shell refresh accepted")
            run.assert_not_called()
    with patch.object(module, "shell_properties", return_value=state), \
            patch.object(module, "process_started_ns", return_value=100), \
            patch.object(module, "installed_shell_ns", return_value=110), \
            patch.object(module, "require_idle_cgroup"), \
            patch.object(module.subprocess, "run", side_effect=subprocess.CalledProcessError(1, ["restart"])):
        refused(lambda: module.refresh_quickshell(env), "shell restart failure ignored")

    for owners, installed in (([False], 110), ([True], 90), ([True, False], 110),
                               ([True, True, False], 110)):
        with patch.object(module, "control_center_connection", return_value=object()), \
                patch.object(module, "control_center_running", side_effect=owners), \
                patch.object(module, "control_center_pid", return_value=42), \
                patch.object(module, "process_started_ns", return_value=100), \
                patch.object(module, "regular_file_ns", return_value=installed), \
                patch.object(module.subprocess, "run") as run, \
                patch.object(module.time, "sleep"):
            result = module.refresh_control_center(env)
            stale = owners[0] and installed >= 100
            require(result["changed"] is stale, "GTK age did not determine retirement")
            if stale:
                run.assert_called_once_with(["/usr/bin/gapplication", "action", APP_ID, "quit"],
                                            check=True, timeout=15, env=env)
            else:
                run.assert_not_called()
    with patch.object(module, "control_center_connection", return_value=object()), \
            patch.object(module, "control_center_running", return_value=True), \
            patch.object(module, "control_center_pid", return_value=42), \
            patch.object(module, "process_started_ns", return_value=100), \
            patch.object(module, "regular_file_ns", return_value=110), \
            patch.object(module.subprocess, "run"), \
            patch.object(module.time, "monotonic", side_effect=[0, 11]):
        refused(lambda: module.refresh_control_center(env), "resident owner retained after quit")
    with patch.object(module, "control_center_connection", side_effect=RuntimeError("bus unavailable")):
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
    source = directory / "timestamps"
    source.mkdir()
    qml = source / "shell.qml"
    qml.write_text("one")
    unit = directory / UNIT
    unit.write_text("one")
    features = source / "features.json"
    features.write_text("{}")
    created = qml.lstat().st_ctime_ns
    # A replacement that keeps an older modification time is still new.
    os.utime(qml, ns=(1, 1))
    require(module.regular_file_ns(qml) >= created, "preserved modification time hides a replacement")
    with patch.object(module, "SHELL_ROOT", source), patch.object(module, "UNIT_PATH", unit):
        original = module.installed_shell_ns()
        os.utime(features, ns=(original + 10**9, original + 10**9))
        require(module.installed_shell_ns() == original, "live-watched features trigger shell restart")
        os.utime(unit, ns=(original + 2 * 10**9, original + 2 * 10**9))
        require(module.installed_shell_ns() > original, "service unit omitted from installed freshness")
        subtree = source / "new"
        subtree.mkdir()
        extra = subtree / "Extra.qml"
        extra.write_text("extra")
        os.utime(extra, ns=(original + 3 * 10**9, original + 3 * 10**9))
        require(module.installed_shell_ns() >= original + 3 * 10**9, "new QML subtree not compared")
        extra.unlink()
        extra.symlink_to(unit)
        refused(module.installed_shell_ns, "redirected shell source accepted")
        extra.unlink()
        unit.unlink()
        refused(module.installed_shell_ns, "missing installed unit accepted")
    proc = directory / "proc"
    pid = proc / "41"
    pid.mkdir(parents=True)
    # The executable name can contain spaces and closing parentheses.
    (pid / "stat").write_text("41 (shell ) worker) S " + "0 " * 18 + "120 0 0\n")
    with patch.object(module, "PROC_ROOT", proc), \
            patch.object(module.time, "time_ns", return_value=20_000_000_000), \
            patch.object(module.time, "clock_gettime_ns", return_value=10_000_000_000), \
            patch.object(module.os, "sysconf", return_value=100):
        require(module.process_started_ns(41) == 11_200_000_000, "process start ticks parsed incorrectly")
        (pid / "stat").write_text("malformed")
        refused(lambda: module.process_started_ns(41), "malformed process start accepted")
    cgroup_contract(module, directory)
    env = {"XDG_RUNTIME_DIR": "/private"}
    properties = {"LoadState": "loaded", "ActiveState": "active", "MainPID": "41",
                  "ControlGroup": "/user.slice/shell.service", "NeedDaemonReload": "no"}
    with patch.object(module.subprocess, "run", return_value=SimpleNamespace(
            stdout="\n".join(key + "=" + value for key, value in properties.items()))) as run:
        require(module.shell_properties(env) == properties, "systemd properties not parsed")
        call = run.call_args
        require(call.args[0][:3] == ["/usr/bin/systemctl", "--user", "show"]
                and call.args[0][-1] == UNIT and call.kwargs["check"]
                and call.kwargs["timeout"] == 10 and call.kwargs["env"] == env,
                "unbounded or incorrect service-state probe")
    for text in ("MainPID=41\nMainPID=42", "ActiveState=active", "not a property",
                 "\n".join(key + "=" + ("unknown" if key == "NeedDaemonReload" else value)
                           for key, value in properties.items())):
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
        # Permanent watchers, their helpers and slow polls are recreated by the new shell.
        members(41, 42, 44, child=(43,))
        module.require_idle_cgroup(properties)
        for busy in ((50,), (51,), (52,), (53,), (50, 54), (99,)):
            members(41, 42, child=busy)
            clock[0] = 0.0
            refused(lambda: module.require_idle_cgroup(properties), "shell cgroup child would be killed")
            require(clock[0] >= 5, "busy shell refused without waiting for short work to finish")
            with patch.object(module, "shell_properties", return_value=dict(
                    properties, LoadState="loaded", ActiveState="active", NeedDaemonReload="no")), \
                    patch.object(module, "process_started_ns", return_value=100), \
                    patch.object(module, "installed_shell_ns", return_value=110), \
                    patch.object(module.subprocess, "run") as run:
                clock[0] = 0.0
                refused(lambda: module.refresh_quickshell({}), "busy cgroup did not refuse refresh")
                run.assert_not_called()
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
    for item in (manager, helper):
        (source / item["src"]).write_text(item["src"] + " one")
    (source / UNIT).write_text("unit one")
    installed = directory / "installed"
    installed.mkdir()
    log, running = directory / "refreshes", directory / "running.json"
    fail_refresh = directory / "fail-refresh"
    running.write_text(json.dumps({"quickshell": 1, "control-center": 1}))
    probe = directory / "probe.py"
    # The production comparison and restart/quit decision execute unchanged.
    # Only session discovery, process start timestamps and external calls are fake.
    probe.write_text("import json, pathlib, runpy, sys, time\n"
                     "from unittest.mock import patch\n"
                     "from types import SimpleNamespace\n"
                     f"m = runpy.run_path({str(SCRIPT)!r})\n"
                     f"root = pathlib.Path({str(installed)!r})\n"
                     f"state_path = pathlib.Path({str(running)!r})\n"
                     "state = json.loads(state_path.read_text())\n"
                     "surface = sys.argv[1]\n"
                     "owner = [True]\n"
                     "def transport(argv, **kwargs):\n"
                     f"    if pathlib.Path({str(fail_refresh)!r}).exists():\n"
                     "        raise RuntimeError('injected refresh failure')\n"
                     "    if 'try-restart' in argv or 'quit' in argv:\n"
                     "        state[surface] = time.time_ns()\n"
                     "        state_path.write_text(json.dumps(state))\n"
                     "        owner[0] = False\n"
                     f"        with open({str(log)!r}, 'a') as stream: stream.write(surface + '\\n')\n"
                     "    return SimpleNamespace(returncode=0)\n"
                     "m.update(SHELL_ROOT=root / 'shell', UNIT_PATH=root / 'unit', "
                     f"CONTROL_CENTER_PATH=root / {manager['dest']!r})\n"
                     "m.update(process_started_ns=lambda pid: state[surface],\n"
                     "         require_idle_cgroup=lambda properties: None,\n"
                     "         control_center_connection=lambda env: object(),\n"
                     "         control_center_running=lambda connection: owner[0],\n"
                     "         control_center_pid=lambda connection: 42,\n"
                     "         shell_properties=lambda env: dict(LoadState='loaded', ActiveState='active',\n"
                     "             MainPID='41', ControlGroup='/shell', NeedDaemonReload='no'))\n"
                     "for name, value in m.items():\n"
                     "    if callable(value) and hasattr(value, '__globals__'): value.__globals__.update(m)\n"
                     "with patch('subprocess.run', side_effect=transport):\n"
                     "    result = m['refresh_quickshell' if surface == 'quickshell' "
                     "else 'refresh_control_center']({})\n"
                     "print(json.dumps(result))\n")
    copies = [
        {"name": tasks[0]["name"],
         "ansible.builtin.copy": {"src": str(shell) + "/", "dest": str(installed / "shell") + "/", "mode": "0644"}},
        {"name": tasks[1]["name"], "loop": [manager, helper],
         "ansible.builtin.copy": {"src": str(source) + "/{{ item.src }}",
                                  "dest": str(installed) + "/{{ item.dest }}", "mode": "0755"}},
        {"name": tasks[2]["name"],
         "ansible.builtin.copy": {"src": str(source / UNIT), "dest": str(installed / "unit"), "mode": "0644"}},
    ]
    fixture_reconcilers = [
        {"name": task["name"], "when": task["when"], "register": task["register"],
         "ansible.builtin.command": {"argv": [sys.executable, str(probe), surface]},
         "changed_when": task["changed_when"]}
        for task, surface in zip(reconcilers, ("quickshell", "control-center"), strict=True)
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
                                           "tasks": copies[:2] + failure + fixture_reconcilers
                                           + copies[2:]}]))
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
    # The unit is copied after the check, as the Hyprland play follows the
    # common role; the next apply restarts the shell under the new unit.
    (source / UNIT).write_text("unit two")
    apply([])
    apply(["quickshell"])
    apply([], changed=False)
    # Already stale residents are detected even when both copies are unchanged.
    running.write_text(json.dumps({"quickshell": 1, "control-center": 1}))
    apply(["quickshell", "control-center"])
    apply([], changed=False)


def main() -> int:
    tasks, handlers = deployment_contract()
    module = load_refresh()
    with tempfile.TemporaryDirectory(prefix="shell-refresh-") as temporary:
        directory = Path(temporary)
        runtime_contract(module, directory)
        refresh_contract(module)
        state_contract(module, directory)
        gtk_transport_contract(module)
        ansible_contract(tasks, handlers, directory)
    print("Shell reload after apply contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
