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
     names the full log (problems/acceptance-check-log-only-recap.md).
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


def main() -> int:
    check_no_hostname_command()
    check_scripts()
    check_library()
    check_library_runs()
    check_failed_playbook_report()
    print("Acceptance scripts contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
