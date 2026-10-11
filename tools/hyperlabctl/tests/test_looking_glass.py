"""Looking Glass stream health and capture restart (ADR 0045)."""

import json
import re
import subprocess
from types import SimpleNamespace

from harness import check, equals
from hyperlabctl.commands import looking_glass as lg
from hyperlabctl.errors import Unavailable

# The sender log of the freeze on dev-01 (2026-10-04), as its filter keeps it.
FROZEN = [
    "00:00:00.043 [I] pipewire.c:231 | streamStateChangedCallback | PipeWire stream state change: unconnected -> connecting",
    "00:00:00.044 [I] pipewire.c:231 | streamStateChangedCallback | PipeWire stream state change: connecting -> paused",
    "00:00:00.052 [I] app.c:451 | captureStart | ==== [ Capture Start ] ====",
    "00:00:00.058 [I] app.c:461 | captureStop | ==== [ Capture Stop ] ====",
    "00:00:00.058 [I] pipewire.c:231 | streamStateChangedCallback | PipeWire stream state change: paused -> streaming",
    "00:00:00.058 [I] pipewire.c:231 | streamStateChangedCallback | PipeWire stream state change: streaming -> paused",
    "00:00:00.059 [I] pipewire.c:231 | streamStateChangedCallback | PipeWire stream state change: paused -> unconnected",
    "00:15:51.960 [I] pipewire.c:231 | streamStateChangedCallback | PipeWire stream state change: unconnected -> connecting",
    "00:15:51.961 [I] pipewire.c:231 | streamStateChangedCallback | PipeWire stream state change: connecting -> paused",
    "00:15:51.976 [I] app.c:451 | captureStart | ==== [ Capture Start ] ====",
    "00:15:51.983 [I] pipewire.c:231 | streamStateChangedCallback | PipeWire stream state change: paused -> streaming",
]
WARN = "01:00:02.000 [W] pipewire.c:470 | pipewire_capture | No usable frame for 10 s while streaming: 0 process callbacks, 0 empty buffers since the last frame"
RESTART = "01:00:22.000 [W] pipewire.c:478 | pipewire_capture | No usable frame for 30 s: restarting the capture (0 process callbacks, 0 empty buffers)"
RESUMED = "01:00:15.000 [I] pipewire.c:150 | streamProcessCallback | Frames resumed after 13 s without a usable frame"


def test_the_old_sender_log_could_not_show_the_freeze():
    # Why the patch logs a stall: without that line the frozen stream reads
    # as streaming.
    equals("frozen_log_reads_streaming", lg.stream_state(FROZEN), "streaming")


def test_silence_is_not_a_stream_state_but_a_restart_is():
    # A still desktop probably sends no frame: the warning does not change the state
    # (problems/looking-glass-sender-hung-after-capture-stop.md).
    equals("warned", lg.stream_state(FROZEN + [WARN]), "streaming")
    equals("resumed", lg.stream_state(FROZEN + [WARN, RESUMED]), "streaming")
    equals("old_sender_restarting", lg.stream_state(FROZEN + [WARN, RESTART]), "restarting")
    failed = "01:00:23.000 [W] pipewire.c:562 | pipewire_capture | The PipeWire stream failed: restarting the capture"
    equals("failed_stream_restarting", lg.stream_state(FROZEN + [failed]), "restarting")
    stop = "01:00:22.001 [I] app.c:461 | captureStop | ==== [ Capture Stop ] ===="
    start = "01:00:22.300 [I] app.c:451 | captureStart | ==== [ Capture Start ] ===="
    flowing = "01:00:22.310 [I] pipewire.c:231 | x | PipeWire stream state change: paused -> streaming"
    equals("restarted", lg.stream_state(FROZEN + [WARN, RESTART, stop, start, flowing]), "streaming")
    equals("idle_after_stop", lg.stream_state(FROZEN + [stop, "PipeWire stream state change: streaming -> paused"]),
           "idle")
    equals("supervisor_saw_the_sender_exit",
           lg.stream_state(FROZEN + ["HyperLab: sender exited with status 0 at 2026-10-05T20:50:37+02:00"]),
           "stopped")
    equals("nothing_known", lg.stream_state([]), "unknown")


def test_the_verdict_never_blames_the_stream_for_a_dead_guest():
    equals("ok", lg.verdict(True, "running", "streaming"), "ok")
    equals("stalled", lg.verdict(True, "running", "stalled"), "stalled")
    equals("restarting", lg.verdict(True, "running", "restarting"), "stalled")
    equals("sender_down", lg.verdict(True, "absent", "streaming"), "sender-down")
    equals("idle", lg.verdict(True, "running", "idle"), "idle")
    equals("agent_no", lg.verdict(False, "running", "stalled"), "guest-unresponsive")
    equals("agent_unknown", lg.verdict(None, "running", "streaming"), "guest-unresponsive")


