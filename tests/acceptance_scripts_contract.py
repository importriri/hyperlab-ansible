#!/usr/bin/env python3
"""The Nitro acceptance scripts keep their promises (tools/acceptance/).

  1. every group script sources lib.sh, names its group once, and starts
     and ends the report;
  2. no script runs sudo itself: root goes through lib.sh's as_root or
     playbook, and a script that uses them asks for the password once, at
     its top level, before any check;
  3. every destructive step (a boot entry, a reboot, LUKS, TPM, Secure Boot
     keys, a domain or lab host removed or started, the USB block turned
     on) sits inside an `if confirm ...` block;
  4. lib.sh never prints the password, never traces, hands it over only on
     stdin with -k or on a fresh 0600 FIFO, and redacts what it logs;
     run for real, its redactor removes keys, passwords and hashes and its
     check helper records PASS and FAIL into a private evidence tree;
  5. no script or lib.sh runs `hostname`, which Arch does not install
     (inetutils), and the report names the host it ran on
     (problems/acceptance-report-without-host.md);
  6. a failed playbook leaves in the report, not only in its own log, the
     name of each failed task and its message, redacted, and the report
     names the full log (problems/acceptance-check-log-only-recap.md);
  7. fail closed: a check mode run is the condition of the step it
     previews. Every `check … --check` is an `if check`, every confirm
     after it sits inside that block, and its else says the step was not
     offered; run for real, group 11 offers the block after a clean check
     mode and only then (problems/acceptance-step-offered-after-failed-check.md);
  8. the report names the commit the run came from, marked +dirty when
     tracked files differ from it, staged or not, with the redacted
     `git diff --stat` and any untracked file in the evidence
     (problems/acceptance-report-hid-a-dirty-tree.md);
  9. a playbook applied to a Machine (its runtime inventory, or a guest-*
     or vm-* playbook) stops at a confirmation first, and no script applies
     a whole workstation profile;
 11. group 7 proves a refusal only with a probe that says what stopped it
     (a drop, a reset, no route), never a probe that did not run, and only
     next to a control that the same probe reaches from the same guest;
 12. group 0 passes the lab host's status only when the lab tool reports
     it running, judged on the tool's own state line;
 13. group 11 passes "every attached device allowed" only when the allowed
     rows match the USB devices the kernel reports, with none blocked;
 14. group 10 names the boot entries exactly as roles/vfio_boot writes them,
     reads the default from bootctl's JSON (never a pattern on its status
     text), and offers the one-shot reboot only when both checks hold;
 10. group 16 passes nothing on an exit code alone: health only on the word
     "ok", the sender only when it is this build (its stamp's digests are
     the repository's, its running executable is the stamped binary, its log
     starts after the step began); it asks the operator nothing after a
     failed or skipped step, run for real in a terminal against fakes
     (problems/looking-glass-acceptance-passed-on-a-stale-sender.md).
"""

from __future__ import annotations

import importlib.util
import json
import io
import os
import pty
import re
import select
import stat
import time
import subprocess
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIR = ROOT / "tools/acceptance"
LIB = DIR / "lib.sh"
ROOT_HELPERS = ("as_root", "playbook", "backup_root")
DESTRUCTIVE = (
    r"bootctl\s+set-(oneshot|default)", r"systemctl\s+(reboot|poweroff)", r"\bcryptsetup\b",
    r"systemd-cryptenroll", r"sbctl\s+(enroll-keys|reset)", r"\bvirsh\b.*\b(destroy|undefine)\b",
    r"vm-destroy\.yml", r"hl_lab\.py\"?\s+(start|destroy)", r"\befibootmgr\b", r"\btpm2_",
    r"playbooks/host-usbguard\.yml(?!.*--check)", r"playbooks/foundation\.yml(?!.*--check)",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def unquoted(line: str) -> str:
    return re.sub(r'"(?:\\.|[^"\\])*"|\'[^\']*\'', '""', line.split(" #", 1)[0])


HOSTNAME_COMMAND = re.compile(r"(\$\(|`|^|[;&|]|\bthen\b|\bdo\b)\s*hostname\b")


def check_no_hostname_command() -> None:
    for path in sorted(DIR.glob("*.sh")):
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            require(HOSTNAME_COMMAND.search(line) is None,
                    f"{path.name}:{number} runs hostname, which Arch does not install: {line.strip()}")


def check_scripts() -> None:
    scripts = sorted(p for p in DIR.glob("*.sh") if p.name != "lib.sh")
    require(len(scripts) >= 5, "the acceptance scripts are missing")
    groups = set()
    for path in scripts:
        text = path.read_text()
        lines = text.splitlines()
        require(os.access(path, os.X_OK), f"{path.name} is not executable")
        group = re.search(r"^export ACCEPTANCE_GROUP=([a-z0-9-]+)", text, re.M)
        require(group is not None and group.group(1) not in groups, f"{path.name} has no unique group")
        groups.add(group.group(1))
        require('source "$(dirname "$0")/lib.sh"' in text and "acceptance_start" in text
                and lines[-1].strip() == "acceptance_end", f"{path.name} does not use the shared report")
        for number, line in enumerate(lines, 1):
            code = unquoted(line)
            require(re.search(r"(^|[\s;&|(])sudo\b", code) is None,
                    f"{path.name}:{number} runs sudo itself: {line.strip()}")
        uses_root = [i for i, line in enumerate(lines)
                     if not line.lstrip().startswith("#")
                     and re.search(r"(?<![-\w])(%s)(?![-\w])" % "|".join(ROOT_HELPERS), unquoted(line))]
        if uses_root:
            become = [i for i, line in enumerate(lines) if line.strip() == "become_once" and not line.startswith(" ")]
            require(become and become[0] < uses_root[0],
                    f"{path.name} uses root before asking for the password once at its top level")
        # Destructive steps only inside `if confirm` blocks.
        depth_stack: list[str] = []
        for number, line in enumerate(lines, 1):
            stripped = line.strip()
            indent = len(line) - len(line.lstrip())
            if stripped.startswith("if confirm "):
                depth_stack.append(" " * indent)
                continue
            if stripped == "fi" and depth_stack and depth_stack[-1] == " " * indent:
                depth_stack.pop()
                continue
            if stripped.startswith(("rollback ", "report ", "#")):
                continue
            for pattern in DESTRUCTIVE:
                if re.search(pattern, line):
                    require(depth_stack, f"{path.name}:{number} runs a destructive step without confirm: "
                                         f"{stripped}")


def check_library() -> None:
    text = LIB.read_text()
    require("set -x" not in text and "xtrace" not in text, "lib.sh traces its commands")
    require(re.search(r'(echo|printf)[^|>\n]*\$_become[^|>\n]*$', text, re.M) is None,
            "lib.sh prints the password somewhere other than a pipe or the FIFO")
    require('printf \'%s\\n\' "$_become" | sudo -S -k -p \'\' --' in text, "as_root does not hand the password over -k")
    require('mkfifo -m 600 "$fifo"' in text and '--become-password-file "$fifo"' in text and 'rm -f -- "$fifo"' in text,
            "playbook does not use a private, removed FIFO")
    for helper in ("check", "expect", "playbook"):
        body = text[text.index(f"\n{helper}() {{"):]
        body = body[:body.index("\n}\n")]
        require("| redact" in body, f"{helper} logs without redaction")
    require("umask 077" in text, "the evidence tree is not private")


def check_library_runs() -> None:
    secrets = ["password=hunter2", "-----BEGIN OPENSSH PRIVATE KEY-----", "b3BlbnNzaC1rZXk",
               "-----END OPENSSH PRIVATE KEY-----", "$6$salt$hashhashhash", "BECOME password: hunter3"]
    with tempfile.TemporaryDirectory() as td:
        script = f"""
ACCEPTANCE_GROUP=contract
HYPERLAB_EVIDENCE_ROOT={td}
source {LIB}
acceptance_start 2>/dev/null
check "passes" true 2>/dev/null
check "fails" false 2>/dev/null
check "leaks" printf '%s\\n' {' '.join(repr(s) for s in secrets)} 2>/dev/null
acceptance_end 2>/dev/null
echo "rc=$?"
echo "evidence=$EVIDENCE"
"""
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False,
                                env=dict(os.environ, HYPERLAB_EVIDENCE_ROOT=td))
        require("rc=1" in result.stdout, f"a failed check did not fail the group: {result.stdout} {result.stderr}")
        evidence = Path(result.stdout.split("evidence=", 1)[1].strip())
        report = (evidence / "report.txt").read_text()
        require("PASS  passes" in report and "FAIL  fails" in report
                and "1 failed" in report, f"the report does not record PASS and FAIL: {report}")
        require(stat.S_IMODE(evidence.stat().st_mode) == 0o700, "the evidence directory is not private")
        host = Path("/proc/sys/kernel/hostname").read_text().strip()
        require(f"group contract on {host} at " in report, f"the report does not name the host: {report}")
        require("command not found" not in result.stderr, f"lib.sh ran a missing command: {result.stderr}")
        logged = (evidence / "leaks.log").read_text()
        for secret in ("hunter2", "b3BlbnNzaC1rZXk", "hashhashhash", "hunter3"):
            require(secret not in logged, f"the log kept {secret}: {logged}")


