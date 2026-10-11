#!/usr/bin/env python3
"""Group 16's still and changing phases, judged from the sender's own log.

The operator's criterion (2026-10-11):

  * the same sender (one pid) runs the still and the changing phase, and
    from the start of the still phase its log has no "restarting the
    capture" and no "Capture Stop" (a sender started with no client logs a
    Capture Stop at once; that one is before the phase and does not count);
  * still phase, timed by the script, at least 5 minutes: "No usable frame"
    warnings are allowed and counted;
  * changing phase: no "No usable frame", and when a warning was active as
    the screen started changing, "Frames resumed" within 2 s of the first
    change. Without an active warning the frames were already arriving. A
    warning logged in the changing phase about a silence that began before
    it (10 s after the last still frame) belongs to the still phase.

Every time is read inside dev-01 as seconds since that sender started, the
clock of its log lines (/proc/uptime against the process start): no wall
clock, and no host clock, is involved.

The change is temporary and leaves nothing behind: Hyprland notifications
that show dev-01's time, one a second for 30 s, each closing by itself after
0.9 s. The loop ends by itself; on any exit, an interruption or a dropped
connection included, the script dismisses what is still shown and says when.
Nothing is installed or changed in dev-01.

  sender_phases.py mark|change|log   print the script to run inside dev-01
  sender_phases.py judge --start F --end F --change F --log F
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

STILL_SECONDS = 300.0
RESUME_SECONDS = 2.0
SENDER = r"^/usr/local/bin/looking-glass-host([[:space:]]|$)"

# Seconds since the running sender started, on the clock of its log lines.
ELAPSED = r"""sender_pid() { pgrep -u "$(id -u)" -f '%s' | head -n 1; }
elapsed() {
    p=$(sender_pid)
    [ -n "$p" ] || { echo none; return; }
    ticks=$(sed 's/.*) //' "/proc/$p/stat" | cut -d' ' -f20)
    awk -v t="$ticks" -v hz="$(getconf CLK_TCK)" '{ printf "%%.3f\n", $1 - t / hz }' /proc/uptime
}
""" % SENDER

MARK = "# sender_phases: mark\n" + ELAPSED + r"""echo "pid=$(sender_pid)"
echo "elapsed=$(elapsed)"
"""

CHANGE = "# sender_phases: change\n" + ELAPSED + r"""uid=$(id -u)
export XDG_RUNTIME_DIR="/run/user/$uid"
sig=$(systemctl --user show-environment 2>/dev/null | sed -n 's/^HYPRLAND_INSTANCE_SIGNATURE=//p')
[ -n "$sig" ] || sig=$(ls -t "$XDG_RUNTIME_DIR/hypr" 2>/dev/null | head -n 1)
export HYPRLAND_INSTANCE_SIGNATURE="$sig"
echo "pid=$(sender_pid)"
focused=$(timeout 5 hyprctl monitors 2>/dev/null | awk '/^Monitor /{m=$2} /focused:/{if (m=="HEADLESS-0") print $2}')
echo "focused=${focused:-unknown}"
[ "$focused" = yes ] || exit 0
closed=0
close_all() {
    [ "$closed" = 1 ] && return
    closed=1
    timeout 5 hyprctl dismissnotify >/dev/null 2>&1
    echo "dismissed_rc=$?"
    echo "closed_at=$(elapsed)"
}
trap close_all EXIT
trap 'close_all; exit 1' INT TERM HUP
echo "opened=30 Hyprland notifications showing dev-01's time, one a second, each closing by itself after 0.9 s"
echo "change_from=$(elapsed)"
failures=0
i=0
while [ "$i" -lt 30 ]; do
    out=$(timeout 5 hyprctl notify -1 900 "rgb(88c0d0)" "HyperLab group 16: $(date +%T)" 2>&1)
    [ "$out" = ok ] || failures=$((failures + 1))
    sleep 1
    i=$((i + 1))
done
echo "change_to=$(elapsed)"
echo "notify_failures=$failures"
"""

LOG = "# sender_phases: log\n" + ELAPSED + r"""echo "pid=$(sender_pid)"
log="$HOME/.local/state/hyperlab/looking-glass-host.log"
grep -E 'Capture Start|Capture Stop|No usable frame|Frames resumed|restarting the capture' "$log" 2>/dev/null \
    | sed 's/^/line=/'
