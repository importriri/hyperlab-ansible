#!/usr/bin/env python3
"""Host-to-guest clipboard: one host action, one Machine, text only (ADR 0020).

Runs the real guest receiver against a fake wl-copy, the real host sender
against fake wl-paste and ssh, and the real bridge verb against inert
fixtures. Nothing reaches a clipboard, a guest or libvirt.
"""
from __future__ import annotations

import importlib.util
import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
RECEIVER = ROOT / "roles/guest_desktop_hyprland/files/hyperlab-clipboard-receive.py"
BRIDGE = ROOT / "roles/host_desktop_common/files/privatestack-machine-actions.py"
sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))

from hyperlabctl import registry  # noqa: E402
from hyperlabctl.commands import clipboard  # noqa: E402
from hyperlabctl.errors import Unavailable  # noqa: E402

TEXT = "git clone https://example.invalid/hyperlab.git && cd hyperlab — ✓\n".encode()


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


# What logind reported on dev-01 when the first send was refused: the systemd
# user manager, two SSH logins (one closing) and the seated Wayland session.
DEV01_SESSIONS = {
    "1": {"Type": "unspecified", "Remote": "no", "Seat": "", "Class": "manager", "State": "active"},
    "12": {"Type": "tty", "Remote": "yes", "Seat": "", "Class": "user", "State": "active"},
    "5": {"Type": "tty", "Remote": "yes", "Seat": "", "Class": "user", "State": "closing"},
    "c1": {"Type": "wayland", "Remote": "no", "Seat": "seat0", "Class": "user", "State": "active"},
}
# ... and its runtime directory: the compositor socket, awww's socket beside
# it with the same prefix, and the compositor lock.
DEV01_RUNTIME = ("wayland-1", "wayland-1-awww-daemon.sock")


def fake_loginctl(path: Path, sessions: dict) -> None:
    lines = ["#!/usr/bin/python3", "import sys", f"sessions = {sessions!r}",
             "args = sys.argv[1:]",
             "if args[0] == 'show-user':",
             "    print('Sessions=' + ' '.join(sessions))",
             "elif args[0] == 'show-session':",
             "    info = sessions[args[1]]",
             "    for arg in args[2:]:",
             "        key = arg.split('=', 1)[1]",
             "        print(f'{key}={info[key]}')",
             "else:",
             "    sys.exit(1)"]
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o755)


