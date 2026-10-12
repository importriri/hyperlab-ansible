#!/usr/bin/env python3
"""The Looking Glass client's output goes to a private file under the user's
state directory, replaced at each start
(problems/looking-glass-client-output-was-lost.md).

`hyperlabctl open looking-glass` execs the client. Its output used to reach
only whoever started it: from the shell, Quickshell kept stderr in memory
and dropped it when the client ended, so a client that did not reconnect to
a restarted sender left no trace. Each case below runs the real redirect in
a child process that then execs a stand-in client writing to both streams.
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "tools/hyperlabctl"
OPENER = CLI / "hyperlabctl/commands/open.py"
CHILD = """
import os, sys
sys.path.insert(0, sys.argv[1])
from hyperlabctl.commands import open as opener
from hyperlabctl.errors import Unavailable
try:
    opener._redirect_looking_glass_output(sys.argv[2])
except Unavailable as exc:
    print("refused: %s" % exc, file=sys.stderr)
    raise SystemExit(3)
os.execv("/bin/sh", ["/bin/sh", "-c", "echo client-out " + sys.argv[3] + "; echo client-err >&2"])
"""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"Looking Glass client log contract: {message}")


def launch(home: Path, domain: str, marker: str, state_home: str | None = None) -> subprocess.CompletedProcess:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(home)}
    if state_home is not None:
        env["XDG_STATE_HOME"] = state_home
    return subprocess.run([sys.executable, "-c", CHILD, str(CLI), domain, marker], env=env,
                          capture_output=True, text=True, timeout=20, check=False)


def check_order() -> None:
    run = OPENER.read_text(encoding="utf-8").split("    def run(self, args, ctx):", 1)[1]
    redirect = run.find("_redirect_looking_glass_output(managed_surface_domain)")
    require(redirect >= 0, "open looking-glass does not send the client's output to its log")
    guard = run.rfind('if managed_surface_kind == "looking-glass":', 0, redirect)
    require(guard >= 0 and run.index("_register_surface_provenance(") < guard < redirect
            < run.index("os.execv(executable"),
            "the client's output is redirected outside the Looking Glass branch, or after the exec")


def check_behaviour() -> None:
    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        state = home / "state"
        log = state / "hyperlab/looking-glass-client-dev-01.log"

        first = launch(home, "dev-01", "first", str(state))
        require(first.returncode == 0, f"the redirect failed: {first.stderr}")
        require(first.stdout == "", f"the client's output still reached its caller: {first.stdout!r}")
        require(first.stderr == f"HyperLab: Looking Glass client output: {log}\n",
                f"the caller is not told where the client's output goes: {first.stderr!r}")
        text = log.read_text()
        require(text.startswith("HyperLab: looking-glass-client for dev-01 started ")
                and "client-out first\n" in text and "client-err\n" in text,
                f"the log does not hold the client's output: {text!r}")
        require(stat.S_IMODE(log.stat().st_mode) == 0o600, "the client log is not 0600")
        require(stat.S_IMODE(log.parent.stat().st_mode) == 0o700, "the state directory was not made 0700")

        log.chmod(0o644)
        second = launch(home, "dev-01", "second", str(state))
        text = log.read_text()
        require(second.returncode == 0 and "client-out second" in text and "first" not in text,
                f"the log was not replaced at the next start: {text!r}")
        require(stat.S_IMODE(log.stat().st_mode) == 0o600, "a pre-existing log kept its looser mode")

        fallback = launch(home, "dev-01", "fallback", "relative/state")
        default = home / ".local/state/hyperlab/looking-glass-client-dev-01.log"
        require(fallback.returncode == 0 and "client-out fallback" in default.read_text(),
                "a relative XDG_STATE_HOME was not ignored for ~/.local/state")

        target = home / "elsewhere"
        target.write_text("keep\n")
        log.unlink()
        log.symlink_to(target)
        linked = launch(home, "dev-01", "linked", str(state))
        require(linked.returncode == 3 and target.read_text() == "keep\n",
                f"a symlinked log was followed: {linked.stderr!r}")

        log.unlink()
        os.mkfifo(log)
        fifo = launch(home, "dev-01", "fifo", str(state))
        require(fifo.returncode == 3, f"a FIFO in place of the log was accepted: {fifo.stderr!r}")

        for domain in ("../escape", ".hidden", "a/b", ""):
            bad = launch(home, domain, "bad", str(state))
            require(bad.returncode == 3, f"the domain name {domain!r} was used in a file name")
        require(not (home / "escape").exists() and not (state / "escape").exists(),
                "a domain name wrote outside the state directory")


def main() -> int:
    check_order()
    check_behaviour()
    print("Looking Glass client log contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