FAKE_FAILED_PLAYBOOK = r"""#!/bin/sh
cat <<'OUT'
PLAY [Apply the host USB device policy] ****************************************
TASK [host_usbguard : Ask USBGuard for a policy that allows every attached device] ***
skipping: [localhost]
TASK [host_usbguard : Refuse a generated policy that would block an attached device] ***
fatal: [localhost]: FAILED! => {
    "assertion": "host_usbguard_allows | length > 0",
    "changed": false,
    "evaluated_to": false,
    "msg": "usbguard generate-policy allowed 0 devices but the kernel reports 4; token=abc123"
}
PLAY RECAP *********************************************************************
localhost                  : ok=8    changed=1    unreachable=0    failed=1    skipped=1
OUT
exit 2
"""


def check_failed_playbook_report() -> None:
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "bin"
        fake.mkdir()
        (fake / "ansible-playbook").write_text(FAKE_FAILED_PLAYBOOK)
        # Passwordless for the test only: become_once must not read a terminal.
        (fake / "sudo").write_text("#!/bin/sh\nexit 0\n")
        for tool in fake.iterdir():
            tool.chmod(0o755)
        script = f"""
ACCEPTANCE_GROUP=contract
source {LIB}
acceptance_start 2>/dev/null
check "usbguard check mode" playbook "usbguard check" -i inventory.ini playbooks/host-usbguard.yml --check 2>/dev/null
acceptance_end 2>/dev/null
echo "evidence=$EVIDENCE"
"""
        env = dict(os.environ, HYPERLAB_EVIDENCE_ROOT=td, PATH=f"{fake}:{os.environ['PATH']}")
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False, env=env)
        evidence = Path(result.stdout.split("evidence=", 1)[1].strip())
        report = (evidence / "report.txt").read_text()
        require("FAIL  usbguard check mode" in report, f"the failed check mode was not a FAIL: {report}")
        require("FAILED TASK: host_usbguard : Refuse a generated policy that would block an attached device" in report,
                f"the report does not name the failed task: {report}")
        require("msg: \"usbguard generate-policy allowed 0 devices but the kernel reports 4" in report,
                f"the report does not carry the failed task's message: {report}")
        require("abc123" not in report and "token=[redacted]" in report, f"the message was not redacted: {report}")
        require(f"full log: {evidence}/usbguard-check.log" in report, f"the report does not name the full log: {report}")
        check_log = (evidence / "usbguard-check-mode.log").read_text()
        require("FAILED TASK: host_usbguard : Refuse" in check_log, "the check's own log has only the recap")


CHECK_MODE = re.compile(r"^(\s*)(if\s+)?check\s.*--check\b")


