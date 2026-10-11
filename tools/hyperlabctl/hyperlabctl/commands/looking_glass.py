"""Whether a Linux Machine's Looking Glass stream is alive, and restarting
its capture without restarting the Machine (ADR 0045).

`health` answers three things, each from its own authority: whether the
guest agent answers (from the host, `guest-ping`), whether the sender runs,
and what the sender last said about its stream, read from its own log over
the pinned SSH channel. The sender logs once when 10 s pass without a
frame (problems/looking-glass-sender-streaming-without-frames.md). That
silence is information, not a failure: a still desktop probably sends no frame, and
restarting on silence hung the sender
(problems/looking-glass-sender-hung-after-capture-stop.md). `health`
reports how long the stream has been silent, from the sender's start time,
the log line and the guest's own clock. The sender restarts its capture
only when the stream or the core fails; `stalled` names a restart that did
not end with a new capture.

`restart-capture` stops the sender, restarts the guest's screen-cast
portals and starts the sender again through the same path `open
looking-glass` uses. The client on the host reconnects by itself. Before it
stops the sender it appends the state of every sender thread to the
sender's log (kept as .1 when the sender starts again): a sender that hung
can then be told apart afterwards
(problems/looking-glass-sender-hung-after-capture-stop.md).
"""

import json
import re
import subprocess
from datetime import datetime, timezone

from ..errors import Unavailable
from .base import Command
from .open import (
    _executable,
    _looking_glass_transport,
    _prepare_linux_looking_glass,
    _require_running_vfio,
    _ssh_argv,
    _wait_for_ssh_ready,
)

# Anchored on the program path: an unanchored `pkill -f looking-glass-host`
# also matches a shell whose own command line holds that text, and ended the
# recovery command that ran it.
SENDER_PATTERN = r"^/usr/local/bin/looking-glass-host([[:space:]]|$)"
LOG = "$HOME/.local/state/hyperlab/looking-glass-host.log"
LOG_LINES = 40

PROBE = r"""set -u
uid="$(id -u)"
log="%(log)s"
if pgrep -u "$uid" -f '%(pattern)s' >/dev/null 2>&1; then
    echo "sender=running"
else
    echo "sender=absent"
fi
if [[ -f "$log" ]]; then
    echo "now=$(date +%%s)"
    echo "log_age=$(( $(date +%%s) - $(stat -c %%Y "$log") ))"
    sed -n '1s/^HyperLab: sender started \([^ ]*\) .*/started=\1/p' "$log"
    grep -E 'Capture Start|Capture Stop|stream state change|No usable frame|Frames resumed|restarting the capture|^HyperLab: ' \
        "$log" | tail -n %(lines)d | sed 's/^/line=/'
else
    echo "log=absent"
fi
""" % {"log": LOG, "pattern": SENDER_PATTERN, "lines": LOG_LINES}

STOP = r"""set -u
uid="$(id -u)"
export XDG_RUNTIME_DIR="/run/user/$uid"
export DBUS_SESSION_BUS_ADDRESS="unix:path=$XDG_RUNTIME_DIR/bus"
pattern='%(pattern)s'
log="%(log)s"
# Where each thread waits, before the sender is gone: in wchan a futex (a
# join or a lock), a poll (the portal) or a sleep (no client) tell a hang
# apart. The system call needs ptrace rights and usually reads "?".
for pid in $(pgrep -u "$uid" -f "$pattern"); do
    {
        printf 'HyperLab: threads of sender %%s before restart-capture at %%s\n' \
            "$pid" "$(date --iso-8601=seconds)"
        for task in /proc/"$pid"/task/*; do
            [[ -d "$task" ]] || continue
            state="$(sed 's/.*) //' "$task/stat" 2>/dev/null | cut -d' ' -f1)"
            printf 'HyperLab: thread %%s %%s state=%%s wchan=%%s syscall=%%s\n' \
                "${task##*/}" \
                "$(cat "$task/comm" 2>/dev/null || echo '?')" \
                "${state:-?}" \
                "$(cat "$task/wchan" 2>/dev/null || echo '?')" \
                "$(cut -d' ' -f1 "$task/syscall" 2>/dev/null || echo '?')"
        done
    } >>"$log" 2>/dev/null || true
done
pkill -TERM -u "$uid" -f "$pattern" || true
for _ in $(seq 1 50); do
    pgrep -u "$uid" -f "$pattern" >/dev/null 2>&1 || break
    sleep 0.1
done
if pgrep -u "$uid" -f "$pattern" >/dev/null 2>&1; then
    echo "REFUSAL: the sender did not stop" >&2
    exit 1
fi
systemctl --user restart xdg-desktop-portal-hyprland.service xdg-desktop-portal.service || {
    echo "REFUSAL: the screen-cast portals did not restart" >&2
    exit 1
}
""" % {"pattern": SENDER_PATTERN, "log": LOG}