"""

_TIME = re.compile(r"^(\d+):(\d{2}):(\d{2})\.(\d{3}) ")


def fields(text: str) -> dict[str, str]:
    values = {}
    for raw in text.splitlines():
        key, sep, value = raw.strip().partition("=")
        if sep and re.fullmatch(r"[a-z_]+", key) and key != "line":
            values[key] = value
    return values


def number(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def events(text: str) -> list[tuple[float, str]]:
    """(seconds since the sender started, line) for every log line kept."""
    found = []
    for raw in text.splitlines():
        if not raw.startswith("line="):
            continue
        line = raw[len("line="):]
        stamp = _TIME.match(line)
        if stamp is not None:
            hours, minutes, seconds, millis = (int(part) for part in stamp.groups())
            found.append((hours * 3600 + minutes * 60 + seconds + millis / 1000, line))
    return found


def judge(start: dict[str, str], end: dict[str, str], change: dict[str, str], after: dict[str, str],
          log: list[tuple[float, str]]) -> tuple[list[tuple[bool, str]], list[str]]:
    findings, notes = [], []
    pids = [start.get("pid", ""), end.get("pid", ""), change.get("pid", ""), after.get("pid", "")]
    findings.append((pids[0].isdigit() and len(set(pids)) == 1,
                     f"the same sender ran both phases (pids {', '.join(p or 'none' for p in pids)})"))

    findings.append((change.get("focused") == "yes",
                     f"HEADLESS-0, the captured output, was focused ({change.get('focused') or 'unread'})"))
    findings.append((change.get("notify_failures") == "0",
                     f"every notification was shown (failures: {change.get('notify_failures') or 'unread'})"))
    closed = change.get("closed_at")
    findings.append((number(closed) is not None,
                     f"the notifications were closed (at {closed or 'never'} s, "
                     f"dismiss exit {change.get('dismissed_rc') or 'unread'})"))
    notes.append(f"opened in dev-01: {change.get('opened') or 'nothing'}; closed at {closed or 'never'} s")

    still_from, still_to = number(start.get("elapsed")), number(end.get("elapsed"))
    change_from, change_to = number(change.get("change_from")), number(change.get("change_to"))
    if None in (still_from, still_to, change_from, change_to):
        findings.append((False, "the phase times were not all read in dev-01"))
        return findings, notes
    findings.append((still_to - still_from >= STILL_SECONDS,
                     f"the still phase lasted {still_to - still_from:.1f} s (at least {STILL_SECONDS:.0f} s)"))

    since_still = [(time, line) for time, line in log if time >= still_from]
    restarts = [line for _, line in since_still if "restarting the capture" in line]
    stops = [line for _, line in since_still if "Capture Stop" in line]
    findings.append((not restarts, f"no capture restart since the still phase began ({len(restarts)})"))
    findings.append((not stops, f"no Capture Stop since the still phase began ({len(stops)})"))

    def silent_since(time: float, line: str) -> float:
        said = re.search(r"No usable frame for (\d+) s", line)
        return time - int(said.group(1)) if said else time

    warnings = [(time, line) for time, line in log if "No usable frame" in line]
    still_warnings = [line for time, line in warnings
                      if still_from <= time and silent_since(time, line) < change_from]
    notes.append(f"'No usable frame' warnings in the still phase: {len(still_warnings)} (allowed)")
    changing_warnings = [line for time, line in warnings if change_from <= time <= change_to
                         and silent_since(time, line) >= change_from]
    findings.append((not changing_warnings,
                     f"no 'No usable frame' while the screen changed ({len(changing_warnings)})"))

    active = False
    for time, line in log:
        if "No usable frame" in line and silent_since(time, line) < change_from:
            active = True
        elif time >= change_from:
            break
        elif "Frames resumed" in line or "Capture Start" in line:
            active = False
    if active:
        resumed = [time for time, line in log if time >= change_from and "Frames resumed" in line]
        delay = resumed[0] - change_from if resumed else None
        findings.append((delay is not None and delay <= RESUME_SECONDS,
                         "frames resumed within %.0f s of the first change (%s)"
                         % (RESUME_SECONDS, "never" if delay is None else "%.2f s" % delay)))
    else:
        notes.append("no warning was active at the first change: frames were already arriving")
    return findings, notes


def main(argv: list[str]) -> int:
    if len(argv) == 1 and argv[0] in ("mark", "change", "log"):
        print({"mark": MARK, "change": CHANGE, "log": LOG}[argv[0]], end="")
        return 0
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["judge"])
    for name in ("start", "end", "change", "log"):
        parser.add_argument(f"--{name}", required=True)
    args = parser.parse_args(argv)
    read = {name: Path(getattr(args, name)).read_text() for name in ("start", "end", "change", "log")}
    findings, notes = judge(fields(read["start"]), fields(read["end"]), fields(read["change"]),
                            fields(read["log"]), events(read["log"]))
    for ok, text in findings:
        print(("ok    " if ok else "WRONG ") + text)
    for text in notes:
        print("note  " + text)
    return 0 if all(ok for ok, _ in findings) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