def receiver_cases() -> None:
    def run(data: bytes, sockets=DEV01_RUNTIME, sessions=DEV01_SESSIONS) -> tuple[int, str, bytes | None]:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "runtime"
            runtime.mkdir(mode=0o700)
            listeners = []
            for name in sockets:
                listener = socket.socket(socket.AF_UNIX)
                listener.bind(str(runtime / name))
                listeners.append(listener)
            (runtime / "wayland-1.lock").write_text("")
            bin_dir = base / "bin"
            bin_dir.mkdir()
            got = base / "got"
            (bin_dir / "wl-copy").write_text(
                f"#!/bin/sh\n[ \"$WAYLAND_DISPLAY\" = wayland-1 ] || exit 9\ncat > {got}\n")
            (bin_dir / "wl-copy").chmod(0o755)
            loginctl = bin_dir / "loginctl"
            fake_loginctl(loginctl, sessions)
            # The receiver runs with the real loginctl path; only that constant
            # is pointed at the fake.
            wrapper = base / "receive.py"
            wrapper.write_text(
                "import runpy, sys\n"
                f"module = runpy.run_path({str(RECEIVER)!r}, run_name='receiver')\n"
                f"module['LOGINCTL'] = {str(loginctl)!r}\n"
                "module['session_display'].__defaults__ = (module['LOGINCTL'],)\n"
                "try:\n"
                "    sys.exit(module['main']())\n"
                "except RuntimeError as exc:\n"
                "    print(f'HyperLab clipboard refused: {exc}', file=sys.stderr)\n"
                "    sys.exit(2)\n")
            result = subprocess.run(
                [sys.executable, str(wrapper)], input=data, capture_output=True, check=False,
                env={"PATH": f"{bin_dir}:/usr/bin", "XDG_RUNTIME_DIR": str(runtime)})
            for listener in listeners:
                listener.close()
            return result.returncode, result.stderr.decode(), got.read_bytes() if got.exists() else None

    # The real dev-01 case that was refused: it must now be delivered.
    rc, error, got = run(TEXT)
    require(rc == 0 and got == TEXT,
            f"the receiver refused dev-01's real session layout: {rc} {error} {got!r}")
    for data, reason in ((b"", "nothing was sent"), (b"x" * ((1 << 20) + 1), "larger than 1 MiB"),
                         (b"\xff\xfe", "not UTF-8"), (b"a\x00b", "NUL")):
        rc, error, got = run(data)
        require(rc == 2 and reason in error and got is None, f"receiver accepted {reason}: {error}")

    second = dict(DEV01_SESSIONS, c2={"Type": "wayland", "Remote": "no", "Seat": "seat0",
                                      "Class": "user", "State": "online"})
    ssh_only = {key: value for key, value in DEV01_SESSIONS.items() if key != "c1"}
    remote = dict(ssh_only, c3={"Type": "wayland", "Remote": "yes", "Seat": "", "Class": "user",
                                "State": "active"})
    for sessions, label in ((second, "two local graphical sessions"), (ssh_only, "SSH logins only"),
                            (remote, "a remote Wayland session")):
        rc, error, got = run(TEXT, sessions=sessions)
        require(rc == 2 and "no single local graphical session" in error and got is None,
                f"receiver delivered with {label}: {error}")
    for sockets, label in (((), "no compositor socket"), (("wayland-1", "wayland-2"), "two compositor sockets"),
                           (("wayland-1-awww-daemon.sock",), "only a helper socket")):
        rc, error, got = run(TEXT, sockets=sockets)
        require(rc == 2 and "no single Wayland display socket" in error and got is None,
                f"receiver guessed a display with {label}: {error}")
    source = RECEIVER.read_text(encoding="utf-8")
    require("shell=True" not in source and "os.system" not in source and "eval(" not in source,
            "the receiver gained a way to execute what it receives")
    require('LOGINCTL = "/usr/bin/loginctl"' in source, "the receiver no longer asks logind")


def sender_cases() -> None:
    calls: list[tuple[list[str], bytes | None]] = []

    def fake_run(clip: bytes, types: str = "text/plain;charset=utf-8\ntext/plain\n", ssh_rc: int = 0):
        def run(argv, input=None, **kwargs):
            calls.append((list(argv), input))
            if argv[1:] == ["--list-types"]:
                return SimpleNamespace(returncode=0, stdout=types.encode(), stderr=b"")
            if "--no-newline" in argv:
                return SimpleNamespace(returncode=0, stdout=clip, stderr=b"")
            return SimpleNamespace(returncode=ssh_rc, stdout=b"",
                                   stderr=b"HyperLab clipboard refused: wl-copy is not installed\n")
        return run

    clipboard._executable = lambda name: "/usr/bin/" + name
    clipboard._ssh_argv = lambda ctx, domain: ["ssh", "-o", "StrictHostKeyChecking=yes", f"sid@{domain}"]
    clipboard._wait_for_ssh_ready = lambda argv, domain: None

    require(clipboard.send(None, "dev-01", fake_run(TEXT)) == len(TEXT), "the sender did not report the size")
    ssh_call = calls[-1]
    require(ssh_call[0] == ["ssh", "-o", "StrictHostKeyChecking=yes", "-T", "sid@dev-01",
                            "hyperlab-clipboard-receive"],
            f"the text did not go to the fixed receiver over the reviewed SSH argv: {ssh_call[0]}")
    require(ssh_call[1] == TEXT and all(TEXT.decode() not in " ".join(argv) for argv, _ in calls),
            "the text was not piped on stdin only")

    for run, reason in ((fake_run(TEXT, types="image/png\n"), "no text"),
                        (fake_run(b""), "empty"),
                        (fake_run(b"x" * ((1 << 20) + 1)), "more than 1 MiB"),
                        (fake_run(b"\xff"), "not UTF-8"),
                        (fake_run(b"a\x00"), "NUL"),
                        (fake_run(TEXT, ssh_rc=127), "no clipboard receiver"),
                        (fake_run(TEXT, ssh_rc=2), "wl-copy is not installed")):
        calls.clear()
        try:
            clipboard.send(None, "srv-01", run)
        except Unavailable as exc:
            require(reason in str(exc), f"refused for the wrong reason: {exc}")
        else:
            raise AssertionError(f"the sender accepted: {reason}")
        if reason in ("no text", "empty", "more than 1 MiB", "not UTF-8", "NUL"):
            require(not any(argv[0] == "ssh" for argv, _ in calls), f"{reason} still reached the guest")

    action = registry.by_id("vm.clipboard-send")
    require(action["command"] == ["hyperlabctl", "clipboard", "send", "{domain}"]
            and action["privileged"] is False and action["target"] == "domain",
            "the clipboard action is not the reviewed unprivileged command")


