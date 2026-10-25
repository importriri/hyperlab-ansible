#!/usr/bin/env python3
"""The showcase script only walks the take; it never changes the host.

It must not use privilege or a become prompt, must reach the shell only
through reviewed IPC targets and must validate the Machine name before
anything else runs. Its terminal is on camera, so it never collects or
prints who or where the host is, and a failing dependency is reported by a
fixed reason, never by that dependency's own output. The storyboard it
follows must fit the roadmap's 60 to 90 seconds.

The script runs here for real, in a fixture: a copy runs by its full path
from a checkout inside a sentinel home, every command it may call is a stub
that answers with sentinel host, user, home and address values on both of
its streams, the environment carries the same sentinels, and each shot's
prompt is answered as the operator does. None of them may reach the
script's standard output or error, on the complete walkthrough or on any
failure.
"""

from __future__ import annotations

import os
import re
import select
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/showcase/demo.sh"
DOC = ROOT / "docs/showcase.md"
IPC = ROOT / "roles/host_desktop_common/files/quickshell/hyperlab/ShellIpc.qml"
PROC = Path("/proc")
# "PID (COMMAND) STATE" and fields 4 to 52, all numbers (Linux 3.5 and
# later). The command may hold ") " itself; the state and the numbers that
# must follow it decide where the command ends.
STAT_LINE = re.compile(r"(?P<pid>[1-9][0-9]*) \((?P<command>.*)\) (?P<state>[A-Za-z])"
                       r"(?: -?[0-9]+){49,}\n", re.S)

NAME = "demo-01"
MARK = "zq7x"
SENT_HOST = f"host-{MARK}-nitro"
SENT_USER = f"user-{MARK}"
SENT_ADDR4 = "203.0.113.77"
SENT_ADDR6 = "2001:db8::7f3a"
SENT_MAC = "52:54:00:7f:3a:11"
SENT_RUNTIME = f"/run/user/4242/{MARK}"

IDENTITY = ("hostname", "hostnamectl", "id", "whoami", "logname", "uname", "ip", "ifconfig",
            "getent", "networkctl", "cat")
FORBIDDEN = ("sudo", "doas", "pkexec", "run0", "su", "virsh", "virt-install", "qemu-img",
             "systemctl", "ansible", "ansible-playbook")
SHOTS = ["1", "2", "3", "4", "5", "6"]
WALK_IPC = [("workspace", "close"), ("workspace", "machines"), ("workspace", "diagnostics"),
            ("workspace", "close")]


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


@dataclass
class Run:
    label: str
    returncode: int
    stdout: str
    stderr: str
    ipc: list[list[str]]
    cli: list[list[str]]
    sleeps: list[str]
    identity: list[list[str]]
    forbidden: list[list[str]]
    client_alive: bool = False

    def shots(self) -> list[str]:
        return re.findall(r"^== Shot (\d+): ", self.stdout, re.M)