def check_fail_closed() -> None:
    for path in sorted(DIR.glob("*.sh")):
        if path.name == "lib.sh":
            continue
        lines = path.read_text().splitlines()
        for number, line in enumerate(lines):
            match = CHECK_MODE.match(line)
            if match is None:
                continue
            require(match.group(2) is not None,
                    f"{path.name}:{number + 1} runs a check mode whose result guards nothing: {line.strip()}")
            indent = match.group(1)
            end = next((i for i in range(number + 1, len(lines))
                        if lines[i] in (f"{indent}else", f"{indent}fi")), None)
            require(end is not None and lines[end] == f"{indent}else",
                    f"{path.name}:{number + 1} has no else saying the step was not offered")
            require("NOT OFFERED" in lines[end + 1],
                    f"{path.name}:{end + 2} does not report that the step was not offered")
            for later in range(end, len(lines)):
                require(not lines[later].lstrip().startswith("if confirm "),
                        f"{path.name}:{later + 1} offers a step outside the check mode that previews it")


FAKE_CHECK_PLAYBOOK = r"""#!/bin/sh
case " $* " in
*" --check "*) exit "${FAKE_CHECK_RC:-0}" ;;
esac
exit 0
"""


def run_group_11(check_rc: int) -> str:
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "bin"
        fake.mkdir()
        (fake / "ansible-playbook").write_text(FAKE_CHECK_PLAYBOOK)
        (fake / "sudo").write_text("#!/bin/sh\nexit 0\n")
        for tool in fake.iterdir():
            tool.chmod(0o755)
        env = dict(os.environ, HYPERLAB_EVIDENCE_ROOT=td, PATH=f"{fake}:{os.environ['PATH']}",
                   FAKE_CHECK_RC=str(check_rc))
        # A new session has no terminal: confirm cannot wait for an answer.
        subprocess.run(["bash", str(DIR / "11-usbguard.sh")], capture_output=True, text=True, check=False,
                       env=env, stdin=subprocess.DEVNULL, start_new_session=True, timeout=120)
        reports = list(Path(td).glob("*/11-usbguard-*/report.txt"))
        require(len(reports) == 1, f"group 11 left {len(reports)} reports")
        return reports[0].read_text()


def check_fail_closed_runs() -> None:
    failed = run_group_11(2)
    require("FAIL  usbguard check mode" in failed and "BLOCK NOT OFFERED" in failed,
            f"a failed check mode did not stop the block: {failed}")
    require("STOP " not in failed, f"the block was offered after a failed check mode: {failed}")
    passed = run_group_11(0)
    require("PASS  usbguard check mode" in passed and "STOP  turn on USBGuard" in passed,
            f"a clean check mode did not offer the block: {passed}")
    require("BLOCK NOT OFFERED" not in passed, f"the block was refused after a clean check mode: {passed}")


def header_in(repo: Path, evidence_root: Path) -> tuple[str, Path]:
    # One root per run: two runs in the same second share an evidence name.
    evidence_root = evidence_root / str(len(list(evidence_root.glob("*"))) if evidence_root.exists() else 0)
    evidence_root.mkdir(parents=True)
    script = f"""
ACCEPTANCE_GROUP=contract
source {repo}/tools/acceptance/lib.sh
acceptance_start 2>/dev/null
echo "evidence=$EVIDENCE"
"""
    result = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=False,
                            env=dict(os.environ, HYPERLAB_EVIDENCE_ROOT=str(evidence_root)))
    evidence = Path(result.stdout.split("evidence=", 1)[1].strip())
    return (evidence / "report.txt").read_text(), evidence


def check_dirty_header() -> None:
    with tempfile.TemporaryDirectory() as td:
        repo = Path(td) / "repo"
        (repo / "tools/acceptance").mkdir(parents=True)
        (repo / "tools/acceptance/lib.sh").write_text(LIB.read_text())
        (repo / "notes.txt").write_text("one\n")
        git = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        subprocess.run([*git, "init", "-q"], check=True)
        subprocess.run([*git, "add", "."], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "fixture"], check=True)
        rev = subprocess.run([*git, "rev-parse", "--short", "HEAD"], capture_output=True, text=True,
                             check=True).stdout.strip()
        root = Path(td) / "evidence"

        report, evidence = header_in(repo, root)
        require(f"repository {rev}\n" in report and "+dirty" not in report,
                f"a clean checkout is not reported as its commit: {report}")
        require(not (evidence / "repository-diff-stat.txt").exists(), "a clean checkout left a diff")

        (repo / "notes.txt").write_text("one\npassword=hunter2\n")
        report, evidence = header_in(repo, root)
        require(f"repository {rev}+dirty" in report, f"a modified tracked file is not +dirty: {report}")
        stat = (evidence / "repository-diff-stat.txt").read_text()
        require("notes.txt" in stat and "hunter2" not in stat, f"the diff stat is missing or leaks: {stat}")

        subprocess.run([*git, "add", "notes.txt"], check=True)
        report, _ = header_in(repo, root)
        require(f"repository {rev}+dirty" in report, f"a staged change is not +dirty: {report}")

        subprocess.run([*git, "commit", "-q", "-m", "second"], check=True)
        (repo / "scratch.txt").write_text("x\n")
        report, evidence = header_in(repo, root)
        require("+dirty" not in report and "1 untracked file(s)" in report,
                f"an untracked file is not reported apart: {report}")
        require("scratch.txt" in (evidence / "repository-untracked.txt").read_text(),
                "the untracked file is not listed in the evidence")


MACHINE_PLAYBOOK = re.compile(r"(ansible-playbook|\bplaybook\b).*(XDG_RUNTIME_DIR|inventory\[@\]|playbooks/(guest|vm)-)")


def check_machine_playbooks() -> None:
    for path in sorted(DIR.glob("*.sh")):
        if path.name == "lib.sh":
            continue
        text = path.read_text()
        require("guest-arch-" not in text, f"{path.name} applies a whole workstation profile")
        stack: list[str] = []
        for number, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            indent = line[:len(line) - len(line.lstrip())]
            if stripped.startswith("if confirm "):
                stack.append(indent)
                continue
            if stripped == "fi" and stack and stack[-1] == indent:
                stack.pop()
                continue
            if stripped.startswith(("#", "report ", "rollback ")):
                continue
            if MACHINE_PLAYBOOK.search(line):
                require(stack, f"{path.name}:{number} applies a playbook to a Machine without a confirmation: {stripped}")