def test_the_silence_is_measured_on_the_guest_clock_from_the_warning():
    # The warning at 01:00:02 elapsed says 10 s without a frame: silent since
    # 00:59:52 after the start, so 1 h 10 min after the start it is 608 s.
    started = "2026-10-07T14:02:17+02:00"
    now = int(lg._epoch(started)) + 3600 + 600
    probe = "sender=running\nnow=%d\nlog_age=1\nstarted=%s\n" % (now, started)
    parsed = lg.parse_probe(probe + "".join("line=%s\n" % line for line in FROZEN + [WARN]))
    equals("silent_stream", (parsed["stream"], parsed["no_frame_seconds"]), ("streaming", 608))
    equals("silent_stream_is_ok", lg.verdict(True, parsed["sender"], parsed["stream"]), "ok")
    resumed = lg.parse_probe(probe + "".join("line=%s\n" % line for line in FROZEN + [WARN, RESUMED]))
    equals("frames_resumed", resumed["no_frame_seconds"], None)
    no_clock = lg.parse_probe("sender=running\n" + "".join("line=%s\n" % line for line in FROZEN + [WARN]))
    equals("no_guest_clock_no_number", no_clock["no_frame_seconds"], None)
    restarted = lg.parse_probe(probe + "".join("line=%s\n" % line for line in FROZEN + [WARN, RESTART]))
    equals("restarting_is_not_silence", (restarted["stream"], restarted["no_frame_seconds"]),
           ("restarting", None))


def test_the_probe_answer_is_parsed_strictly():
    parsed = lg.parse_probe("sender=running\nlog_age=12\n" + "".join("line=%s\n" % line for line in FROZEN + [WARN]))
    equals("probe", parsed, {"sender": "running", "log_age_seconds": 12, "log": True, "stream": "streaming",
                             "no_frame_seconds": None})
    equals("no_log", lg.parse_probe("sender=absent\nlog=absent\n")["stream"], "unknown")
    try:
        lg.parse_probe("sender=maybe\n")
        check("unknown_sender_refused", False)
    except Unavailable:
        check("unknown_sender_refused", True)


def test_the_sender_pattern_cannot_match_the_shell_that_runs_it():
    # pgrep's [[:space:]] is Python's \s here.
    pattern = re.compile(lg.SENDER_PATTERN.replace("[[:space:]]", r"\s"))
    check("matches_the_sender", pattern.search("/usr/local/bin/looking-glass-host") is not None)
    check("matches_the_sender_with_args", pattern.search("/usr/local/bin/looking-glass-host -f x") is not None)
    shell = "bash -c pkill -f looking-glass-host; systemctl --user restart xdg-desktop-portal-hyprland.service"
    check("unanchored_pattern_matched_its_own_shell", re.search("looking-glass-host", shell) is not None)
    check("anchored_pattern_spares_the_shell", pattern.search(shell) is None)
    check("anchored_pattern_spares_bash_s", pattern.search("bash -s") is None)
    check("stop_script_uses_the_anchored_pattern", "pattern='%s'" % lg.SENDER_PATTERN in lg.STOP)
    check("stop_script_has_no_unanchored_pkill", "pkill -f looking-glass-host" not in lg.STOP)


class _Fakes:
    def __init__(self, agent=True, stop_rc=0, probe="sender=running\nlog=absent\n"):
        self.calls = []
        self.agent = agent
        self.stop_rc = stop_rc
        self.probe = probe

    def run(self, argv, **kwargs):
        self.calls.append(argv)
        if "qemu-agent-command" in argv:
            return SimpleNamespace(returncode=0 if self.agent else 1,
                                   stdout=json.dumps({"return": {}}) if self.agent else "", stderr="")
        script = kwargs.get("input", "")
        if script == lg.STOP:
            return SimpleNamespace(returncode=self.stop_rc, stdout="", stderr="REFUSAL: x" if self.stop_rc else "")
        return SimpleNamespace(returncode=0, stdout=self.probe, stderr="")


def _patched(fakes, transport="linux-experimental"):
    saved = {name: getattr(lg, name) for name in
             ("_require_running_vfio", "_looking_glass_transport", "_ssh_argv", "_wait_for_ssh_ready", "_executable")}
    lg._require_running_vfio = lambda ctx, domain: None
    lg._looking_glass_transport = lambda ctx, domain: transport
    lg._ssh_argv = lambda ctx, domain: ["ssh", domain]
    lg._wait_for_ssh_ready = lambda argv, domain: None
    lg._executable = lambda name: name
    return saved


def _restore(saved):
    for name, value in saved.items():
        setattr(lg, name, value)


