"Adversarial V4.3 regressions for durable fullscreen operations."

import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from harness import check, equals
from hyperlabctl.commands import vm
from hyperlabctl.errors import Unavailable


def _write_executable(path, content):
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _dispatches(path):
    return len(
        [
            line
            for line in path.read_text(encoding="utf-8").splitlines()
            if line
        ]
    )


def _fake_environment(root, initial_mode=0, behavior="normal"):
    runtime = root / "runtime"
    bindir = root / "bin"
    runtime.mkdir(mode=0o700)
    bindir.mkdir()

    state = root / "state"
    behavior_file = root / "behavior"
    count = root / "dispatch-count"
    state.write_text(str(initial_mode), encoding="utf-8")
    behavior_file.write_text(behavior, encoding="utf-8")
    count.write_text("", encoding="utf-8")

    _write_executable(
        bindir / "pgrep",
        "#!/bin/sh\nprintf '4242\\n'\n",
    )

    hyprctl = r"""#!/usr/bin/env python3
import json
import os
import pathlib
import signal
import sys

state = pathlib.Path(os.environ["HL43_STATE"])
behavior_file = pathlib.Path(os.environ["HL43_BEHAVIOR"])
count = pathlib.Path(os.environ["HL43_COUNT"])
args = sys.argv[1:]
behavior = behavior_file.read_text().strip()

if args == ["instances", "-j"]:
    print(json.dumps([{
        "pid": 4242,
        "instance": "test-instance",
        "wl_socket": "wayland-test",
    }]))
    raise SystemExit(0)

if args == ["activewindow", "-j"]:
    print(json.dumps({
        "address": "0xabc",
        "stableId": "18000001",
        "fullscreen": int(state.read_text()),
    }))
    raise SystemExit(0)

if args == ["clients", "-j"]:
    if behavior == "query_fail":
        raise SystemExit(9)
    if behavior == "target_missing":
        print("[]")
        raise SystemExit(0)
    mode = int(state.read_text())
    if behavior == "state_flip":
        mode = 0
    print(json.dumps([{
        "address": "0xabc",
        "stableId": "18000001",
        "fullscreen": mode,
    }]))
    raise SystemExit(0)

if len(args) == 2 and args[0] == "dispatch":
    expression = args[1]
    with count.open("a", encoding="utf-8") as handle:
        handle.write("1\n")

    if 'window = "stableid:18000001"' not in expression:
        raise SystemExit(20)
    if 'action = "set"' in expression:
        desired_mode = 2
    elif 'action = "unset"' in expression:
        desired_mode = 0
    elif 'action = "toggle"' in expression:
        desired_mode = 0 if int(state.read_text()) in (2, 3) else 2
    else:
        raise SystemExit(21)

    if behavior == "apply_query_fail":
        state.write_text(str(desired_mode), encoding="utf-8")
        behavior_file.write_text("query_fail", encoding="utf-8")
        print("ok")
        raise SystemExit(0)

    if behavior == "apply_nonzero":
        state.write_text(str(desired_mode), encoding="utf-8")
        raise SystemExit(7)

    if behavior == "kill_parent_after_apply":
        state.write_text(str(desired_mode), encoding="utf-8")
        os.kill(os.getppid(), signal.SIGKILL)
        raise SystemExit(0)

    state.write_text(str(desired_mode), encoding="utf-8")
    print("ok")
    raise SystemExit(0)

raise SystemExit(22)
"""
    _write_executable(bindir / "hyprctl", hyprctl)

    env = os.environ.copy()
    env["PATH"] = str(bindir) + os.pathsep + "/usr/bin:/bin"
    env["XDG_RUNTIME_DIR"] = str(runtime)
    env["HL43_STATE"] = str(state)
    env["HL43_BEHAVIOR"] = str(behavior_file)
    env["HL43_COUNT"] = str(count)
    return env, state, behavior_file, count, runtime