def load_identity():
    spec = importlib.util.spec_from_file_location("sender_identity", DIR / "sender_identity.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def good_probe(identity, binary="b" * 64, exe=None, pid="918", started="2026-10-06T22:30:39+02:00", stalls="0",
               restarts="0"):
    want = identity.expected()
    lines = [f"pid={pid}", f"exe_sha256={exe or binary}"]
    lines += [f"stamp.{key}={value}" for key, value in want.items()]
    if binary:
        lines.append(f"stamp.binary_sha256={binary}")
    lines += ["stamp.runtime_enabled=false", f"started={started}", f"no_usable_frame={stalls}",
              f"capture_restarts={restarts}"]
    return "dev-01 | CHANGED | rc=0 >>\n" + "\n".join(lines) + "\n"


def check_sender_identity() -> None:
    identity = load_identity()
    since = time.mktime(time.strptime("2026-10-06 22:30:00", "%Y-%m-%d %H:%M:%S"))
    want = identity.expected()

    def verdict(text, **kwargs):
        return all(ok for ok, _ in identity.judge(identity.parse(text), want, since, **kwargs))

    require(verdict(good_probe(identity), not_pid="809", no_restart=True), "a sender of this build was refused")
    # A still desktop probably sends no frame: its warnings are counted, not a failure.
    require(verdict(good_probe(identity, stalls="2"), no_restart=True), "silence warnings failed the step")
    require(verdict(good_probe(identity), pid="918"), "the same sender was refused")
    bad = {
        "an old runtime patch": good_probe(identity).replace(want["runtime_patch_sha256"], "1b8bf54e" + "0" * 56),
        "no binary digest": good_probe(identity, binary=""),
        "a running executable that is not the stamped binary": good_probe(identity, exe="c" * 64),
        "a log started before the step": good_probe(identity, started="2026-10-06T17:00:00+02:00"),
        "no start line": good_probe(identity).replace("started=", "x="),
        "no sender": good_probe(identity, pid="none"),
    }
    for label, text in bad.items():
        require(not verdict(text), f"the identity check accepted {label}")
    require(not verdict(good_probe(identity), not_pid="918"), "the identity check accepted the old process")
    require(not verdict(good_probe(identity), pid="999"), "the identity check accepted another process")
    require(not verdict(good_probe(identity, restarts="1"), no_restart=True),
            "the identity check accepted a capture restart")
    require(not verdict(good_probe(identity, restarts=""), no_restart=True), "an unread restart count passed")
    probe = identity.PROBE
    require("/proc/$pid/exe" in probe and "\necho\n" in probe, "the probe does not read the running binary or "
            "end the stamp's last line")

    script = (DIR / "16-looking-glass-sender.sh").read_text()
    for line in script.splitlines():
        if re.match(r'\s*(check|expect)\s+"[^"]*health', line):
            require("health_ok" in line, f"16 judges health without the word: {line.strip()}")
        if re.match(r'\s*(if\s+)?(check|expect)\s', line) and "looking-glass health" in line:
            raise AssertionError(f"16 passes the health command on its exit code: {line.strip()}")
    require('grep -q \'"health":"ok"\'' in script, "health_ok does not look for the word ok")


FAKE_ANSIBLE = r"""#!/bin/sh
cat "$FAKE_DIR/$FAKE_PROBE_NAME"
"""
FAKE_HYPERLABCTL = r"""#!/bin/sh
case "$*" in
*restart-capture*) exit 0 ;;
*health*) echo '{"health":"idle"}' ;;
esac
"""


def run_in_terminal(script: str, fakes: dict[str, str], files: dict[str, str], answers: dict[str, str],
                    extra_env: dict[str, str] | None = None, args: tuple[str, ...] = ()) -> str:
    """Run an acceptance script in a pseudo-terminal against fake tools.

    Every time a question appears it is answered once; a script that does
    not finish within a minute is killed and fails the contract.
    """
    with tempfile.TemporaryDirectory() as td:
        fake = Path(td) / "bin"
        fake.mkdir()
        for name, body in fakes.items():
            (fake / name).write_text(body)
            (fake / name).chmod(0o755)
        for name, body in files.items():
            (Path(td) / name).write_text(body)
        env = dict(os.environ, HYPERLAB_EVIDENCE_ROOT=td, PATH=f"{fake}:{os.environ['PATH']}",
                   XDG_RUNTIME_DIR=td, FAKE_DIR=td, **(extra_env or {}))
        child, master = pty.fork()
        if child == 0:
            os.execve("/bin/bash", ["bash", str(DIR / script), *args], env)
        seen, deadline, finished = b"", time.monotonic() + 60, False
        answered = dict.fromkeys(answers, 0)
        while time.monotonic() < deadline:
            ready, _, _ = select.select([master], [], [], 0.5)
            if ready:
                try:
                    chunk = os.read(master, 4096)
                except OSError:
                    finished = True
                    break
                if not chunk:
                    finished = True
                    break
                seen += chunk
                for prompt, answer in answers.items():
                    while seen.count(prompt.encode()) > answered[prompt]:
                        answered[prompt] += 1
                        os.write(master, answer.encode() + b"\n")
        if not finished:
            os.kill(child, 9)
        os.waitpid(child, 0)
        os.close(master)
        require(finished, f"{script} did not finish within a minute: {seen.decode(errors='replace')[-500:]}")
        group = script.rsplit(".", 1)[0]
        reports = list(Path(td).glob(f"*/{group}-*/report.txt"))
        require(len(reports) == 1, f"{script} left {len(reports)} reports: {seen.decode(errors='replace')[-500:]}")
        return reports[0].read_text()


def run_16(playbook_rc: int, probe: str, answers: dict[str, str]) -> str:
    return run_in_terminal(
        "16-looking-glass-sender.sh",
        {"ansible": FAKE_ANSIBLE, "ansible-playbook": f"#!/bin/sh\nexit {playbook_rc}\n",
         "hyperlabctl": FAKE_HYPERLABCTL},
        {"probe.txt": probe}, answers, {"HYPERLABCTL": "hyperlabctl", "FAKE_PROBE_NAME": "probe.txt"})


TCP_PROBE = DIR / "probes/tcp-probe"