_STATE_RE = re.compile(r"stream state change: \S+ -> (\S+)")
_ELAPSED_RE = re.compile(r"^(\d+):(\d{2}):(\d{2})\.(\d{3}) ")
_SILENCE_RE = re.compile(r"No usable frame for (\d+) s while streaming")


def stream_state(lines):
    """The stream state the sender's log last reported, oldest line first."""
    state = "unknown"
    for line in lines:
        if "Capture Start" in line:
            state = "starting"
        elif "Capture Stop" in line:
            state = "idle"
        elif "Frames resumed" in line:
            state = "streaming"
        elif "restarting the capture" in line:
            state = "restarting"
        elif "No usable frame" in line:
            # A silent stream is still streaming (silent_since says since when).
            continue
        elif line.startswith("HyperLab: ") and ("exited" in line or "is gone" in line):
            state = "stopped"
        else:
            match = _STATE_RE.search(line)
            if match is not None and state not in ("idle", "stopped"):
                state = "streaming" if match.group(1) == "streaming" else "starting"
    return state


def silent_since(lines):
    """Seconds after the sender's start when its stream last went silent, or
    None when a frame, a new capture or a restart came after that."""
    since = None
    for line in lines:
        silence = _SILENCE_RE.search(line)
        elapsed = _ELAPSED_RE.match(line)
        if silence is not None and elapsed is not None:
            hours, minutes, secs, millis = (int(part) for part in elapsed.groups())
            since = hours * 3600 + minutes * 60 + secs + millis / 1000 - int(silence.group(1))
        elif any(word in line for word in ("Frames resumed", "Capture Start", "Capture Stop",
                                           "restarting the capture")):
            since = None
    return since


def no_frame_seconds(lines, started, now):
    """How long a streaming sender has had no new frame, on the guest's clock;
    None when it is not silent or the times are not known."""
    since = silent_since(lines)
    if since is None or started is None or now is None or stream_state(lines) != "streaming":
        return None
    return max(0, int(now - (started + since)))


def _epoch(value):
    try:
        return datetime.fromisoformat(value).timestamp()
    except ValueError:
        return None


def parse_probe(text):
    sender, age, lines, log, started, now = None, None, [], True, None, None
    for raw in text.splitlines():
        key, _, value = raw.partition("=")
        if key == "sender" and value in ("running", "absent"):
            sender = value
        elif key == "log_age" and re.fullmatch(r"-?[0-9]+", value):
            age = max(0, int(value))
        elif key == "now" and re.fullmatch(r"[0-9]+", value):
            now = int(value)
        elif key == "started":
            started = _epoch(value)
        elif key == "log" and value == "absent":
            log = False
        elif key == "line":
            lines.append(value)
    if sender is None:
        raise Unavailable("the guest did not report its sender")
    return {"sender": sender, "log_age_seconds": age, "log": log,
            "stream": stream_state(lines) if log else "unknown",
            "no_frame_seconds": no_frame_seconds(lines, started, now) if log else None}