def argv_log(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    return [line.split("\x1f")[:-1] for line in path.read_text().splitlines()]


def stub_text(fixture: Path, body: str) -> str:
    log = fixture / "log"
    return (
        "#!/bin/sh\n"
        f"sent_home='{fixture / ('home-' + MARK)}'\n"
        f"sent_host='{SENT_HOST}'\n"
        f"sent_user='{SENT_USER}'\n"
        f"sent_addr='{SENT_ADDR4}'\n"
        f"logdir='{log}'\n"
        "record() {\n"
        "    for arg in \"$@\"; do printf '%s\\037' \"${arg}\"; done >>\"${logdir}/$1\"\n"
        "    printf '\\n' >>\"${logdir}/$1\"\n"
        "}\n"
        "leak_out() {\n"
        "    printf '%s %s %s %s\\n' \"${sent_host}\" \"${sent_user}\" \"${sent_home}\" \"${sent_addr}\"\n"
        "}\n"
        "leak_err() {\n"
        "    printf 'error: %s/.local/state on %s for %s via %s\\n' \"${sent_home}\" \"${sent_host}\" "
        "\"${sent_user}\" \"${sent_addr}\" >&2\n"
        "}\n"
        + body
    )


# hyperlabctl: the inventory answers the next line of `states` on each call
# (the last line repeats); `open` only records.
CLI = """\
record hyperlabctl "$@"
leak_err
if [ "$#" -eq 3 ] && [ "$1" = machine ] && [ "$2" = inventory ] && [ "$3" = --json ]; then
    calls=0
    read -r calls <"${logdir}/../calls" || calls=0
    calls=$((calls + 1))
    printf '%s\\n' "${calls}" >"${logdir}/../calls"
    seen=0
    state=absent
    while IFS= read -r line; do
        seen=$((seen + 1))
        state="${line}"
        [ "${seen}" -ge "${calls}" ] && break
    done <"${logdir}/../states"
    other='{"name": "other-01", "state": "running", "display_name": "'"${sent_host}"'", "owner": "'"${sent_user}"'", "address": "'"${sent_addr}"'"}'
    case "${state}" in
        fail) exit 1 ;;
        garbage) printf 'Traceback: %s %s\\n' "${sent_home}" "${sent_addr}"; exit 0 ;;
        absent) printf '{"machines": [%s]}\\n' "${other}" ;;
        duplicate) printf '{"machines": [{"name": "%s", "state": "running"}, {"name": "%s", "state": "running"}, %s]}\\n' "${machine}" "${machine}" "${other}" ;;
        *) printf '{"machines": [{"name": "%s", "state": "%s", "owner": "%s"}, %s]}\\n' "${machine}" "${state}" "${sent_user}" "${other}" ;;
    esac
    exit 0
fi
read -r mode <"${logdir}/../open-mode" || mode=ok
case "${mode}" in
    fail) leak_out; leak_err; printf '%s\n' "$$" >"${logdir}/../open-pid"; exit 7 ;;
    fail-late)
        printf '%s\n' "$$" >"${logdir}/../open-pid"
        while [ ! -e "${logdir}/../open-go" ]; do "${real_sleep}" 0.02; done
        leak_out; leak_err; exit 7 ;;
    linger) printf '%s\n' "$$" >"${logdir}/../open-pid"; exec "${real_sleep}" 20 ;;
esac
leak_out
exit 0
"""

QS = """\
record qs "$@"
leak_out
leak_err
while IFS= read -r failing; do
    [ "$5.$6" = "${failing}" ] && exit 1
done <"${logdir}/../qs-fail"
exit 0
"""

SLEEP = """\
record sleep "$@"
leak_out
leak_err
[ -s "${logdir}/../sleep-fail" ] && exit 1
total=0
read -r total <"${logdir}/../slept" || total=0
total=$((total + $1))
printf '%s\\n' "${total}" >"${logdir}/../slept"
[ "${total}" -le 1000 ] || exit 1
exit 0
"""

IDENTITY_STUB = """\
record identity "${0##*/}" "$@"
case "${0##*/}" in
    ip) printf '2: enp9s0    inet %s/24 brd 203.0.113.255 scope global enp9s0\\n' "${sent_addr}"
        printf '3: virbr9    inet6 %s/64 scope global\\n' '""" + SENT_ADDR6 + """' ;;
    ifconfig) printf 'enp9s0: inet %s ether %s\\n' "${sent_addr}" '""" + SENT_MAC + """' ;;
    id|whoami|logname) printf '%s\\n' "${sent_user}" ;;
    getent) printf '%s:x:4242:4242::%s:/bin/sh\\n' "${sent_user}" "${sent_home}" ;;
    *) printf '%s\\n' "${sent_host}" ;;
esac
exit 0
"""

FORBIDDEN_STUB = """\
record forbidden "${0##*/}" "$@"
exit 1
"""


PROMPT = b"Press Enter when the shot is done. "


def drive(argv: list[str], env: dict[str, str], cwd: Path, stderr: Path, acks: int,
          on_prompt) -> tuple[int, str, str]:
    """Answer each shot's prompt as the operator does, one at a time."""
    with stderr.open("wb") as err:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=err,
                                   env=env, cwd=cwd)
        assert process.stdin is not None and process.stdout is not None
        if acks == 0:
            process.stdin.close()
        out, prompts, deadline = b"", 0, time.monotonic() + 120
        while True:
            ready, _, _ = select.select([process.stdout], [], [], max(0.0, deadline - time.monotonic()))
            if not ready:
                process.kill()
                process.wait()
                raise AssertionError(f"the script did not finish within 120 seconds:\n{out.decode()}")
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                break
            out += chunk
            while out.count(PROMPT) > prompts:
                prompts += 1
                if on_prompt is not None:
                    on_prompt(prompts)
                if not process.stdin.closed:
                    try:
                        process.stdin.write(b"\n")
                        process.stdin.flush()
                        if prompts >= acks:
                            process.stdin.close()
                    except BrokenPipeError:
                        pass
        process.stdout.close()
        if not process.stdin.closed:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
        returncode = process.wait(timeout=10)
    return returncode, out.decode(), stderr.read_text()


