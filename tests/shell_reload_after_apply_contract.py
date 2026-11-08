#!/usr/bin/env python3
"""Changed desktop code refreshes resident presentation, never a session."""
from __future__ import annotations

import ast
import configparser
import os
from pathlib import Path
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
    common, sway = read_tasks(COMMON), read_tasks(SWAY)
    shell = [task for task in common if task.get("ansible.builtin.copy", {}).get("src")
             == "quickshell/hyperlab/"]
    require(len(shell) == 1, "shared shell copy must be unique")
    require(shell[0].get("notify") == SHELL_NOTICE, "shell copy has no deferred refresh notification")
    helpers = next(task for task in sway if task["name"] == "Deploy the cockpit helpers")
    require(sum(item["src"] == "privatestack-hyperlab-domains.py"
                for item in helpers["loop"]) == 1, "recovery code needs one helper-loop copy")
    require(not any(task.get("ansible.builtin.copy", {}).get("src")
                    == "privatestack-hyperlab-domains.py" for task in sway), "recovery code copied twice")
    require(helpers.get("notify") == GTK_NOTICE, "recovery copy has no retirement notification")
    require(isinstance(helpers.get("register"), str), "helper-copy results must gate GTK retirement")
    unit = configparser.ConfigParser(interpolation=None)
    unit.read(ROOT / "roles/host_desktop_hyprland/files" / UNIT)
    require(unit["Service"]["Environment"] == "QS_DISABLE_FILE_WATCHER=1",
            "partial deployment can trigger a file-watcher reload")
    handlers = []
    for role, notice, surface in ((COMMON, SHELL_NOTICE, "quickshell"),
                                  (SWAY, GTK_NOTICE, "control-center")):
        candidates = yaml.safe_load((role / "handlers/main.yml").read_text())
        handler = next(item for item in candidates if item["name"] == notice)
        require(handler.get("become") is True and handler.get("become_user") == "{{ admin_user }}",
                "refresh must run as the configured desktop user")
        if surface == "quickshell":
            require(handler.get("when") == "not ansible_check_mode", "check mode can refresh a live UI")
        else:
            conditions = handler.get("when")
            require(isinstance(conditions, list) and len(conditions) == 2
                    and conditions[0] == "not ansible_check_mode",
                    "GTK retirement needs check-mode and changed-source guards")
        argv = shlex.split(handler["ansible.builtin.script"]["cmd"].replace(
            "{{ role_path }}", str(role)))
        require(len(argv) == 2 and Path(argv[0]).resolve() == SCRIPT and argv[1] == surface,
                "handler must use the reviewed refresh script and surface")
        require(handler["ansible.builtin.script"].get("executable") == "/usr/bin/python",
                "refresh interpreter changed")
        require(not any(key in handler for key in ("ignore_errors", "failed_when", "check_mode")),
                "refresh errors or check mode suppressed")
        handlers.append(handler)
    return [shell[0], helpers], handlers


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
    for state in (0, 3, 4, 1):
        calls = []

        def run(argv: list[str], calls: list[list[str]] = calls,
                state: int = state, **kwargs: Any) -> Any:
            require(kwargs["env"] == env and 0 < kwargs["timeout"] <= 30,
                    "refresh lost the user environment or deadline")
            calls.append(argv)
            return SimpleNamespace(returncode=state if len(calls) == 1 else 0)

        with patch.object(module.subprocess, "run", side_effect=run):
            if state == 1:
                refused(lambda: module.refresh_quickshell(env), "bus failure ignored")
            else:
                module.refresh_quickshell(env)
        expected = [["/usr/bin/systemctl", "--user", "is-active", "--quiet", UNIT]]
        if state == 0:
            expected += [["/usr/bin/systemctl", "--user", "try-restart", UNIT],
                         ["/usr/bin/systemctl", "--user", "is-active", "--quiet", UNIT]]
        require(calls == expected, "inactive or unrelated unit started, or active shell not refreshed")
    with patch.object(module.subprocess, "run", side_effect=subprocess.TimeoutExpired("refresh", 30)):
        refused(lambda: module.refresh_quickshell(env), "shell timeout ignored")
    def failed_restart(argv: list[str], **kwargs: Any) -> Any:
        if "try-restart" in argv:
            if kwargs.get("check"):
                raise subprocess.CalledProcessError(1, argv)
            return SimpleNamespace(returncode=1)
        return SimpleNamespace(returncode=0)

    with patch.object(module.subprocess, "run", side_effect=failed_restart):
        refused(lambda: module.refresh_quickshell(env), "shell restart failure ignored")

    for owners in ([False], [True, False], [True, True, False]):
        owner_states = iter(owners)

        def has_owner(_connection: Any, states: Any = owner_states, last: bool = owners[-1]) -> bool:
            return next(states, last)

        with patch.object(module, "control_center_connection", return_value=object()), \
                patch.object(module, "control_center_running", side_effect=has_owner), \
                patch.object(module.subprocess, "run") as run, \
                patch.object(module.time, "sleep"):
            module.refresh_control_center(env)
            if owners[0]:
                run.assert_called_once_with(["/usr/bin/gapplication", "action", APP_ID, "quit"],
                                            check=True, timeout=15, env=env)
            else:
                run.assert_not_called()
    with patch.object(module, "control_center_connection", return_value=object()), \
            patch.object(module, "control_center_running", return_value=True), \
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
                    patch.object(module, "refresh_quickshell") as shell, \
                    patch.object(module, "refresh_control_center") as gtk:
                require(module.main() == 0, "refresh entrypoint failed")
                expected = shell if function == "refresh_quickshell" else gtk
                other = gtk if expected is shell else shell
                other.assert_not_called()
                if session is None:
                    expected.assert_not_called()
                else:
                    expected.assert_called_once_with(env)


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


