#!/usr/bin/env python3
"""Host applications start only from the reviewed catalogue (milestone 8).

The shell names an application id; the shell action bridge accepts it only
if it is in APPLICATIONS, its desktop entry is a regular file the session
cannot change, and then hands `gio launch` that entry's path, never the id
or anything else the caller sent. `applications` lists only what is present
and trusted.
"""

from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "roles/host_desktop_common/files/privatestack-shell-actions.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def load():
    spec = importlib.util.spec_from_file_location("shell_actions", BRIDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    bridge = load()
    quiet = io.StringIO()
    with redirect_stderr(quiet):
        check(bridge)
    require("rejected" in quiet.getvalue(), "a refusal did not say why")
    print("Host app launch contract: OK")
    return 0


def check(bridge) -> None:
    require(bridge.APPLICATIONS == ("foot", "nemo"), "the reviewed host application catalogue changed")
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        bridge.APPLICATIONS_DIR = directory
        bridge.TRUSTED_UID = os.getuid()
        (directory / "foot.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=Foot\nName[it]=Piede\nIcon=foot\nExec=foot\n"
            "[Desktop Action server]\nName=Server\n")
        (directory / "nemo.desktop").write_text("[Desktop Entry]\nName=Files\nExec=nemo\n")
        (directory / "nemo.desktop").chmod(0o664)  # group-writable: not trusted
        (directory / "firefox.desktop").write_text("[Desktop Entry]\nName=Firefox\n")

        argv = bridge.resolve(["app-launch", "foot"])
        require(argv == ("/usr/bin/gio", "launch", str(directory / "foot.desktop")),
                f"a catalogue application did not resolve to its entry: {argv!r}")
        for refused in ("nemo", "firefox", "../foot", "Foot", "foot extra", "", "-foot"):
            require(bridge.resolve(["app-launch", refused]) is None, f"app-launch {refused!r} was accepted")
        require(bridge.resolve(["app-launch"]) is None and bridge.resolve(["app-launch", "foot", "x"]) is None,
                "app-launch accepted a wrong number of arguments")

        (directory / "nemo.desktop").chmod(0o644)
        (directory / "nemo.desktop").rename(directory / "real-nemo.desktop")
        (directory / "nemo.desktop").symlink_to(directory / "real-nemo.desktop")
        require(bridge.resolve(["app-launch", "nemo"]) is None, "a symlinked entry was accepted")

        out = io.StringIO()
        with redirect_stdout(out):
            require(bridge.applications() == 0, "applications failed")
        listed = json.loads(out.getvalue())["applications"]
        require(listed == [{"id": "foot", "name": "Foot", "icon": "foot"}],
                f"applications listed something untrusted or misread: {listed!r}")

        bridge.TRUSTED_UID = os.getuid() + 1
        require(bridge.resolve(["app-launch", "foot"]) is None, "an entry the session owns was accepted")

    shell_actions = (ROOT / "roles/host_desktop_common/files/quickshell/hyperlab/ShellActions.qml").read_text()
    require('"app-launch"' in shell_actions and "launchApplication" in shell_actions,
            "the shell cannot start a catalogue application")


if __name__ == "__main__":
    sys.exit(main())