def exited(pid: int, proc: Path = PROC) -> bool:
    """True once the process has exited, whether or not it has been reaped.

    An exited child stays in the process table, in state Z, until its
    parent waits for it, and when that happens depends on the shell: Bash
    reaps a background job as soon as it ends, dash and BusyBox sh leave it
    there while `read` waits for the operator. A status line that cannot be
    read or parsed is a refusal, never an exit.
    """
    path = proc / str(pid) / "stat"
    try:
        stat = path.read_text()
    except (FileNotFoundError, ProcessLookupError):
        require((proc / "self" / "stat").is_file(), f"{proc} is not a proc filesystem")
        return True
    line = STAT_LINE.fullmatch(stat)
    require(line is not None and line["pid"] == str(pid), f"{path} is not a process status line: {stat!r}")
    assert line is not None
    return line["state"] == "Z"


def client_pid(path: Path) -> int | None:
    """The PID the client stub wrote, read once; None until it is written.

    The stub writes the PID and a newline: a missing or empty file, or one
    without the newline yet, is not written yet. Anything else that is not
    a PID is a refusal.
    """
    try:
        text = path.read_text()
    except FileNotFoundError:
        return None
    if not text.endswith("\n"):
        return None
    require(re.fullmatch(r"[1-9][0-9]*\n", text) is not None, f"{path} does not hold a PID: {text!r}")
    return int(text)


def refused(call: Callable[[], object]) -> bool:
    try:
        call()
    except (AssertionError, OSError):
        return True
    return False