def ansible_contract(tasks: list[dict[str, Any]], handlers: list[dict[str, Any]], directory: Path) -> None:
    """Exercise Ansible's real copy and deferred handler scheduler, no live roles."""
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
    installed = directory / "installed"
    installed.mkdir()
    log = directory / "refreshes"
    probe = directory / "probe.py"
    probe.write_text("import pathlib, sys\n"
                     f"root = pathlib.Path({str(installed)!r})\n"
                     "assert (root / 'shell/shell.qml').is_file()\n"
                     "assert (root / 'shell/IsolationGlyph.qml').is_file()\n"
                     f"assert (root / {manager['dest']!r}).is_file()\n"
                     f"with open({str(log)!r}, 'a') as stream:\n"
                     "    stream.write(sys.argv[1] + '\\n')\n")
    fixture_tasks = [
        {"name": tasks[0]["name"], "notify": tasks[0]["notify"],
         "ansible.builtin.copy": {"src": str(shell) + "/", "dest": str(installed / "shell") + "/", "mode": "0644"}},
        {"name": tasks[1]["name"], "notify": tasks[1]["notify"], "loop": [manager, helper],
         "register": tasks[1]["register"],
         "ansible.builtin.copy": {"src": str(source) + "/{{ item.src }}",
                                  "dest": str(installed) + "/{{ item.dest }}", "mode": "0755"}},
    ]
    fixture_handlers = [
        {"name": handler["name"], "when": handler["when"],
         "ansible.builtin.command": {"argv": [sys.executable, str(probe), surface]},
         "changed_when": True}
        for handler, surface in zip(handlers, ("quickshell", "control-center"), strict=True)
    ]
    playbook = directory / "contract.yml"
    playbook.write_text(yaml.safe_dump([{"name": "Isolated desktop refresh", "hosts": "localhost",
                                       "gather_facts": False, "become": False,
                                       "tasks": fixture_tasks, "handlers": fixture_handlers}]))
    env = dict(os.environ, ANSIBLE_LOCAL_TEMP=str(directory / "local"),
               ANSIBLE_REMOTE_TEMP=str(directory / "remote"), ANSIBLE_NOCOLOR="1")

    def apply(expected: list[str], changed: bool = True, check: bool = False) -> None:
        log.write_text("")
        result = subprocess.run(["ansible-playbook", "-i", "localhost,", "-c", "local",
                                 str(playbook), *(["--check"] if check else [])],
                                env=env, capture_output=True, text=True, check=False, timeout=60)
        require(result.returncode == 0, "isolated Ansible fixture failed: " + result.stdout + result.stderr)
        require(sorted(log.read_text().splitlines()) == sorted(expected), "unexpected handler execution")
        if not changed:
            require("changed=0" in result.stdout, "second apply was not idempotent")

    apply(["quickshell", "control-center"])
    apply([], changed=False)
    (source / helper["src"]).write_text("helper two")
    apply([])
    (shell / "IsolationGlyph.qml").write_text("symbol two")
    (shell / "shell.qml").write_text("entry two")
    apply(["quickshell"])
    (source / manager["src"]).write_text("manager two")
    apply([], check=True)
    apply(["control-center"])
    apply([], changed=False)


def main() -> int:
    tasks, handlers = deployment_contract()
    module = load_refresh()
    with tempfile.TemporaryDirectory(prefix="shell-refresh-") as temporary:
        directory = Path(temporary)
        runtime_contract(module, directory)
        refresh_contract(module)
        gtk_transport_contract(module)
        ansible_contract(tasks, handlers, directory)
    print("Shell reload after apply contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
