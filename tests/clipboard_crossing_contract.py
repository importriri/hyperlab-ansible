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


def receiver_cases() -> None:
    def run(data: bytes, sockets: int = 1) -> tuple[int, str, bytes | None]:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            runtime = base / "runtime"
            runtime.mkdir(mode=0o700)
            listeners = []
            for index in range(sockets):
                listener = socket.socket(socket.AF_UNIX)
                listener.bind(str(runtime / f"wayland-{index + 1}"))
                listeners.append(listener)
            (runtime / "wayland-1.lock").write_text("")
            bin_dir = base / "bin"
            bin_dir.mkdir()
            got = base / "got"
            (bin_dir / "wl-copy").write_text(
                f"#!/bin/sh\n[ \"$WAYLAND_DISPLAY\" = wayland-1 ] || exit 9\ncat > {got}\n")
            (bin_dir / "wl-copy").chmod(0o755)
            result = subprocess.run(
                [sys.executable, str(RECEIVER)], input=data, capture_output=True, check=False,
                env={"PATH": f"{bin_dir}:/usr/bin", "XDG_RUNTIME_DIR": str(runtime)})
            for listener in listeners:
                listener.close()
            return result.returncode, result.stderr.decode(), got.read_bytes() if got.exists() else None

    rc, _, got = run(TEXT)
    require(rc == 0 and got == TEXT, f"the receiver did not hand the text to wl-copy: {rc} {got!r}")
    for data, reason in ((b"", "nothing was sent"), (b"x" * ((1 << 20) + 1), "larger than 1 MiB"),
                         (b"\xff\xfe", "not UTF-8"), (b"a\x00b", "NUL")):
        rc, error, got = run(data)
        require(rc == 2 and reason in error and got is None, f"receiver accepted {reason}: {error}")
    for count in (0, 2):
        rc, error, got = run(TEXT, sockets=count)
        require(rc == 2 and "no single graphical session" in error and got is None,
                f"receiver guessed a session among {count}")
    source = RECEIVER.read_text(encoding="utf-8")
    require("shell=True" not in source and "os.system" not in source and "eval(" not in source,
            "the receiver gained a way to execute what it receives")


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
