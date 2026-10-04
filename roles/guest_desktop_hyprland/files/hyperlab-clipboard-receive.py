#!/usr/bin/python3 -I
"""Receive one text sent from the HyperLab host and put it on this clipboard.

The host runs this over its pinned SSH channel with the text on stdin
(ADR 0020). It never runs anything the text says: it checks the size and the
encoding, finds this account's own Wayland session and hands the text to
wl-copy, which keeps serving it after this program exits.
"""
from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path

LIMIT = 1 << 20
LOGINCTL = "/usr/bin/loginctl"
# The compositor's display socket. Other programs put their own sockets beside
# it with the same prefix (awww's wayland-1-awww-daemon.sock); they are not a
# session.
DISPLAY_SOCKET = re.compile(r"^wayland-[0-9]+$")


def properties(argv: list[str]) -> dict[str, str]:
    result = subprocess.run(argv, capture_output=True, text=True, timeout=5, check=False)
    if result.returncode != 0:
        raise RuntimeError("logind did not answer")
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def local_graphical_sessions(loginctl: str = LOGINCTL) -> list[str]:
    """This account's local, seated, active Wayland sessions, from logind."""
    user = properties([loginctl, "show-user", str(os.getuid()), "--property=Sessions"])
    found = []
    for session in user.get("Sessions", "").split():
        info = properties([loginctl, "show-session", session, "--property=Type",
                           "--property=Remote", "--property=Seat", "--property=Class",
                           "--property=State"])
        if (info.get("Type") == "wayland" and info.get("Remote") == "no"
                and info.get("Seat", "") != "" and info.get("Class") == "user"
                and info.get("State") in ("active", "online")):
            found.append(session)
    return found


def session_display(runtime: Path, loginctl: str = LOGINCTL) -> str:
    """The one compositor socket of this account's one local session, or refuse.

    An SSH login is a session too, but not a graphical one; it never counts.
    """
    if len(local_graphical_sessions(loginctl)) != 1:
        raise RuntimeError("no single local graphical session is running for this account")
    sockets = sorted(
        path.name for path in runtime.iterdir()
        if DISPLAY_SOCKET.fullmatch(path.name)
        and stat.S_ISSOCK(path.lstat().st_mode)
        and path.lstat().st_uid == os.getuid()
    )
    if len(sockets) != 1:
        raise RuntimeError("the graphical session has no single Wayland display socket")
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