def walk(label: str, argv: list[str], *, states: str = "absent\ncreating\ncreating\nrunning\n",
         acks: int = 6, qs_fail: str = "", missing: tuple[str, ...] = (), sleep_fail: bool = False,
         open_mode: str = "ok", after: list[int] | None = None) -> Run:
    with tempfile.TemporaryDirectory(prefix="showcase-") as raw:
        fixture = Path(raw)
        home = fixture / ("home-" + MARK)
        # The script runs from a checkout in the sentinel home, by its full
        # path: the working directory and every diagnostic the shell prefixes
        # with the script's path carry the sentinel.
        checkout = home / "hyperlab-ansible"
        script = checkout / SCRIPT.relative_to(ROOT)
        stubs, pybin, log = fixture / "stubs", fixture / "python", fixture / "log"
        for directory in (stubs, pybin, log, script.parent):
            directory.mkdir(parents=True)
        shutil.copy2(SCRIPT, script)
        (fixture / "states").write_text(states)
        (fixture / "qs-fail").write_text(qs_fail)
        (fixture / "sleep-fail").write_text("fail\n" if sleep_fail else "")
        (fixture / "open-mode").write_text(open_mode + "\n")
        (fixture / "calls").write_text("0\n")
        (fixture / "slept").write_text("0\n")
        python3, real_sleep, shell = shutil.which("python3"), shutil.which("sleep"), shutil.which("sh")
        require(None not in (python3, real_sleep, shell), "the showcase fixture needs python3, sleep and sh")
        if "python3" not in missing:
            (pybin / "python3").symlink_to(Path(str(python3)).resolve())
        programs = {"hyperlabctl": f"machine='{NAME}'\nreal_sleep='{real_sleep}'\n" + CLI, "qs": QS,
                    "sleep": SLEEP}
        programs |= dict.fromkeys(IDENTITY, IDENTITY_STUB)
        programs |= dict.fromkeys(FORBIDDEN, FORBIDDEN_STUB)
        for tool, body in programs.items():
            if tool in missing:
                continue
            stub = stubs / tool
            stub.write_text(stub_text(fixture, body))
            stub.chmod(0o755)
        env = {
            "PATH": f"{stubs}:{pybin}",
            "HOME": str(home),
            "USER": SENT_USER,
            "LOGNAME": SENT_USER,
            "HOSTNAME": SENT_HOST,
            "XDG_RUNTIME_DIR": SENT_RUNTIME,
            "LANG": "C.UTF-8",
        }
        pid_file = fixture / "open-pid"

        def on_prompt(prompt: int) -> None:
            # A failing client must have ended before the operator answers
            # this prompt. Whether the script's shell has reaped it by then
            # depends on the shell, so it is not waited for.
            if after is None or prompt not in after:
                return
            (fixture / "open-go").write_text("")
            deadline = time.monotonic() + 10
            while True:
                pid = client_pid(pid_file)
                if pid is not None and exited(pid):
                    return
                require(time.monotonic() < deadline, f"{label}: the Looking Glass stub did not end")
                time.sleep(0.02)

        try:
            returncode, stdout, stderr = drive([str(shell), str(script), *argv], env, checkout,
                                               fixture / "stderr", acks, on_prompt)
        except AssertionError as exc:
            raise AssertionError(f"{label}: {exc}") from exc
        # `open looking-glass` runs in the background; give its stub a moment.
        deadline = time.monotonic() + 5
        while (returncode == 0 and time.monotonic() < deadline
               and not any(call[1:3] == ["open", "looking-glass"]
                           for call in argv_log(log / "hyperlabctl"))):
            time.sleep(0.05)
        lingering = client_pid(pid_file) if open_mode == "linger" else None
        alive = lingering is not None and not exited(lingering)
        run = Run(label, returncode, stdout, stderr,
                  [call[1:] for call in argv_log(log / "qs")],
                  [call[1:] for call in argv_log(log / "hyperlabctl")],
                  [call[1] for call in argv_log(log / "sleep")],
                  [call[1:] for call in argv_log(log / "identity")],
                  [call[1:] for call in argv_log(log / "forbidden")],
                  alive)
        if lingering is not None and alive:
            os.kill(lingering, signal.SIGTERM)
    check_always(run)
    return run


def reviewed_ipc() -> set[tuple[str, str]]:
    ipc = IPC.read_text()
    reviewed = set()
    for block in ipc.split('target: "')[1:]:
        target = block.split('"', 1)[0]
        body = block.split("target:", 1)[0]
        reviewed |= {(target, function) for function in re.findall(r"function (\w+)\(", body)}
    return reviewed


def check_always(run: Run) -> None:
    """What holds on every run, whatever happened."""
    for stream, text in (("stdout", run.stdout), ("stderr", run.stderr)):
        for secret in (MARK, SENT_ADDR4, SENT_ADDR6, SENT_MAC, "4242"):
            require(secret not in text, f"{run.label}: a private sentinel ({secret}) reached {stream}:\n{text}")
    require(not run.identity, f"{run.label}: the script collected host identity: {run.identity}")
    require(not run.forbidden, f"{run.label}: the script ran a privileged or lifecycle tool: {run.forbidden}")
    reviewed = reviewed_ipc()
    for call in run.ipc:
        require(len(call) == 6 and call[:4] == ["-c", "hyperlab", "ipc", "call"]
                and (call[4], call[5]) in reviewed,
                f"{run.label}: shell IPC {call} is not a reviewed target")
    for call in run.cli:
        require(call == ["machine", "inventory", "--json"] or call == ["open", "looking-glass", NAME],
                f"{run.label}: hyperlabctl was asked for {call}")


