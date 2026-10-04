#!/usr/bin/env python3
"""The Linux Looking Glass sender keeps the evidence of its previous run.

After a `hyprctl reload` in dev-01 the client stayed on the splash screen,
and the sender's log was gone: every launch overwrote it. The real supervisor
from `hyperlabctl open looking-glass` runs here with a fake sender and a fake
pgrep; the previous log must survive as .1 and the new one must say when the
sender started, for which Hyprland, and how it ended.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))

from hyperlabctl.commands import open as open_command  # noqa: E402

START = "<<'HYPERLAB_LG_SUPERVISOR' &\n"
END = "\nHYPERLAB_LG_SUPERVISOR\n"


def require(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def supervisor() -> str:
    script = open_command._LINUX_LOOKING_GLASS_PREPARE
    start = script.index(START) + len(START)
    return script[start:script.index(END, start)] + "\n"


def run(body: str, hyprland_checks: int, sender_exit: int) -> tuple[str, str]:
    with tempfile.TemporaryDirectory() as temporary:
        base = Path(temporary)
        bin_dir = base / "bin"
        bin_dir.mkdir()
        counter = base / "count"
        counter.write_text("0")
        # Hyprland is "running" for the first N checks, then gone.
        (bin_dir / "pgrep").write_text(
            f"#!/bin/sh\nn=$(cat {counter}); echo $((n+1)) > {counter}\n"
            f"[ \"$n\" -lt {hyprland_checks} ]\n")
        sender = bin_dir / "looking-glass-host"
        sender.write_text(f"#!/bin/sh\necho 'fake sender capturing'\nsleep 1.2\nexit {sender_exit}\n")
        for program in (bin_dir / "pgrep", sender):
            program.chmod(0o755)
        log = base / "looking-glass-host.log"
        log.write_text("previous run: capture stopped\n")
        script = body.replace("/usr/local/bin/looking-glass-host", str(sender))
        subprocess.run(["bash", "-s", "--", str(log)], input=script, text=True, timeout=30, check=False,
                       env={**os.environ, "PATH": f"{bin_dir}:/usr/bin:/bin",
                            "HYPRLAND_INSTANCE_SIGNATURE": "fixture_signature"})
        return log.read_text(), (base / "looking-glass-host.log.1").read_text()


def main() -> int:
    body = supervisor()
    require("set -u" in body and 'kill "$sender_pid"' in body, "the supervisor lost its session binding")

    current, previous = run(body, hyprland_checks=100, sender_exit=3)
    require(previous == "previous run: capture stopped\n", f"the previous log was not kept: {previous!r}")
    lines = current.splitlines()
    require(lines[0].startswith("HyperLab: sender started ") and lines[0].endswith("for Hyprland fixture_signature"),
            f"the log does not say when and for which Hyprland the sender started: {lines[:1]}")
    require("fake sender capturing" in current, "the sender's own output is not in the log")
    require(lines[-1].startswith("HyperLab: sender exited with status 3 "),
            f"the log does not record how the sender ended: {lines[-1:]}")

    current, _ = run(body, hyprland_checks=1, sender_exit=0)
    require("HyperLab: Hyprland is gone; stopping the sender" in current,
            f"the log does not record why the supervisor stopped the sender: {current!r}")

    result = subprocess.run(["bash", "-n"], input=open_command._LINUX_LOOKING_GLASS_PREPARE,
                            text=True, capture_output=True, check=False)
    require(result.returncode == 0, f"the prepare script no longer parses: {result.stderr}")
    print("Looking Glass sender log contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
