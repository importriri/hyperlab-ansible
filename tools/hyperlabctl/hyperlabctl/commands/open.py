"""Open fixed graphical HyperLab shell surfaces through the authoritative CLI.

The launcher drawer and full Control Center are one single-instance GTK4 Layer
Shell application. Every target remains a fixed argv element; user-controlled
domain names never enter a shell program.
"""

import os
import shutil
import subprocess
from pathlib import Path

from ..errors import Unavailable
from .base import Command


_MANAGER = "/usr/local/bin/privatestack-hyperlab-domains"
_SECTIONS = (
    "overview",
    "domains",
    "vms",
    "create",
    "images",
    "policies",
    "gpu",
    "activity",
    "diagnostics",
)
_SURFACES = ("drawer", "overlay")


def _executable(command):
    if "/" in command:
        path = Path(command)
        if not path.is_file() or not os.access(path, os.X_OK):
            raise Unavailable("graphical helper is unavailable: %s" % command)
        return str(path)
    resolved = shutil.which(command)
    if resolved is None:
        raise Unavailable("graphical helper is unavailable: %s" % command)
    return resolved


class OpenCommand(Command):
    name = "open"
    help = "open fixed graphical HyperLab shell surfaces"
    order = 17

    def configure(self, parser):
        sub = parser.add_subparsers(dest="open_action", required=True)
        manager = sub.add_parser(
            "manager",
            help="toggle the Waybar drawer or full Layer Shell Control Center",
        )
        manager.add_argument("--surface", choices=_SURFACES, default="overlay")
        manager.add_argument("--section", choices=_SECTIONS, default="vms")
        console = sub.add_parser("console", help="open a libvirt graphical console")
        console.add_argument("domain")
        sub.add_parser("looking-glass", help="open the Looking Glass client")

    def run(self, args, ctx):
        del ctx
        if args.open_action == "manager":
            executable = _executable(_MANAGER)
            subprocess.Popen(
                [
                    executable,
                    "--surface",
                    args.surface,
                    "--section",
                    args.section,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return 0
        if args.open_action == "console":
            argv = [
                "virt-viewer",
                "--connect",
                "qemu:///system",
                "--wait",
                args.domain,
            ]
        else:
            argv = ["looking-glass-client"]

        executable = _executable(argv[0])
        os.execv(executable, [executable, *argv[1:]])
        raise AssertionError("os.execv unexpectedly returned")