def check_failure(run: Run, reason: str) -> None:
    require(run.returncode == 1, f"{run.label}: exit status {run.returncode}, not 1:\n{run.stderr}")
    lines = run.stderr.splitlines()
    require(len(lines) == 1 and lines[0].startswith("demo: ") and reason in lines[0],
            f"{run.label}: stderr is not the one reason {reason!r}:\n{run.stderr}")
    require(["open", "looking-glass", NAME] not in run.cli, f"{run.label}: Looking Glass opened anyway")


def check_walkthrough() -> None:
    run = walk("walkthrough", [NAME])
    require(run.returncode == 0, f"walkthrough: exit status {run.returncode}:\n{run.stderr}")
    require(run.stderr == "", f"walkthrough: the take's stderr is not empty:\n{run.stderr}")
    require(run.shots() == SHOTS, f"walkthrough: shots {run.shots()}, not {SHOTS}")
    before = run.stdout.split("== Shot 1:", 1)[0]
    for category in ("host name", "user name", "home path", "address", "notification", "password"):
        require(category in before, f"walkthrough: the checklist before shot 1 does not name the {category}")
    require(f"name {NAME}," in run.stdout.split("== Shot 3:", 1)[0].split("== Shot 2:", 1)[1],
            "walkthrough: shot 2 does not give the chosen Machine name")
    between = run.stdout.split("== Shot 2:", 1)[1].split("== Shot 3:", 1)[0]
    require(re.search(rf"Waiting for {NAME} to run\.+ running$", between, re.M) is not None,
            "walkthrough: shot 3 did not wait for the inventory to show the Machine running")
    require([tuple(call[4:]) for call in run.ipc] == WALK_IPC,
            f"walkthrough: shell IPC {run.ipc}, not {WALK_IPC}")
    inventory = [["machine", "inventory", "--json"]] * 4
    require(run.cli == [*inventory, ["open", "looking-glass", NAME]],
            f"walkthrough: hyperlabctl calls {run.cli}")
    require(run.sleeps == ["5", "5"], f"walkthrough: waited {run.sleeps}")


def check_names() -> None:
    bad = ["", "Demo", "-x", "x", "1ab", "ab-", "a" * 32, "x;id", "ab;id", "ab cd", "aa.b",
           "ab/cd", "ab$x", "--help", "d\u00e9mo", "d\u00c9mo", "ab\ncd"]
    for argv in [[], [NAME, "extra"], *([name] for name in bad)]:
        run = walk(f"name {argv!r}", argv)
        require(run.returncode == 2, f"name {argv!r}: exit status {run.returncode}, not 2")
        require(run.stdout == "" and run.stderr.startswith("usage: ") and run.stderr.count("\n") == 1,
                f"name {argv!r}: no usage refusal:\n{run.stderr}")
        require(not run.ipc and not run.cli and not run.sleeps,
                f"name {argv!r} reached the backend: {run.ipc} {run.cli}")
    for good in ("ab", "a" * 31, "dev-2"):
        run = walk(f"name {good!r}", [good], qs_fail="workspace.close\n")
        require(run.returncode == 1 and run.ipc, f"name {good!r} was refused before the preflight")


