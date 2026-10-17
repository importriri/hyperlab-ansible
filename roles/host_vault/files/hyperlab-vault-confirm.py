#!/usr/bin/python3
"""hyperlab-vault-confirm MACHINE FINGERPRINT COMMENT - ask the operator.

Shows one host dialog naming the Machine and the key, and prints one of the
answers the relay accepts: deny, allow-once, allow-minutes:N. A closed
dialog, an unknown button or no display prints deny. The Machine name comes
from libvirt and the comment from the vault, yet both are shown as plain
text: the dialog's label would otherwise read markup in them.
"""

from __future__ import annotations

import html
import subprocess
import sys

DIALOG = "/usr/bin/hyprland-dialog"
MINUTES = 5
BUTTONS = {"Deny": "deny", "Allow once": "allow-once", f"Allow {MINUTES} minutes": f"allow-minutes:{MINUTES}"}


def plain(value: str, limit: int) -> str:
    printable = "".join(ch if ch.isprintable() else "?" for ch in value)[:limit]
    return html.escape(printable, quote=True)


def answer(argv: list[str], run=subprocess.run) -> str:
    if len(argv) != 3:
        return "deny"
    machine, key, comment = (plain(argv[0], 64), plain(argv[1], 64), plain(argv[2], 120))
    text = (f"Machine {machine} asks the key vault for a signature.<br><br>"
            f"Key: {key}<br>Comment: {comment}<br><br>"
            "Allow only if you started an SSH connection or a signed commit there just now.")
    try:
        result = run([DIALOG, "--title", "HyperLab key vault", "--apptitle", "Signature request",
                      "--text", text, "--buttons", ";".join(BUTTONS)],
                     capture_output=True, text=True, check=False)
    except OSError:
        return "deny"
    if result.returncode != 0:
        return "deny"
    return BUTTONS.get(result.stdout.strip(), "deny")


if __name__ == "__main__":
    print(answer(sys.argv[1:]))
