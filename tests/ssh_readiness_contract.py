#!/usr/bin/env python3
# SSH-backed open actions must absorb only the bounded cold-start race.

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OPEN = ROOT / "tools/hyperlabctl/hyperlabctl/commands/open.py"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    source = OPEN.read_text(encoding="utf-8")

    require("import time\n" in source, "readiness gate lacks monotonic timing")
    require(
        "_SSH_READY_TIMEOUT_SECONDS = 30.0" in source,
        "SSH readiness deadline is not pinned to the reviewed bound",
    )
    require(
        "_SSH_READY_PROBE_TIMEOUT_SECONDS = 2.0" in source,
        "individual SSH readiness probes are not bounded",
    )
    require(
        "_SSH_READY_RETRY_SECONDS = 0.5" in source,
        "SSH readiness retry cadence drifted",
    )

    start = source.index("def _wait_for_ssh_ready(ssh_argv, domain):")
    end = source.index("\n\ndef _require_running_vfio", start)
    helper = source[start:end]

    for marker in (
        "time.monotonic()",
        '"ConnectTimeout=1"',
        '"ConnectionAttempts=1"',
        '"-T"',
        '"true"',
        "subprocess.TimeoutExpired",
        "time.sleep(min(_SSH_READY_RETRY_SECONDS, remaining))",
        "_SSH_TRANSIENT_ERRORS",
    ):
        require(marker in helper, "readiness helper missing boundary: %s" % marker)

    for marker in (
        '"connection refused"',
        '"connection timed out"',
        '"operation timed out"',
        '"no route to host"',
        '"network is unreachable"',
        '"connection reset by peer"',
        '"connection closed by"',
    ):
        require(marker in source, "transient SSH error set missing: %s" % marker)

    for permanent_failure in (
        "permission denied",
        "host key verification failed",
        "remote host identification has changed",
    ):
        require(
            permanent_failure not in helper,
            "permanent SSH trust/auth failure was made retryable: %s"
            % permanent_failure,
        )

    ssh_branch_start = source.index('elif args.open_action == "ssh":')
    ssh_branch_end = source.index("\n        else:", ssh_branch_start)
    ssh_branch = source[ssh_branch_start:ssh_branch_end]
    require(
        "_wait_for_ssh_ready(ssh_argv, args.domain)" in ssh_branch,
        "interactive SSH opens before the guest SSH service is ready",
    )
    require(
        ssh_branch.index("_wait_for_ssh_ready")
        < ssh_branch.index('"foot"'),
        "interactive terminal starts before the readiness gate",
    )

    lg_start = source.index("def _prepare_linux_looking_glass(ctx, domain):")
    lg_end = source.index("\n\nclass OpenCommand", lg_start)
    lg_prepare = source[lg_start:lg_end]
    require(
        "_wait_for_ssh_ready(ssh_argv, domain)" in lg_prepare,
        "Linux Looking Glass bypasses the shared SSH readiness gate",
    )
    require(
        lg_prepare.index("_wait_for_ssh_ready")
        < lg_prepare.index("subprocess.run("),
        "Looking Glass remote preparation races sshd",
    )

    require(
        "ansible-playbook" not in helper,
        "SSH readiness bypasses the authoritative inventory/CLI boundary",
    )

    print("SSH cold-start readiness contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
