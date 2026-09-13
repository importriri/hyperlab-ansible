#!/usr/bin/env python3
"""Unprivileged client for transactional HyperLab Gaming Mode."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys


CONFIG = Path("/etc/privatestack/host-gaming-mode.json")
STATE = Path("/run/hyperlab-gaming-mode/state.json")
ROOT_HELPER = "/usr/local/libexec/hyperlab-gaming-mode-root"


class ClientError(RuntimeError):
    """A local client contract failure."""


def load_config() -> dict[str, object]:
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ClientError(f"cannot read Gaming Mode config: {exc}") from exc

    if data.get("schema_version") != 1:
        raise ClientError("unsupported Gaming Mode schema")

    operator = pwd.getpwuid(os.getuid()).pw_name

    if data.get("operator_user") != operator:
        raise ClientError(
            f"Gaming Mode is delegated to {data.get('operator_user')!r}, "
            f"not {operator!r}"
        )

    return data


def validate_installation() -> dict[str, object]:
    config = load_config()
    helper = Path(ROOT_HELPER)

    if not helper.is_file() or helper.is_symlink():
        raise ClientError("root helper is unavailable or unsafe")

    if not os.access(helper, os.X_OK):
        raise ClientError("root helper is not executable")

    return config


def sudo_validate() -> None:
    result = subprocess.run(
        ["sudo", "-v"],
        check=False,
    )

    if result.returncode != 0:
        raise ClientError("sudo validation failed")


def print_guard_line(line: str) -> dict[str, object] | None:
    print(line, end="")

    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        return None

    if isinstance(data, dict):
        return data

    return None


def run_workload(command: list[str]) -> int:
    validate_installation()

    if not command:
        raise ClientError("run requires a workload command")

    if command[0] == "--":
        command = command[1:]

    if not command:
        raise ClientError("run requires a workload command")

    sudo_validate()

    guard = subprocess.Popen(
        ["sudo", "-n", ROOT_HELPER, "guard"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )

    if guard.stdin is None or guard.stdout is None:
        guard.kill()
        raise ClientError("cannot establish root guard pipes")

    ready = False

    while True:
        line = guard.stdout.readline()

        if not line:
            break

        data = print_guard_line(line)

        if data and data.get("event") == "ready":
            ready = True
            break

        if data and data.get("event") in {
            "error",
            "apply-failure",
            "restore",
        }:
            break

    if not ready:
        guard.stdin.close()

        for line in guard.stdout:
            print_guard_line(line)

        guard_rc = guard.wait()

        raise ClientError(
            f"Gaming Mode guard did not become ready (rc={guard_rc})"
        )

    workload_rc = 125

    try:
        result = subprocess.run(
            command,
            check=False,
        )
        workload_rc = result.returncode
    except KeyboardInterrupt:
        workload_rc = 130
    finally:
        guard.stdin.close()

        for line in guard.stdout:
            print_guard_line(line)

        guard_rc = guard.wait()

    if guard_rc != 0:
        raise ClientError(
            f"Gaming Mode restore failed or guard exited rc={guard_rc}"
        )

    return workload_rc


def recover() -> int:
    validate_installation()
    sudo_validate()

    result = subprocess.run(
        ["sudo", "-n", ROOT_HELPER, "recover"],
        check=False,
    )

    return result.returncode


def status() -> int:
    config = validate_installation()

    data: dict[str, object] = {
        "schema_version": 1,
        "policy": "transactional-runtime-only",
        "active_or_stale": STATE.exists(),
        "epp": config["epp"],
        "allowed_cpus": config["allowed_cpus"],
        "domain": config["domain"],
    }

    if STATE.exists():
        try:
            state = json.loads(STATE.read_text(encoding="utf-8"))
            data["guard_pid"] = state.get("guard_pid")
        except (OSError, json.JSONDecodeError):
            data["state_readable"] = False

    print(json.dumps(data, sort_keys=True))
    return 0


def self_test() -> int:
    config = validate_installation()

    print(
        json.dumps(
            {
                "event": "self-test",
                "ok": True,
                "schema_version": config["schema_version"],
                "privilege": "sudo-on-activation",
                "persistence": "runtime-only",
            },
            sort_keys=True,
        )
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="HyperLab transactional Gaming Mode"
    )
    subparsers = parser.add_subparsers(
        dest="operation",
        required=True,
    )

    run_parser = subparsers.add_parser(
        "run",
        help="run one workload inside the measured host Gaming Mode",
    )
    run_parser.add_argument(
        "command",
        nargs=argparse.REMAINDER,
    )

    subparsers.add_parser(
        "status",
        help="show whether a transaction is active or stale",
    )
    subparsers.add_parser(
        "recover",
        help="restore a stale transaction",
    )
    subparsers.add_parser(
        "self-test",
        help="validate the installed client contract",
    )

    args = parser.parse_args()

    try:
        if args.operation == "run":
            return run_workload(args.command)

        if args.operation == "status":
            return status()

        if args.operation == "recover":
            return recover()

        return self_test()
    except (ClientError, OSError, KeyError, ValueError) as exc:
        print(f"hyperlab-gaming-mode: {exc}", file=sys.stderr)
        return 64


if __name__ == "__main__":
    raise SystemExit(main())