def verdict(agent, sender, stream):
    """One word for the shell. Every input is a fact, never a guess."""
    if agent is not True:
        return "guest-unresponsive"
    if sender != "running":
        return "sender-down"
    if stream in ("stalled", "restarting"):
        return "stalled"
    if stream == "streaming":
        return "ok"
    if stream == "idle":
        return "idle"
    return "starting" if stream == "starting" else "unknown"


def agent_answers(domain, run=subprocess.run):
    try:
        result = run([_executable("virsh"), "--connect", "qemu:///system", "qemu-agent-command",
                      domain, '{"execute":"guest-ping"}', "--timeout", "5"],
                     capture_output=True, text=True, timeout=10, check=False)
    except subprocess.TimeoutExpired:
        return False
    if result.returncode != 0:
        return False
    try:
        return json.loads(result.stdout).get("return") == {}
    except (json.JSONDecodeError, AttributeError):
        return False


def _require_linux_stream(ctx, domain):
    _require_running_vfio(ctx, domain)
    if _looking_glass_transport(ctx, domain) != "linux-experimental":
        raise Unavailable("stream health covers Linux Looking Glass guests only")


def _remote(ctx, domain, script, timeout, run=subprocess.run):
    ssh_argv = _ssh_argv(ctx, domain)
    _wait_for_ssh_ready(ssh_argv, domain)
    try:
        return run([*ssh_argv, "bash", "-s"], input=script, text=True,
                   capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise Unavailable("%s did not answer in time" % domain) from exc


def health(ctx, domain, run=subprocess.run):
    _require_linux_stream(ctx, domain)
    agent = agent_answers(domain, run)
    result = _remote(ctx, domain, PROBE, 15, run)
    if result.returncode != 0:
        raise Unavailable("%s did not report its sender: %s"
                          % (domain, (result.stderr.strip() or "exit %d" % result.returncode)[-300:]))
    probe = parse_probe(result.stdout)
    return {
        "machine": domain,
        "agent": "yes" if agent else "no",
        "sender": probe["sender"],
        "stream": probe["stream"],
        "log_age_seconds": probe["log_age_seconds"],
        "no_frame_seconds": probe["no_frame_seconds"],
        "health": verdict(agent, probe["sender"], probe["stream"]),
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def restart_capture(ctx, domain, run=subprocess.run, prepare=_prepare_linux_looking_glass):
    _require_linux_stream(ctx, domain)
    if not agent_answers(domain, run):
        raise Unavailable("%s does not answer its guest agent; restarting the capture "
                          "would not help" % domain)
    result = _remote(ctx, domain, STOP, 30, run)
    if result.returncode != 0:
        raise Unavailable("%s: %s" % (domain, (result.stderr.strip() or "exit %d" % result.returncode)[-300:]))
    if not prepare(ctx, domain):
        raise Unavailable("%s has no graphical session to capture" % domain)
    return {"machine": domain, "phase": "restarted"}


class LookingGlassCommand(Command):
    name = "looking-glass"
    help = "check a Linux Machine's Looking Glass stream, or restart its capture"
    order = 24

    def configure(self, parser):
        sub = parser.add_subparsers(dest="looking_glass_action", required=True)
        for action, text in (("health", "report the guest agent, sender and stream state"),
                             ("restart-capture", "restart the sender and the screen-cast portals")):
            target = sub.add_parser(action, help=text)
            target.add_argument("domain")

    def run(self, args, ctx):
        if args.looking_glass_action == "health":
            report = health(ctx, args.domain)
        else:
            report = restart_capture(ctx, args.domain)
        if args.json:
            print(json.dumps(report, separators=(",", ":")))
        elif args.looking_glass_action == "health":
            silence = report["no_frame_seconds"]
            print("%(machine)s: %(health)s (agent %(agent)s, sender %(sender)s, stream %(stream)s" % report
                  + (", no new frame for %d s)" % silence if silence is not None else ")"))
        else:
            print("%s: capture restarted" % args.domain)
        return 0