def test_restart_stops_the_sender_and_portals_before_starting_it_again():
    fakes = _Fakes()
    order = []
    saved = _patched(fakes)
    try:
        def prepare(ctx, domain):
            order.append(("prepare", len(fakes.calls)))
            return True
        result = lg.restart_capture(None, "dev-01", run=fakes.run, prepare=prepare)
    finally:
        _restore(saved)
    equals("restarted", result, {"machine": "dev-01", "phase": "restarted"})
    scripts = [call for call in fakes.calls if call[:2] == ["ssh", "dev-01"]]
    equals("one_stop_script", len(scripts), 1)
    check("prepare_after_stop", order == [("prepare", len(fakes.calls))])


def test_restart_records_the_sender_threads_before_stopping_it():
    # A sender that hung (problems/looking-glass-sender-hung-after-capture-stop.md)
    # can only be told apart while it still runs: the stop script appends
    # where each of its threads waits to its log, then stops it. Run here
    # with a real process standing in for the sender and fake pgrep, pkill
    # and systemctl.
    import os
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="hyperlabctl-stop-") as tmp:
        home = Path(tmp) / "home"
        (home / ".local/state/hyperlab").mkdir(parents=True)
        log = home / ".local/state/hyperlab/looking-glass-host.log"
        log.write_text("HyperLab: sender started 2026-10-07T14:02:17+02:00 for Hyprland x\n")
        sender = subprocess.Popen(["sleep", "60"])
        fakes = Path(tmp) / "bin"
        fakes.mkdir()
        for name, body in (
                # A killed child stays a zombie until this test reaps it: not running.
                ("pgrep", 'grep -qv "^[0-9]* ([^)]*) Z" /proc/%d/stat 2>/dev/null || exit 1\necho %d\n'
                 % (sender.pid, sender.pid)),
                ("pkill", 'kill %d 2>/dev/null\nexit 0\n' % sender.pid),
                ("systemctl", "exit 0\n")):
            (fakes / name).write_text("#!/bin/bash\n" + body)
            (fakes / name).chmod(0o755)
        try:
            env = dict(os.environ, HOME=str(home), PATH="%s:%s" % (fakes, os.environ["PATH"]))
            done = subprocess.run(["bash", "-s"], input=lg.STOP, text=True, capture_output=True,
                                  env=env, timeout=30, check=False)
        finally:
            sender.kill()
            sender.wait()
        text = log.read_text()
    equals("stop_script_exit", done.returncode, 0)
    check("threads_header_logged", "HyperLab: threads of sender %d before restart-capture at " % sender.pid in text)
    check("thread_line_logged",
          re.search(r"^HyperLab: thread %d sleep state=[SR] wchan=\S+ syscall=\S+$" % sender.pid, text, re.M)
          is not None)
    check("log_start_kept", text.startswith("HyperLab: sender started "))


def test_restart_is_refused_without_an_answering_agent_or_on_a_failed_stop():
    for label, fakes, transport in (("agent_down", _Fakes(agent=False), "linux-experimental"),
                                    ("stop_failed", _Fakes(stop_rc=1), "linux-experimental"),
                                    ("windows", _Fakes(), "windows")):
        prepared = []
        saved = _patched(fakes, transport)
        try:
            lg.restart_capture(None, "dev-01", run=fakes.run,
                               prepare=lambda c, d, seen=prepared: seen.append(d) or True)
            check("%s_refused" % label, False)
        except Unavailable:
            check("%s_refused" % label, True)
        finally:
            _restore(saved)
        equals("%s_never_restarted_the_sender" % label, prepared, [])


def test_health_reports_each_fact_from_its_own_authority():
    started = "2026-10-07T14:02:17+02:00"
    probe = ("sender=running\nnow=%d\nlog_age=3\nstarted=%s\n" % (int(lg._epoch(started)) + 3725, started)
             + "".join("line=%s\n" % line for line in FROZEN + [WARN]))
    fakes = _Fakes(agent=True, probe=probe)
    saved = _patched(fakes)
    try:
        report = lg.health(None, "dev-01", run=fakes.run)
        timed_out = lg.agent_answers(
            "dev-01", run=lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("virsh", 10)))
    finally:
        _restore(saved)
    equals("health", {key: report[key] for key in ("machine", "agent", "sender", "stream", "health",
                                                   "no_frame_seconds")},
           {"machine": "dev-01", "agent": "yes", "sender": "running", "stream": "streaming", "health": "ok",
            "no_frame_seconds": 133})
    check("agent_asked_from_the_host",
          any(call[:1] == ["virsh"] and "guest-ping" in call[5] for call in fakes.calls if len(call) > 5))
    check("timeout_is_a_no", timed_out is False)