def check_tcp_probe() -> None:
    import socket

    def probe(port: int, path: str | None = None) -> str:
        env = dict(os.environ, PATH=path) if path is not None else None
        result = subprocess.run(["/bin/sh", str(TCP_PROBE), "127.0.0.1", str(port)], capture_output=True,
                                text=True, check=False, env=env, timeout=20)
        return result.stdout.strip()

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        require(probe(listener.getsockname()[1]) == "result=reached", "the probe did not reach a listening port")
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        port = closed.getsockname()[1]
    require(probe(port) == "result=refused", "the probe did not report a refusal")
    require(probe(port, path="/nonexistent") == "result=cannot-run", "a probe without bash ran anyway")
    with tempfile.TemporaryDirectory() as td:
        for name, body in (("timeout-124", "exit 124"), ("timeout-unreach", "echo 'Network is unreachable' >&2; exit 1"),
                           ("timeout-7", "echo weird >&2; exit 7")):
            directory = Path(td) / name
            directory.mkdir()
            (directory / "timeout").write_text(f"#!/bin/sh\n{body}\n")
            (directory / "timeout").chmod(0o755)
        bash_dir = str(Path(subprocess.run(["sh", "-c", "command -v bash"], capture_output=True, text=True,
                                           check=True).stdout.strip()).parent)
        for name, expected_word in (("timeout-124", "result=timeout"), ("timeout-unreach", "result=unreachable"),
                                    ("timeout-7", "result=other:7")):
            got = probe(port, path=f"{Path(td) / name}:{bash_dir}")
            require(got == expected_word, f"the probe read {name} as {got}")

    script = (DIR / "07-network-isolation.sh").read_text()
    require("! timeout" not in script and '-a "!' not in script,
            "group 7 still proves a refusal by negating a command that may not have run")
    control = script.index('if expect "srv-tz-01 reaches its own gateway\'s DNS over TCP (control)" \'^result=reached$\'')
    otherwise = script.index("NOT JUDGED", control)
    for name in ("srv-tz-01 cannot reach the dev resolver", "srv-tz-01 cannot reach the host's LLMNR"):
        at = script.index(name)
        require(control < at < otherwise, f"{name!r} is judged outside its control")
        require("'^result=(timeout|refused|unreachable)$'" in script[at:at + 200],
                f"{name!r} accepts something other than a refusal")


FAKE_ANSIBLE_07 = r"""#!/bin/sh
case "$*" in
*"tcp-probe 10.10.5.1 53") word=$CONTROL ;;
*tcp-probe*) word=$REFUSAL ;;
*) echo "srv-tz-01 | SUCCESS"; exit 0 ;;
esac
printf 'srv-tz-01 | CHANGED => {\n    "stdout_lines": [\n        "result=%s"\n    ]\n}\n' "$word"
"""


def run_07(control: str, refusal: str) -> str:
    return run_in_terminal(
        "07-network-isolation.sh",
        {"ansible": FAKE_ANSIBLE_07, "ansible-playbook": "#!/bin/sh\nexit 0\n", "sudo": "#!/bin/sh\nexit 0\n",
         "virsh": "#!/bin/sh\nexit 0\n"},
        {}, {"Type 'apply'": "apply"}, {"CONTROL": control, "REFUSAL": refusal})


def check_07_runs() -> None:
    good = run_07("reached", "timeout")
    require("PASS  srv-tz-01 reaches its own gateway's DNS over TCP (control)" in good
            and "PASS  srv-tz-01 cannot reach the dev resolver" in good
            and "PASS  srv-tz-01 cannot reach the host's LLMNR" in good, f"group 7 did not judge a drop: {good}")
    norun = run_07("reached", "cannot-run")
    require("FAIL  srv-tz-01 cannot reach the dev resolver" in norun, f"a probe that never ran passed: {norun}")
    blind = run_07("cannot-run", "timeout")
    require("NOT JUDGED" in blind and "PASS  srv-tz-01 cannot reach" not in blind,
            f"refusals passed without a control: {blind}")


def check_00_status() -> None:
    script = (DIR / "00-lab-host.sh").read_text()
    require('check "lab host status"' not in script, "group 0 passes the lab host's status on an exit code")
    match = re.search(r"expect \"lab host status is running\" '([^']+)'", script)
    require(match is not None, "group 0 does not judge the lab host's state")
    pattern = re.compile(match.group(1), re.M)
    spec = importlib.util.spec_from_file_location("hl_lab", ROOT / "tools/lab/hl_lab.py")
    hl_lab = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(hl_lab)
    saved = hl_lab.virsh
    try:
        for state, should_pass in (("running", True), ("shut off", False), ("paused", False), ("", False)):
            def fake(*args, check=True, _state=state):
                listing = {"net-list": hl_lab.NETWORK, "pool-list": hl_lab.POOL, "list": hl_lab.DOMAIN}
                out = listing.get(args[0], _state if args[0] == "domstate" else "")
                return subprocess.CompletedProcess(args, 0, out + "\n", "")
            hl_lab.virsh = fake
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                hl_lab.status()
            require(bool(pattern.search(buffer.getvalue())) == should_pass,
                    f"group 0 reads the state {state!r} wrongly: {buffer.getvalue()}")
    finally:
        hl_lab.virsh = saved


FAKE_SUDO_USBGUARD = r"""#!/bin/sh
case "$*" in
*"usbguard list-devices"*) printf '%b' "$LIST_DEVICES" ;;
esac
exit 0
"""


def run_11_listing(listing: str) -> str:
    with tempfile.TemporaryDirectory() as sysfs:
        for number in range(3):
            device = Path(sysfs) / f"1-{number}"
            device.mkdir()
            for name, value in (("idVendor", "1d6b"), ("idProduct", f"000{number}"), ("authorized", "1")):
                (device / name).write_text(value + "\n")
        return run_in_terminal(
            "11-usbguard.sh",
            {"ansible-playbook": "#!/bin/sh\nexit 0\n", "sudo": FAKE_SUDO_USBGUARD},
            {}, {"Type 'block'": "block", "[y/n]": "y"},
            {"HYPERLAB_USB_SYSFS": sysfs, "LIST_DEVICES": listing})


