"""Send the host clipboard to one Machine, once (ADR 0020).

The text is read from the host's Wayland clipboard as text only, checked,
and piped over the same reviewed SSH argv `hyperlabctl open ssh` uses to the
guest's fixed receiver. It never appears in an argument vector or in this
command's output, which reports only the byte count.
"""

import json
import subprocess

from ..errors import Unavailable
from .base import Command
from .open import _executable, _ssh_argv, _wait_for_ssh_ready

LIMIT = 1 << 20
RECEIVER = "hyperlab-clipboard-receive"
_WL_PASTE = "wl-paste"
_TIMEOUT_SECONDS = 20


def read_host_clipboard(run=subprocess.run):
    """The host clipboard as UTF-8 text, or refuse."""
    types = run([_executable(_WL_PASTE), "--list-types"], capture_output=True,
                timeout=5, check=False)
    offered = types.stdout.decode("utf-8", "replace").split() if types.returncode == 0 else []
    if not any(kind.startswith("text/plain") for kind in offered):
        raise Unavailable("the host clipboard holds no text")
    result = run([_executable(_WL_PASTE), "--no-newline", "--type", "text/plain"],
                 capture_output=True, timeout=5, check=False)
    data = result.stdout
    if result.returncode != 0 or not data:
        raise Unavailable("the host clipboard is empty")
    if len(data) > LIMIT:
        raise Unavailable("the host clipboard holds more than 1 MiB")
    if b"\x00" in data:
        raise Unavailable("the host clipboard text contains a NUL byte")
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise Unavailable("the host clipboard text is not UTF-8") from exc
    return data


def send(ctx, domain, run=subprocess.run):
    data = read_host_clipboard(run)
    ssh_argv = _ssh_argv(ctx, domain)
    _wait_for_ssh_ready(ssh_argv, domain)
    result = run([*ssh_argv[:-1], "-T", ssh_argv[-1], RECEIVER], input=data,
                 capture_output=True, timeout=_TIMEOUT_SECONDS, check=False)
    if result.returncode == 127:
        raise Unavailable("%s has no clipboard receiver; only workstation Machines take a clipboard"
                          % domain)
    if result.returncode != 0:
        detail = result.stderr.decode("utf-8", "replace").strip().splitlines()
        raise Unavailable("%s refused the clipboard: %s"
                          % (domain, detail[-1][-300:] if detail else "exit %d" % result.returncode))
    return len(data)


class ClipboardCommand(Command):
    name = "clipboard"
    help = "send the host clipboard text to one Machine, once"
    order = 23

    def configure(self, parser):
        sub = parser.add_subparsers(dest="clipboard_action", required=True)
        target = sub.add_parser("send", help="send the host clipboard text to one Machine")
        target.add_argument("domain")

    def run(self, args, ctx):
        sent = send(ctx, args.domain)
        if args.json:
            print(json.dumps({"phase": "sent", "machine": args.domain, "bytes": sent}))
        else:
            print("sent %d bytes to %s" % (sent, args.domain))
        return 0