def _run(env, operation_id, requested, timeout=8.0):
    return subprocess.run(
        [
            sys.executable,
            "-c",
            vm._GUEST_FULLSCREEN_TRANSACTION,
            operation_id,
            requested,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
        env=env,
    )


def _receipt(
    operation_id,
    requested="on",
    before_mode=0,
    after_mode=2,
    desired=1,
    transition_required=1,
):
    return (
        json.dumps(
            {
                "operation_id": operation_id,
                "status": "success",
                "address": "0xabc",
                "before_mode": before_mode,
                "after_mode": after_mode,
                "requested": requested,
                "desired": desired,
                "transition_required": transition_required,
                "failure": None,
            },
            sort_keys=True,
        )
        + "\n"
    )


def test_v43_uncertain_same_id_never_redispatches():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v43-replay-") as temp:
        env, state, behavior, count, _runtime = _fake_environment(
            Path(temp),
            initial_mode=0,
            behavior="apply_query_fail",
        )
        operation_id = "4" * 32

        first = _run(env, operation_id, "on")

        equals("v43_replay_first_rc", first.returncode, 2)
        equals("v43_replay_first_dispatches", _dispatches(count), 1)
        equals("v43_replay_applied_state", int(state.read_text()), 2)

        first_payload = vm._parse_fullscreen_receipt(
            first.stdout,
            operation_id,
            "on",
        )

        equals(
            "v43_replay_first_failure",
            first_payload["failure"],
            "POST_DISPATCH_QUERY_FAILED",
        )

        second = _run(env, operation_id, "on")

        equals("v43_replay_second_rc", second.returncode, 2)
        equals("v43_replay_no_redispatch", _dispatches(count), 1)
        equals("v43_replay_same_receipt", second.stdout, first.stdout)

        behavior.write_text("normal", encoding="utf-8")

        third = _run(env, operation_id, "on")

        equals("v43_replay_third_rc", third.returncode, 2)
        equals("v43_replay_still_one_dispatch", _dispatches(count), 1)
        equals("v43_replay_terminal_receipt", third.stdout, first.stdout)



def test_v43_unresolved_operation_blocks_new_operation():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v43-block-") as temp:
        env, state, behavior, count, _runtime = _fake_environment(
            Path(temp),
            initial_mode=0,
            behavior="apply_query_fail",
        )

        first = _run(env, "5" * 32, "on")

        equals("v43_block_first_rc", first.returncode, 2)
        equals("v43_block_first_dispatches", _dispatches(count), 1)
        equals("v43_block_first_state", int(state.read_text()), 2)

        # A synchronously completed request with a lost immediate observation
        # becomes a terminal failure receipt, not an UNKNOWN operation barrier.
        behavior.write_text("normal", encoding="utf-8")

        second = _run(env, "6" * 32, "off")

        equals("v43_block_second_rc", second.returncode, 0)
        equals("v43_block_dispatches", _dispatches(count), 2)
        equals("v43_block_final_state", int(state.read_text()), 0)



def test_v43_crash_after_dispatch_never_replays_mutation():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v43-crash-") as temp:
        env, state, behavior, count, runtime = _fake_environment(
            Path(temp),
            initial_mode=0,
            behavior="kill_parent_after_apply",
        )
        operation_id = "7" * 32

        first = _run(env, operation_id, "on")
        check(
            "v43_crash_first_not_success",
            first.returncode != 0,
            "rc=%r" % first.returncode,
        )
        equals("v43_crash_state_applied", int(state.read_text()), 2)
        equals("v43_crash_dispatches_once", _dispatches(count), 1)

        behavior.write_text("normal", encoding="utf-8")
        replay = _run(env, operation_id, "on")
        equals("v43_crash_replay_stays_unknown", replay.returncode, 75)
        equals("v43_crash_no_redispatch", _dispatches(count), 1)
        receipt = (
            runtime
            / "hyperlab-fullscreen"
            / "receipts"
            / (operation_id + ".json")
        )
        check("v43_crash_no_false_receipt", not receipt.exists())


def test_v43_apply_then_nonzero_remains_unknown():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v43-nonzero-") as temp:
        env, state, _behavior, count, runtime = _fake_environment(
            Path(temp),
            initial_mode=0,
            behavior="apply_nonzero",
        )
        operation_id = "8" * 32
        result = _run(env, operation_id, "on")

        equals("v43_nonzero_rc", result.returncode, 75)
        equals("v43_nonzero_state", int(state.read_text()), 2)
        equals("v43_nonzero_dispatches", _dispatches(count), 1)

        unknown = vm._parse_fullscreen_unknown(
            result.stdout,
            operation_id,
        )
        equals(
            "v43_nonzero_reason",
            unknown["reason"],
            "FULLSCREEN_DISPATCH_UNACKNOWLEDGED",
        )
        equals(
            "v43_nonzero_blocker",
            unknown["blocking_operation_id"],
            operation_id,
        )

        receipt = (
            runtime
            / "hyperlab-fullscreen"
            / "receipts"
            / (operation_id + ".json")
        )
        operation = (
            runtime
            / "hyperlab-fullscreen"
            / "operations"
            / (operation_id + ".json")
        )

        check("v43_nonzero_no_terminal_receipt", not receipt.exists())
        check("v43_nonzero_barrier_persisted", operation.exists())


def test_v43_noop_target_loss_is_never_false_success():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v43-loss-") as temp:
        env, _state, _behavior, count, _runtime = _fake_environment(
            Path(temp),
            initial_mode=2,
            behavior="target_missing",
        )
        result = _run(env, "9" * 32, "on")

        equals("v43_noop_loss_rc", result.returncode, 2)
        equals("v43_noop_loss_dispatches", _dispatches(count), 0)
        check(
            "v43_noop_loss_failure",
            '"status":"failure"' in result.stdout,
            result.stdout,
        )


def test_v43_noop_state_change_is_never_false_success():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v43-drift-") as temp:
        env, _state, _behavior, count, _runtime = _fake_environment(
            Path(temp),
            initial_mode=2,
            behavior="state_flip",
        )
        result = _run(env, "a" * 32, "on")

        equals("v43_noop_drift_rc", result.returncode, 2)
        equals("v43_noop_drift_dispatches", _dispatches(count), 0)
        check(
            "v43_noop_drift_failure",
            '"failure":"PREPARED_STATE_DRIFT"' in result.stdout,
            result.stdout,
        )


def test_v43_host_reconciliation_rejects_late_success():
    operation_id = "b" * 32
    original_run = vm._run_fullscreen_receipt_remote
    original_window = vm._GUEST_FULLSCREEN_RECEIPT_RECONCILE_SECONDS
    original_poll = vm._GUEST_FULLSCREEN_RECEIPT_POLL_SECONDS
    observed_timeouts = []

    class Result:
        returncode = 0
        stdout = _receipt(operation_id)
        stderr = ""

    def late_read(_argv, _operation_id, timeout):
        observed_timeouts.append(timeout)
        time.sleep(0.03)
        return Result()

    vm._run_fullscreen_receipt_remote = late_read
    vm._GUEST_FULLSCREEN_RECEIPT_RECONCILE_SECONDS = 0.01
    vm._GUEST_FULLSCREEN_RECEIPT_POLL_SECONDS = 0.001
    try:
        try:
            vm._reconcile_fullscreen_receipt(
                ["ssh", "example"],
                "demo",
                operation_id,
                "on",
                "test",
            )
        except Unavailable:
            check("v43_late_receipt_rejected", True)
        else:
            check(
                "v43_late_receipt_rejected",
                False,
                "late receipt was accepted",
            )
    finally:
        vm._run_fullscreen_receipt_remote = original_run
        vm._GUEST_FULLSCREEN_RECEIPT_RECONCILE_SECONDS = original_window
        vm._GUEST_FULLSCREEN_RECEIPT_POLL_SECONDS = original_poll

    check(
        "v43_host_timeout_has_no_100ms_floor",
        bool(observed_timeouts) and observed_timeouts[0] <= 0.011,
        repr(observed_timeouts),
    )