def check_11_allowed_count() -> None:
    script = (DIR / "11-usbguard.sh").read_text()
    require("'^[0-9]+: allow' as_root" not in script, "group 11 passes on one allowed device")
    allow = "".join(f"{n}: allow id 1d6b:000{n} via-port \"1-{n}\"\\n" for n in range(3))
    good = run_11_listing(allow)
    require("PASS  every attached device allowed, none blocked" in good, f"three of three allowed failed: {good}")
    one = run_11_listing("1: allow id 1d6b:0000\\n")
    require("FAIL  every attached device allowed, none blocked" in one, f"one of three allowed passed: {one}")
    blocked = run_11_listing(allow + "4: block id 090c:1000 via-port \"1-1\"\\n")
    require("FAIL  every attached device allowed, none blocked" in blocked, f"a blocked device passed: {blocked}")


def check_10_entries() -> None:
    script = (DIR / "10-apparmor-boot.sh").read_text()
    defaults = (ROOT / "roles/vfio_boot/defaults/main.yml").read_text()
    tasks = (ROOT / "roles/vfio_boot/tasks/main.yml").read_text()
    entry_match = re.search(r"^entry=(\S+)$", script, re.M)
    default_match = re.search(r"^default_entry=(\S+)$", script, re.M)
    require(entry_match is not None and default_match is not None,
            "group 10 does not name both the AppArmor entry and the default entry")
    entry, default_entry = entry_match.group(1), default_match.group(1)
    require(f"- file: {entry}" in defaults and "AppArmor" in entry, f"group 10's AppArmor entry {entry} is not the role's")
    require(f"line: default {default_entry}" in tasks, f"group 10's default entry {default_entry} is not the role's")
    require("bootctl status" not in script, "group 10 reads the default from bootctl's status text")

    def boot_json(default: str, present: bool = True) -> str:
        ids = ["Arch-Linux-Hardened.conf", default_entry] + ([entry] if present else [])
        return json.dumps([{"id": i, "isDefault": i == default} for i in ids])

    fakes = {"sudo": "#!/bin/sh\nexit 0\n", "bootctl": "#!/bin/sh\nprintf '%s' \"$BOOT_JSON\"\n"}
    answers = {"Type 'reboot'": "no"}
    good = run_in_terminal("10-apparmor-boot.sh", fakes, {}, answers, {"BOOT_JSON": boot_json(default_entry)},
                           ("prepare",))
    require("PASS  the AppArmor entry exists" in good and "PASS  the default is still the Vfio entry" in good
            and "STOP  boot once into the AppArmor entry" in good, f"group 10 refused the reviewed entries: {good}")
    wrong = run_in_terminal("10-apparmor-boot.sh", fakes, {}, answers, {"BOOT_JSON": boot_json(entry)},
                            ("prepare",))
    require("FAIL  the default is still the Vfio entry" in wrong and "REBOOT NOT OFFERED" in wrong
            and "STOP " not in wrong, f"group 10 went on with the AppArmor entry as default: {wrong}")
    missing = run_in_terminal("10-apparmor-boot.sh", fakes, {}, answers,
                              {"BOOT_JSON": boot_json(default_entry, present=False)}, ("prepare",))
    require("FAIL  the AppArmor entry exists" in missing and "REBOOT NOT OFFERED" in missing,
            f"group 10 offered a reboot into a missing entry: {missing}")


def load_phases():
    spec = importlib.util.spec_from_file_location("sender_phases", DIR / "sender_phases.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def phase_files(resumed: str = "00:06:42.500", extra: tuple[str, ...] = (), after_pid: str = "918",
                still_end: str = "400.5", change: dict[str, str] | None = None) -> dict[str, str]:
    """dev-01's answers for a healthy run: still from 100 s to 400.5 s after the
    sender started, notifications from 401 s to 431.5 s."""
    fields = {"pid": "918", "focused": "yes", "opened": "30 Hyprland notifications showing dev-01's time",
              "change_from": "401.000", "change_to": "431.500", "notify_failures": "0",
              "dismissed_rc": "0", "closed_at": "432.000", **(change or {})}
    lines = ["00:00:00.056 [I] app.c:451 | captureStart | ==== [ Capture Start ] ====",
             "00:00:00.063 [I] app.c:461 | captureStop | ==== [ Capture Stop ] ====",
             "00:01:52.000 [I] app.c:451 | captureStart | ==== [ Capture Start ] ====",
             "00:02:10.000 [W] pipewire.c:577 | pipewire_capture | No usable frame for 10 s while streaming: "
             "0 process callbacks, 0 empty buffers since the last frame"]
    if resumed:
        lines.append(f"{resumed} [I] pipewire.c:211 | streamProcessCallback | Frames resumed after 282 s "
                     "without a usable frame")
    lines += list(extra)
    return {
        "mark-1.txt": "dev-01 | CHANGED | rc=0 >>\npid=918\nelapsed=100.000\n",
        "mark-2.txt": f"dev-01 | CHANGED | rc=0 >>\npid=918\nelapsed={still_end}\n",
        "change.txt": "dev-01 | CHANGED | rc=0 >>\n" + "".join(f"{k}={v}\n" for k, v in fields.items()),
        "log.txt": f"dev-01 | CHANGED | rc=0 >>\npid={after_pid}\n" + "".join(f"line={x}\n" for x in sorted(lines)),
    }


