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
     (problems/acceptance-report-hid-a-dirty-tree.md).
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
import tempfile
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


def main() -> int:
    check_no_hostname_command()
    check_scripts()
    check_library()
    check_library_runs()
    check_failed_playbook_report()
    check_fail_closed()
    check_fail_closed_runs()
    check_dirty_header()
    print("Acceptance scripts contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
