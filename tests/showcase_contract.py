#!/usr/bin/env python3
"""The showcase script only walks the take; it never changes the host.

It must not use privilege or a become prompt, must reach the shell only
through reviewed IPC targets, must validate the Machine name before using
it, and must print the strings the published film may not show. The
storyboard it follows must fit the roadmap's 60 to 90 seconds.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/showcase/demo.sh"
DOC = ROOT / "docs/showcase.md"
IPC = ROOT / "roles/host_desktop_common/files/quickshell/hyperlab/ShellIpc.qml"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    source = SCRIPT.read_text()
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    for forbidden in ("sudo", " -K", "ansible-playbook", "virsh", "pkexec", "rm "):
        require(forbidden not in code, f"the showcase script must not use {forbidden.strip()}")

    ipc = IPC.read_text()
    calls = re.findall(r"shell_ipc (\w+) (\w+)", code)
    require(calls, "the script reaches no shell surface")
    for target, function in calls:
        block = ipc.split(f'target: "{target}"', 1)
        require(len(block) == 2 and f"function {function}(" in block[1].split("target:", 1)[0],
                f"shell IPC {target}.{function} is not a reviewed target")

    for bad in ("", "Demo", "-x", "a" * 40, "x;id", "--help"):
        result = subprocess.run(["sh", str(SCRIPT), bad], capture_output=True, text=True,
                                timeout=10, check=False, env={"PATH": "/usr/bin:/bin"})
        require(result.returncode == 2, f"name {bad!r} was not refused before anything ran")

    for shown in ("host name", "user name", "home path", "address"):
        require(f"'  {shown}" in source, f"the script does not print the {shown} to keep off screen")

    seconds = [int(cell) for cell in re.findall(r"^\| \d+ \| (\d+) \|", DOC.read_text(), re.M)]
    require(len(seconds) >= 5 and 60 <= sum(seconds) <= 90,
            f"the storyboard runs {sum(seconds)} seconds, not 60 to 90")
    print("Showcase contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