def check_sender_phases() -> None:
    phases = load_phases()

    def verdict(files: dict[str, str]) -> tuple[bool, list[str]]:
        f = phases.fields
        findings, notes = phases.judge(f(files["mark-1.txt"]), f(files["mark-2.txt"]), f(files["change.txt"]),
                                       f(files["log.txt"]), phases.events(files["log.txt"]))
        return all(ok for ok, _ in findings), [text for ok, text in findings if not ok] + notes

    ok, said = verdict(phase_files())
    require(ok, f"a healthy run was refused: {said}")
    require(any("warnings in the still phase: 1" in text for text in said), f"the warnings are not counted: {said}")
    require(any(text.startswith("opened in dev-01: 30 Hyprland") and "closed at 432.000" in text for text in said),
            f"what was opened and its closing are not said: {said}")
    # 10 s after the last still frame (393 s), the warning lands just after
    # the change began: it is the still phase's, and the resume still counts.
    boundary = phase_files(resumed="00:06:42.500", extra=(
        "00:06:41.200 [W] pipewire.c:577 | pipewire_capture | No usable frame for 10 s while streaming",
        "00:06:33.000 [I] pipewire.c:211 | streamProcessCallback | Frames resumed after 20 s"))
    ok, said = verdict(boundary)
    require(ok, f"a warning about a silence from before the change failed the changing phase: {said}")
    flowing = phase_files(resumed="00:03:00.000")
    ok, said = verdict(flowing)
    require(ok and any("already arriving" in text for text in said),
            f"frames that resumed before the change were not accepted as flowing: {said}")
    bad = {
        "frames resumed after 2.5 s": phase_files(resumed="00:06:43.500"),
        "no frames resumed": phase_files(resumed=""),
        "a warning while the screen changed": phase_files(extra=(
            "00:07:00.000 [W] pipewire.c:577 | pipewire_capture | No usable frame for 10 s while streaming",)),
        "a Capture Stop in the still phase": phase_files(extra=(
            "00:03:20.000 [I] app.c:461 | captureStop | ==== [ Capture Stop ] ====",)),
        "a capture restart": phase_files(extra=(
            "00:03:20.000 [W] pipewire.c:570 | pipewire_capture | The PipeWire stream failed: "
            "restarting the capture",)),
        "another sender at the end": phase_files(after_pid="919"),
        "a still phase of 250 s": phase_files(still_end="350.0"),
        "a notification not shown": phase_files(change={"notify_failures": "1"}),
        "an unfocused captured output": phase_files(change={"focused": "no"}),
        "notifications never closed": phase_files(change={"closed_at": ""}),
    }
    for label, files in bad.items():
        ok, said = verdict(files)
        require(not ok, f"the phase judge accepted {label}: {said}")

    script = (DIR / "16-looking-glass-sender.sh").read_text()
    require("STILL_SECONDS=${ACCEPTANCE_STILL_SECONDS:-300}" in script, "16 does not time a 5-minute still phase")
    order = [script.index(step) for step in ('in_dev01 mark "$EVIDENCE/phase-still-start.txt"',
                                             'sleep "$STILL_SECONDS"',
                                             'in_dev01 mark "$EVIDENCE/phase-still-end.txt"',
                                             'in_dev01 change', 'in_dev01 log', '"$PHASES" judge')]
    require(order == sorted(order), "16 runs the phases out of order")
    change = phases.CHANGE
    require(change.count("timeout 5 hyprctl") == change.count("hyprctl"),
            "a hyprctl call in dev-01 has no time limit")
    require("trap close_all EXIT" in change and "dismissnotify" in change and "while [ \"$i\" -lt 30 ]" in change,
            "the change in dev-01 is not bounded or not closed on exit")
    require(not re.search(r"\b(pacman|install|cp|mv|tee|>\s*/)", change.split("echo \"opened=")[1].split("done")[0]),
            "the change in dev-01 installs or writes something")


FAKE_ANSIBLE_PHASES = r"""#!/bin/sh
case "$*" in
*"sender_phases: mark"*)
    n=$(( $(cat "$FAKE_DIR/marks" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$FAKE_DIR/marks"
    cat "$FAKE_DIR/mark-$n.txt" ;;
*"sender_phases: change"*) cat "$FAKE_DIR/change.txt" ;;
*"sender_phases: log"*) cat "$FAKE_DIR/log.txt" ;;
*)
    n=$(( $(cat "$FAKE_DIR/probes" 2>/dev/null || echo 0) + 1 )); echo "$n" > "$FAKE_DIR/probes"
    if [ "$n" -le 2 ]; then cat "$FAKE_DIR/probe-old.txt"; else cat "$FAKE_DIR/probe.txt"; fi ;;
esac
"""
FAKE_HYPERLABCTL_OK = r"""#!/bin/sh
case "$*" in
*restart-capture*) exit 0 ;;
*health*) echo '{"health":"ok"}' ;;
esac
"""


# Every health answer is counted; sleep returns at once and records what it was asked.
FAKE_HYPERLABCTL_IDLE = r"""#!/bin/sh
case "$*" in
*restart-capture*) exit 0 ;;
*health*) echo x >> "$FAKE_DIR/health-calls"
    echo '{"machine":"dev-01","agent":"yes","sender":"running","stream":"idle","health":"idle"}' ;;
esac
"""
FAKE_SLEEP = "#!/bin/sh\necho \"$1\" >> \"$FAKE_DIR/slept\"\n"


def run_16_phases(files: dict[str, str], hyperlabctl: str = FAKE_HYPERLABCTL_OK,
                  answers: dict[str, str] | None = None) -> tuple[str, tuple[int, list[str]]]:
    """The report of a run that reaches the phases, with how many times it
    asked for the health and what it asked sleep for."""
    identity = load_identity()
    later = time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(time.time() + 120))
    later = later[:-2] + ":" + later[-2:]
    probes = {"probe-old.txt": good_probe(identity, pid="809"), "probe.txt": good_probe(identity, started=later)}
    answers = answers or {"Type 'rebuild'": "rebuild", "Type 'restart'": "restart", "[y/n]": "y",
                          "Type 'pane'": "no"}
    calls = Path(tempfile.mkdtemp())
    fake_health = hyperlabctl.replace('"$FAKE_DIR/health-calls"', f'"{calls}/health-calls"')
    try:
        report = run_in_terminal(
            "16-looking-glass-sender.sh",
            {"ansible": FAKE_ANSIBLE_PHASES, "ansible-playbook": "#!/bin/sh\nexit 0\n",
             "hyperlabctl": fake_health, "grim": "#!/bin/sh\nexit 1\n",
             "sleep": FAKE_SLEEP.replace('"$FAKE_DIR/slept"', f'"{calls}/slept"')},
            {**probes, **files}, answers, {"HYPERLABCTL": "hyperlabctl", "ACCEPTANCE_STILL_SECONDS": "0"})
        health = (calls / "health-calls").read_text().count("x") if (calls / "health-calls").exists() else 0
        slept = (calls / "slept").read_text().split() if (calls / "slept").exists() else []
    finally:
        for leftover in calls.iterdir():
            leftover.unlink()
        calls.rmdir()
    return report, (health, slept)