def check_failures() -> None:
    for tool in ("hyperlabctl", "qs", "python3", "sleep"):
        run = walk(f"without {tool}", [NAME], missing=(tool,))
        check_failure(run, f"{tool} is not installed")
        require(not run.ipc and not run.cli and not run.shots(), f"without {tool}: something ran")

    run = walk("failed shell preflight", [NAME], qs_fail="workspace.close\n")
    check_failure(run, "the HyperLab shell does not answer")
    require(not run.cli and not run.shots(), "failed shell preflight: the take went on")

    for states, label in (("running\n", "duplicate Machine"), ("stopped\n", "existing stopped Machine")):
        run = walk(label, [NAME], states=states)
        check_failure(run, f"{NAME} already exists")
        require(len(run.ipc) == 1 and not run.shots(), f"{label}: the take went on")

    for states, label in (("fail\n", "failed inventory"), ("garbage\n", "unreadable inventory"),
                          ("duplicate\n", "inventory naming the Machine twice")):
        run = walk(label, [NAME], states=states)
        check_failure(run, "the Machine inventory is not readable")
        require(len(run.ipc) == 1 and not run.shots(), f"{label}: the take went on")

    run = walk("inventory failing during the wait", [NAME], states="absent\ncreating\nfail\n")
    check_failure(run, "the Machine inventory is not readable")
    require(run.shots() == ["1", "2"], f"inventory failing during the wait: shots {run.shots()}")

    run = walk("Machine never running", [NAME], states="absent\ncreating\n")
    check_failure(run, f"{NAME} is not running after 15 minutes")
    require(run.shots() == ["1", "2"], f"Machine never running: shots {run.shots()}")
    slept = sum(int(seconds) for seconds in run.sleeps)
    require(slept == 900, f"Machine never running: the wait slept {slept} seconds, not 900")
    require(len(run.cli) == 1 + 900 // 5 + 1, f"Machine never running: {len(run.cli)} inventory calls")

    run = walk("sleep failing during the wait", [NAME], states="absent\ncreating\n", sleep_fail=True)
    check_failure(run, f"the wait for {NAME} was interrupted")
    require(run.shots() == ["1", "2"], f"sleep failing during the wait: shots {run.shots()}")

    for mode, after, label in (("fail", [5], "Looking Glass failing during shot 5"),
                               ("fail-late", [6], "Looking Glass failing during shot 6")):
        run = walk(label, [NAME], open_mode=mode, after=after)
        require(run.returncode == 1, f"{label}: exit status {run.returncode}, not 1")
        lines = run.stderr.splitlines()
        require(lines == [f"demo: Looking Glass failed for {NAME}; stop the take"],
                f"{label}: stderr is not the one reason:\n{run.stderr}")
        require(run.shots() == SHOTS[:after[0]], f"{label}: shots {run.shots()}")
        require("Take complete" not in run.stdout, f"{label}: the take was announced complete")

    run = walk("Looking Glass client still running", [NAME], open_mode="linger")
    require(run.returncode == 0 and "Take complete" in run.stdout,
            f"Looking Glass client still running: exit status {run.returncode}:\n{run.stderr}")
    require(run.client_alive, "Looking Glass client still running: the script waited for the client to end")

    run = walk("shell failing mid-take", [NAME], qs_fail="workspace.machines\n")
    check_failure(run, "the HyperLab shell did not open workspace machines")
    require(run.shots() == ["1"], f"shell failing mid-take: shots {run.shots()}")

    run = walk("no acknowledgement", [NAME], acks=0)
    check_failure(run, "no answer from the terminal")
    require(run.shots() == ["1"], f"no acknowledgement: shots {run.shots()}")


def check_source() -> None:
    source = SCRIPT.read_text()
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    for forbidden in ("sudo", " -K", "ansible-playbook", "virsh", "pkexec", "rm "):
        require(forbidden not in code, f"the showcase script must not use {forbidden.strip()}")
    # A builtin read of a host file cannot be stubbed: the script names none.
    host_file = re.search(r"(?<![\w.~-])/(proc|sys|etc)/", code)
    require(host_file is None, f"the showcase script reads a host file: {host_file and host_file.group(0)}")
    reviewed = reviewed_ipc()
    calls = re.findall(r"shell_ipc (\w+) (\w+)", code)
    require(calls, "the script reaches no shell surface")
    for call in calls:
        require(call in reviewed, f"shell IPC {call[0]}.{call[1]} is not a reviewed target")


def check_storyboard() -> None:
    seconds = [int(cell) for cell in re.findall(r"^\| \d+ \| (\d+) \|", DOC.read_text(), re.M)]
    require(len(seconds) >= 5 and 60 <= sum(seconds) <= 90,
            f"the storyboard runs {sum(seconds)} seconds, not 60 to 90")


def stat_line(pid: str, command: str, state: str, numbers: int = 49) -> str:
    """A made-up /proc/PID/stat line: Linux 3.5 and later print 49 numbers
    after the state (fields 4 to 52)."""
    return f"{pid} ({command}) {state} " + " ".join(["1", "-20", *["0"] * (numbers - 2)]) + "\n"


class CountedPath(Path):
    """A path that counts how often its text is read."""

    reads = 0

    def read_text(self, *args, **kwargs) -> str:
        self.reads += 1
        return super().read_text(*args, **kwargs)


def check_exit_predicate() -> None:
    """The fixture tells a client that has ended from one still running."""
    child = subprocess.Popen([sys.executable, "-I", "-c", ""])
    try:
        # Returns once the child has exited and leaves it unreaped (state Z).
        os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOWAIT)
        require((PROC / str(child.pid)).exists(), "exit predicate: the child was reaped before the check")
        require(exited(child.pid), "exit predicate: an exited, unreaped child counts as running")
    finally:
        child.wait()
    require(exited(child.pid), "exit predicate: a reaped child counts as running")

    live = subprocess.Popen([sys.executable, "-I", "-c", "import sys; sys.stdin.read()"],
                            stdin=subprocess.PIPE)
    assert live.stdin is not None
    try:
        # The child cannot end before its standard input is closed.
        require(not exited(live.pid), "exit predicate: a live child counts as exited")
    finally:
        live.stdin.close()
        live.wait()

    with tempfile.TemporaryDirectory(prefix="showcase-proc-") as raw:
        proc = Path(raw)
        require(refused(lambda: exited(7, proc)),
                "exit predicate: a missing proc filesystem counts as an exit")
        (proc / "self").mkdir()
        (proc / "self" / "stat").write_text("1 (python3) R 0 1 1\n")
        require(exited(7, proc), "exit predicate: a missing PID counts as running")
        entry = proc / "7"
        entry.mkdir()
        # The command name is in parentheses and may hold ") " itself.
        for stat, ended in ((stat_line("7", "sh", "S"), False), (stat_line("7", "sh", "Z"), True),
                            (stat_line("7", "a) Z (b", "S"), False), (stat_line("7", "a) S (b", "Z"), True),
                            (stat_line("7", "a\nb", "S"), False)):
            (entry / "stat").write_text(stat)
            require(exited(7, proc) is ended, f"exit predicate: {stat!r} read as exited={not ended}")
        whole = stat_line("7", "sh", "Z")
        for stat in ("", "garbage\n", "7) Z\n", "7 (sh) Z\n", "7 (sh)\n", "7 sh Z 1\n",
                     stat_line("8", "sh", "Z"), stat_line("7", "sh", "ZZ"), stat_line("7", "sh", "Z", 48),
                     whole.replace("(", "", 1), whole.replace(")", "", 1), whole[:-1],
                     whole[:-2] + "x\n"):
            (entry / "stat").write_text(stat)
            require(refused(lambda: exited(7, proc)), f"exit predicate: {stat!r} was not refused")
        (entry / "stat").unlink()
        (entry / "stat").mkdir()
        require(refused(lambda: exited(7, proc)), "exit predicate: an unreadable stat was not refused")

        pid_file = proc / "open-pid"
        require(client_pid(pid_file) is None, "client PID: a missing PID file holds a PID")
        for text in ("", "12"):
            pid_file.write_text(text)
            require(client_pid(pid_file) is None, f"client PID: {text!r} is a PID before it is written")
        pid_file.write_text("12\n")
        require(client_pid(pid_file) == 12, "client PID: '12\\n' is not PID 12")
        # One read per attempt: a second one could see other contents.
        for text in ("12\n", "", "12", "x\n"):
            pid_file.write_text(text)
            counted = CountedPath(pid_file)
            refused(partial(client_pid, counted))
            require(counted.reads == 1, f"client PID: {text!r} was read {counted.reads} times, not once")
        for text in ("\n", "x\n", "0\n", "-3\n", "12 13\n", "12\n13\n"):
            pid_file.write_text(text)
            require(refused(lambda: client_pid(pid_file)), f"client PID: {text!r} was not refused")


def main() -> int:
    check_exit_predicate()
    check_walkthrough()
    check_names()
    check_failures()
    check_source()
    check_storyboard()
    print("Showcase contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
