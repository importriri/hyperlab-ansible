#!/usr/bin/python3 -I
"""Receive one text sent from the HyperLab host and put it on this clipboard.

The host runs this over its pinned SSH channel with the text on stdin
(ADR 0020). It never runs anything the text says: it checks the size and the
encoding, finds this account's own Wayland session and hands the text to
wl-copy, which keeps serving it after this program exits.
"""
from __future__ import annotations

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

LIMIT = 1 << 20


def session_display(runtime: Path) -> str:
    """The one Wayland socket of this account's session, or refuse."""
    sockets = sorted(
        path.name for path in runtime.glob("wayland-*")
        if not path.name.endswith(".lock")
        and stat.S_ISSOCK(path.lstat().st_mode)
        and path.lstat().st_uid == os.getuid()
    )
    if len(sockets) != 1:
        raise RuntimeError("no single graphical session is running for this account")
    return sockets[0]


def main() -> int:
    data = sys.stdin.buffer.read(LIMIT + 1)
    if not data:
        raise RuntimeError("nothing was sent")
    if len(data) > LIMIT:
        raise RuntimeError("the text is larger than 1 MiB")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError("the text is not UTF-8") from exc
    if b"\x00" in data:
        raise RuntimeError("the text contains a NUL byte")

    runtime = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
    info = runtime.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError("the session runtime directory is not this account's")
    wl_copy = shutil.which("wl-copy")
    if wl_copy is None:
        raise RuntimeError("wl-copy is not installed")
    env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), WAYLAND_DISPLAY=session_display(runtime))

    # wl-copy forks a server that owns the selection; its output is closed so
    # the SSH session that delivered the text can end.
    result = subprocess.run([wl_copy, "--type", "text/plain;charset=utf-8"], input=data, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=False)
    if result.returncode != 0:
        raise RuntimeError("the session clipboard refused the text")

    notify = shutil.which("notify-send")
    if notify is not None:
        subprocess.run([notify, "--app-name=HyperLab", "Clipboard received from the host",
                        f"{len(data)} bytes, ready to paste"], env=env,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5, check=False)
    print(f"received {len(data)} bytes")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
        print(f"HyperLab clipboard refused: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