def check_16_phases_run() -> None:
    passed, _ = run_16_phases(phase_files())
    stream = passed.find("PASS  health is ok before the still phase")
    shown = passed.find("PASS  Looking Glass shows dev-01's desktop (operator)")
    require(0 <= stream < shown, f"16 asks whether the desktop shows before the stream is healthy: {passed}")
    require("PASS  still and changing phases" in passed and "PASS  health is ok after the changing phase" in passed,
            f"16 did not pass a healthy still and changing run: {passed}")
    require("opened in dev-01: 30 Hyprland notifications" in passed and "closed at 432.000" in passed,
            f"16's report does not say what it opened in dev-01 and that it closed: {passed}")
    failed, _ = run_16_phases(phase_files(change={"notify_failures": "1"}))
    require("FAIL  still and changing phases" in failed and "STOPPED" in failed
            and "8;10u" not in failed, f"16 went on after a failed phase: {failed}")
    require("closed at 432.000" in failed, f"a failed run does not say the notifications closed: {failed}")

    # problems/looking-glass-acceptance-asked-before-the-stream.md: a window
    # showing dev-01 through SPICE looked like the stream while no client was
    # connected to the sender. The script waits up to 60 s for health ok
    # before asking, and says why it failed.
    idle, (calls, slept) = run_16_phases(phase_files(), hyperlabctl=FAKE_HYPERLABCTL_IDLE)
    require("FAIL  health is ok before the still phase" in idle and "STOPPED" in idle,
            f"16 went on with an idle stream: {idle}")
    require("(operator)" not in idle.split("Open Looking Glass on dev-01")[1],
            f"16 asked the operator before the stream was healthy: {idle}")
    require("no Looking Glass client is connected to dev-01's sender" in idle and "SPICE display" in idle,
            f"16's failure does not say that no client is connected: {idle}")
    require(calls == 13 and sum(int(s) for s in slept) == 60,
            f"16 did not wait 60 s for health ok before the still phase ({calls} answers, slept {slept})")
    declined, _ = run_16_phases(phase_files(), answers={
        "Type 'rebuild'": "rebuild", "Type 'restart'": "restart",
        "Does Looking Glass show dev-01's desktop": "n"})
    require("FAIL  Looking Glass shows dev-01's desktop (operator)" in declined
            and "still and changing phases" not in declined and "STOPPED" in declined,
            f"16 ran the still phase after the operator said the desktop is not shown: {declined}")

    # 2026-10-12 on the Nitro: the installed shell predated ADR 0045 and the
    # pane had no Restart capture; the step failed twice and stopped the
    # group. A pane without the button is reported N/A, counted apart, and
    # the group ends without a failure.
    absent, _ = run_16_phases(phase_files(), answers={
        "Type 'rebuild'": "rebuild", "Type 'restart'": "restart",
        "Does Looking Glass show dev-01's desktop": "y", "Is there NO '8;10u'": "y",
        "Does dev-01's Machine pane offer Restart capture": "n", "Type 'pane'": "no"})
    require("N/A   Restart capture from the pane: the Machine pane does not offer it; "
            "the installed shell may predate ADR 0045" in absent,
            f"16 does not say the pane has no Restart capture: {absent}")
    require("FAIL" not in absent and "STOP  use Restart capture" not in absent and "STOPPED" not in absent,
            f"a pane without Restart capture failed or stopped 16: {absent}")
    require(absent.rstrip().endswith("0 failed, 0 skipped, 1 not available"),
            f"16's summary does not count the missing button apart: {absent}")
    unclear, _ = run_16_phases(phase_files(), answers={
        "Type 'rebuild'": "rebuild", "Type 'restart'": "restart",
        "Does Looking Glass show dev-01's desktop": "y", "Is there NO '8;10u'": "y",
        "Does dev-01's Machine pane offer Restart capture": "", "Type 'pane'": "no"})
    require("FAIL  Restart capture from the pane (operator: neither y nor n)" in unclear
            and "N/A" not in unclear and "STOP  use Restart capture" not in unclear and "STOPPED" in unclear,
            f"an answer other than n was taken as a pane without Restart capture: {unclear}")


def check_12_run() -> None:
    # ADR 0039: the ring over a fullscreen Looking Glass window and over a
    # fullscreen SPICE console, never over a fullscreen host window.
    report = run_in_terminal("12-fullscreen-ring.sh", {"grim": "#!/bin/sh\nexit 1\n"}, {}, {"[y/n]": "y"})
    steps = ["PASS  ring around the fullscreen guest (operator)",
             "PASS  no ring for the host (operator)",
             "hyperlabctl open console dev-01",
             "PASS  ring around the fullscreen SPICE console (operator)",
             "group 12-fullscreen-ring: 4 passed, 0 failed, 0 skipped"]
    found = [report.find(step) for step in steps]
    require(found[3] >= 0, f"12 does not check the ring over a fullscreen SPICE console: {report}")
    require(all(f >= 0 for f in found) and found == sorted(found),
            f"12's steps are missing or out of order: {report}")
    require("close Looking Glass" in report[found[1]:found[2]],
            f"12 opens the console without closing Looking Glass first: {report}")


def check_16_runs() -> None:
    identity = load_identity()
    stale = good_probe(identity, binary="")
    answers = {"Type 'rebuild'": "rebuild", "Type 'restart'": "restart", "[y/n]": "y"}
    failed = run_16(2, stale, answers)
    require("FAIL  sender playbook" in failed and "STOPPED" in failed, f"a failed playbook did not stop 16: {failed}")
    require("(operator)" not in failed and "STOP  restart" not in failed,
            f"16 went on after a failed playbook: {failed}")
    wrong = run_16(0, stale, answers)
    require("PASS  sender playbook" in wrong and "FAIL  the running sender is this build" in wrong,
            f"16 accepted a sender that is not this build: {wrong}")
    require("(operator)" not in wrong and "STOPPED" in wrong, f"16 asked the operator after a wrong sender: {wrong}")


def main() -> int:
    check_sender_phases()
    check_16_phases_run()
    check_12_run()
    check_no_hostname_command()
    check_scripts()
    check_library()
    check_library_runs()
    check_failed_playbook_report()
    check_fail_closed()
    check_fail_closed_runs()
    check_dirty_header()
    check_machine_playbooks()
    check_sender_identity()
    check_16_runs()
    check_tcp_probe()
    check_07_runs()
    check_00_status()
    check_11_allowed_count()
    check_10_entries()
    print("Acceptance scripts contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
