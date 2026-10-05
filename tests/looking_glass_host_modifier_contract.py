#!/usr/bin/env python3
"""The host's SUPER key never reaches a Linux guest through Looking Glass.

problems/looking-glass-super-key-reached-guest.md: "8;10u" appeared in a
guest terminal. It is what Bash's readline leaves of the CSI u report of
SUPER+SHIFT+L (also B or V), which the guest's kitty sends for a key with
the SUPER modifier. The Looking Glass client passed SUPER to the guest,
whose shortcuts use ALT and bind nothing to SUPER, while it held the
keyboard and the host's own shortcuts were off.

  1. the symptom: an interactive Bash given that report shows "8;10u";
  2. the opener tells the client to keep SUPER for a Linux guest, and only
     for a Linux guest (a Windows guest keeps its Windows key);
  3. the guest compositor binds nothing to SUPER, so no guest shortcut is
     lost.
"""

from __future__ import annotations

import os
import pty
import re
import select
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPEN = ROOT / "tools/hyperlabctl/hyperlabctl/commands/open.py"
GUEST_HYPRLAND = ROOT / "roles/guest_desktop_hyprland/templates/hyprland.lua.j2"
SUPER_SHIFT_L = b"\x1b[108;10u"  # key 108 ('l'), modifiers 1 + shift(1) + super(8)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def bash_echo(sequence: bytes) -> bytes:
    pid, fd = pty.fork()
    if pid == 0:
        os.environ.update({"TERM": "xterm-kitty", "PS1": "$ ", "INPUTRC": "/dev/null"})
        os.execvp("bash", ["bash", "--norc", "--noprofile", "-i"])
    try:
        deadline = time.monotonic() + 5
        prompt = b""
        while b"$ " not in prompt and time.monotonic() < deadline:
            if select.select([fd], [], [], 0.1)[0]:
                prompt += os.read(fd, 4096)
        os.write(fd, sequence)
        echoed = b""
        quiet_since = time.monotonic()
        while time.monotonic() - quiet_since < 0.5 and time.monotonic() < deadline + 5:
            if select.select([fd], [], [], 0.1)[0]:
                echoed += os.read(fd, 4096)
                quiet_since = time.monotonic()
        return echoed.replace(b"\x07", b"")
    finally:
        os.kill(pid, 9)
        os.waitpid(pid, 0)


def main() -> int:
    require(shutil.which("bash") is not None, "bash is needed to show the symptom")
    echoed = bash_echo(SUPER_SHIFT_L)
    require(echoed == b"8;10u", f"Bash did not turn SUPER+SHIFT+L into the reported text: {echoed!r}")

    opener = OPEN.read_text(encoding="utf-8")
    linux = re.search(r'( +)if transport == "linux-experimental":\n'
                      r'\1    argv\.append\("egl:mapHDRtoSDR=no"\)\n((?:\1    .*\n)*)', opener)
    require(linux is not None, "the opener has no Linux-guest branch")
    require('argv.append("input:ignoreWindowsKeys=yes")' in linux.group(2),
            "the Looking Glass client passes SUPER to a Linux guest")
    require(opener.count("ignoreWindowsKeys") == 1,
            "the Windows key is withheld outside the Linux-guest branch")

    guest = GUEST_HYPRLAND.read_text(encoding="utf-8")
    require('local main_mod = "ALT"' in guest, "the guest compositor's modifier is no longer ALT")
    code = "\n".join(line for line in guest.splitlines() if not line.lstrip().startswith("--"))
    require("SUPER" not in code.upper(), "the guest compositor binds something to SUPER")
    print("Looking Glass host modifier contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