def bridge_cases() -> None:
    spec = importlib.util.spec_from_file_location("clipboard_bridge", BRIDGE)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    executed: list[list[str]] = []
    emitted: list[dict] = []
    state = {"machine": {"name": "dev-01", "state": "running", "managed": True, "vfio": True}}
    bridge.live_machine = lambda name: dict(state["machine"], name=name)
    bridge.managed_spec = lambda name: {"path": f"vm-specs/.generated/{name}.yml", "spec": {"name": name}}
    bridge.runtime_ssh_problem = lambda name: None
    bridge.cli_json = lambda *args: (["hyperlabctl", "clipboard", "send", args[-1]]
                                     if args[:3] == ("actions", "--resolve", "vm.clipboard-send")
                                     else (_ for _ in ()).throw(AssertionError(args)))
    bridge.emit = emitted.append
    bridge.os.execvp = lambda program, argv: executed.append(list(argv))

    sys.argv = ["bridge", "clipboard", "dev-01"]
    bridge.main()
    require(executed == [["hyperlabctl", "clipboard", "send", "dev-01"]],
            f"the bridge did not run the reviewed command: {executed}")
    require(emitted and emitted[0]["verb"] == "clipboard" and emitted[0]["phase"] == "accepted",
            "the bridge did not report the clipboard operation")

    executed.clear()
    state["machine"]["state"] = "shut off"
    try:
        bridge.main()
    except bridge.Refused as exc:
        require("SSH requires a running managed machine" in str(exc), str(exc))
    else:
        raise AssertionError("a stopped Machine was sent the clipboard")
    require(not executed, "a refused clipboard request ran")
    require("clipboard" not in bridge.VERBS,
            "clipboard joined the capability verbs the shell validates")


def static_cases() -> None:
    tasks = (ROOT / "roles/guest_desktop_hyprland/tasks/main.yml").read_text(encoding="utf-8")
    require("src: hyperlab-clipboard-receive.py" in tasks
            and "dest: /usr/local/bin/hyperlab-clipboard-receive" in tasks,
            "the guest role does not install the receiver")
    # A Machine never gets the continuous SPICE clipboard; the host action is
    # the only way text crosses.
    factory = (ROOT / "tools/hyperlabctl/hyperlabctl/machine_factory.py").read_text(encoding="utf-8")
    require('"clipboard": False,' in factory, "the Machine projection enabled the SPICE clipboard")


def main() -> int:
    receiver_cases()
    sender_cases()
    bridge_cases()
    static_cases()
    print("HyperLab clipboard crossing contract: OK")
    return 0


if __name__ == "__main__":
    os.umask(0o022)
    raise SystemExit(main())
