#!/usr/bin/env python3
"""Is the Looking Glass sender running in a Machine the one this test built?

Reads, on standard input, what PROBE printed inside the Machine, and judges
it against the repository, never against what the Machine claims:

  * a sender is running, and it is a new process when --not-pid names the
    one before (and the same process when --pid names it);
  * its build stamp carries the reviewed patch digests and source commit of
    roles/guest_looking_glass_linux, and a binary digest, without which it
    is "rebuild needed";
  * the running executable (/proc/PID/exe) has that binary digest;
  * its log starts with "HyperLab: sender started <time>" at or after
    --since, so the log read belongs to this sender;
  * with --no-restart, that log holds no capture restart ("restarting the
    capture"). "No usable frame" warnings are counted, not judged: a still
    desktop probably sends no frame (problems/looking-glass-sender-hung-after-capture-stop.md).

Prints one line per finding and exits 0 only when every one holds.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULTS = ROOT / "roles/guest_looking_glass_linux/defaults/main.yml"
SHARED = ROOT / "group_vars/all/looking-glass.yml"

# Run inside the Machine as its graphical user. It only reads.
PROBE = r"""pid=$(pgrep -u "$(id -u)" -f '^/usr/local/bin/looking-glass-host([[:space:]]|$)' | head -n 1)
echo "pid=${pid:-none}"
if [ -n "$pid" ]; then echo "exe_sha256=$(sha256sum "/proc/$pid/exe" | cut -d' ' -f1)"; fi
sed -n 's/^\([a-z_0-9]*\): *\(.*\)$/stamp.\1=\2/p' /usr/local/share/looking-glass-linux-host/built-from.yml 2>/dev/null
echo
log="$HOME/.local/state/hyperlab/looking-glass-host.log"
head -n 1 "$log" 2>/dev/null | sed -n 's/^HyperLab: sender started \([^ ]*\).*/started=\1/p'
echo "no_usable_frame=$(grep -c 'No usable frame' "$log" 2>/dev/null || true)"
echo "capture_restarts=$(grep -c 'restarting the capture' "$log" 2>/dev/null || true)"
"""


def parse(text: str) -> dict[str, str]:
    found = {}
    for line in text.splitlines():
        match = re.fullmatch(r"\s*([a-z_.0-9]+)=(.*)", line)
        if match:
            found[match.group(1)] = match.group(2).strip()
    return found


def expected() -> dict[str, str]:
    defaults = yaml.safe_load(DEFAULTS.read_text())
    shared = yaml.safe_load(SHARED.read_text())
    # The role pins the sender to the host client's source commit.
    if defaults["guest_looking_glass_linux_commit"] != "{{ hyperlab_looking_glass_commit }}":
        raise SystemExit("the sender's commit is no longer the shared pin; update sender_identity.py")
    return {
        "commit": str(shared["hyperlab_looking_glass_commit"]),
        "compat_patch_sha256": str(defaults["guest_looking_glass_linux_compat_patch_sha256"]),
        "runtime_patch_sha256": str(defaults["guest_looking_glass_linux_runtime_patch_sha256"]),
    }


def judge(probe: dict[str, str], want: dict[str, str], since: float, not_pid: str | None = None,
          pid: str | None = None, no_restart: bool = False) -> list[tuple[bool, str]]:
    findings = []
    running = probe.get("pid", "none")
    findings.append((running.isdigit(), f"a sender is running (pid {running})"))
    if not_pid is not None:
        findings.append((running.isdigit() and running != not_pid,
                         f"it is a new process (was {not_pid}, now {running})"))
    if pid is not None:
        findings.append((running == pid, f"it is still the same process (expected {pid}, now {running})"))
    for key, value in want.items():
        have = probe.get(f"stamp.{key}", "")
        findings.append((have == value, f"stamp {key} is the repository's ({have or 'absent'})"))
    binary = probe.get("stamp.binary_sha256", "")
    if not re.fullmatch(r"[0-9a-f]{64}", binary):
        findings.append((False, "rebuild needed: the stamp has no binary digest"))
    else:
        exe = probe.get("exe_sha256", "")
        findings.append((exe == binary, f"the running executable is the stamped binary ({exe or 'unread'})"))
    started = probe.get("started", "")
    try:
        when = datetime.fromisoformat(started).timestamp()
    except ValueError:
        findings.append((False, f"the log does not start with this sender's start line ({started or 'absent'})"))
    else:
        findings.append((when >= since, f"the log's sender started at {started}, after the test began"))
    if no_restart:
        restarts = probe.get("capture_restarts", "")
        findings.append((restarts == "0", f"no capture restart in this sender's log ({restarts or 'unread'})"))
    return findings


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", type=float, required=True, help="epoch seconds the test step began")
    parser.add_argument("--not-pid")
    parser.add_argument("--pid")
    parser.add_argument("--no-restart", action="store_true")
    parser.add_argument("--input", help="the probe's output; standard input when absent")
    parser.add_argument("--print-probe", action="store_true", help="print the probe to run in the Machine")
    if "--print-probe" in argv:
        print(PROBE, end="")
        return 0
    args = parser.parse_args(argv)
    text = Path(args.input).read_text() if args.input else sys.stdin.read()
    probe = parse(text)
    findings = judge(probe, expected(), args.since, args.not_pid, args.pid, args.no_restart)
    for ok, text in findings:
        print(("ok    " if ok else "WRONG ") + text)
    if args.no_restart:
        print("note  'No usable frame' warnings in this sender's log: %s (counted, allowed on a still desktop)"
              % (probe.get("no_usable_frame") or "unread"))
    return 0 if all(ok for ok, _ in findings) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
