'Adversarial V4.2 tests for the managed fullscreen transaction.'

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


def _receipt(
    operation_id="a" * 32,
    status="success",
    address="0xabc",
    before_mode=0,
    after_mode=2,
    requested="toggle",
    desired=1,
    transition_required=1,
    failure=None,
):
    return json.dumps(
        {
            "operation_id": operation_id,
            "status": status,
            "address": address,
            "before_mode": before_mode,
            "after_mode": after_mode,
            "requested": requested,
            "desired": desired,
            "transition_required": transition_required,
            "failure": failure,
        },
        sort_keys=True,
    ) + "\n"


def _expect_unavailable(name, callback):
    try:
        callback()
    except Unavailable:
        check(name, True)
    else:
        check(name, False, "expected Unavailable")


def _write_executable(path, content):
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _fake_environment(root, initial_mode=0, behavior="normal", hold=0.0):
    runtime = root / "runtime"
    bindir = root / "bin"
    runtime.mkdir(mode=0o700)
    bindir.mkdir()
    state_file = root / "state"
    dispatch_count = root / "dispatch-count"
    dispatch_log = root / "dispatch.log"
    state_file.write_text(str(initial_mode), encoding="utf-8")
    dispatch_count.write_text("", encoding="utf-8")

    _write_executable(bindir / "pgrep", "#!/bin/sh\nprintf '4242\\n'\n")

    hyprctl = r'''#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys
import time

state = pathlib.Path(os.environ["HL_TEST_STATE"])
count = pathlib.Path(os.environ["HL_TEST_COUNT"])
log = pathlib.Path(os.environ["HL_TEST_DISPATCH_LOG"])
behavior = os.environ.get("HL_TEST_BEHAVIOR", "normal")
hold = float(os.environ.get("HL_TEST_HOLD", "0"))
args = sys.argv[1:]

if args == ["instances", "-j"]:
    print(json.dumps([{
        "pid": 4242,
        "instance": "test-instance",
        "wl_socket": "wayland-test",
    }]))
    raise SystemExit(0)

mode = int(state.read_text())

if args == ["activewindow", "-j"]:
    print(json.dumps({"address": "0xabc", "stableId": "18000001", "fullscreen": mode}))
    raise SystemExit(0)

if args == ["clients", "-j"]:
    if behavior == "slow_noapply":
        time.sleep(0.8)
    print(json.dumps([{
        "address": "0xabc",
        "stableId": "18000001",
        "fullscreen": int(state.read_text()),
    }]))
    raise SystemExit(0)

if len(args) == 2 and args[0] == "dispatch":
    expression = args[1]
    log.write_text(expression, encoding="utf-8")
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

    if behavior == "timeout_delayed":
        code = (
            "import pathlib,time;"
            "time.sleep(5.0);"
            "pathlib.Path(%r).write_text(%r)"
            % (str(state), str(desired_mode))
        )
        subprocess.Popen(
            [sys.executable, "-c", code],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        time.sleep(3.0)
        raise SystemExit(0)

    if behavior != "slow_noapply":
        state.write_text(str(desired_mode), encoding="utf-8")

    if behavior == "timeout_applied":
        time.sleep(3.0)
    elif hold:
        time.sleep(hold)

    print("ok")
    raise SystemExit(0)

raise SystemExit(22)
'''
    _write_executable(bindir / "hyprctl", hyprctl)

    env = os.environ.copy()
    env["PATH"] = str(bindir) + os.pathsep + "/usr/bin:/bin"
    env["XDG_RUNTIME_DIR"] = str(runtime)
    env["HL_TEST_STATE"] = str(state_file)
    env["HL_TEST_COUNT"] = str(dispatch_count)
    env["HL_TEST_DISPATCH_LOG"] = str(dispatch_log)
    env["HL_TEST_BEHAVIOR"] = behavior
    env["HL_TEST_HOLD"] = str(hold)
    return env, state_file, dispatch_count, runtime


def _run_transaction(env, operation_id, requested, timeout=8.0):
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


def _dispatches(path):
    return len([line for line in path.read_text(encoding="utf-8").splitlines() if line])


def test_v42_receipt_rejects_requested_state_contradictions():
    contradictory = (
        (
            "on",
            _receipt(
                requested="on",
                before_mode=0,
                after_mode=0,
                desired=0,
                transition_required=0,
            ),
        ),
        (
            "off",
            _receipt(
                requested="off",
                before_mode=2,
                after_mode=2,
                desired=1,
                transition_required=0,
            ),
        ),
        (
            "toggle",
            _receipt(
                requested="toggle",
                before_mode=0,
                after_mode=0,
                desired=0,
                transition_required=0,
            ),
        ),
    )
    for index, (requested, raw) in enumerate(contradictory):
        _expect_unavailable(
            "v42_contradictory_%d" % index,
            lambda requested=requested, raw=raw: vm._parse_fullscreen_receipt(
                raw,
                "a" * 32,
                requested,
            ),
        )


def test_v42_duplicate_operation_id_is_sequentially_idempotent():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v42-seq-") as temp:
        env, state, count, _runtime = _fake_environment(Path(temp), initial_mode=0)
        operation_id = "e" * 32
        first = _run_transaction(env, operation_id, "toggle")
        second = _run_transaction(env, operation_id, "toggle")

        equals("v42_seq_first_rc", first.returncode, 0)
        equals("v42_seq_second_rc", second.returncode, 0)
        equals("v42_seq_same_receipt", second.stdout, first.stdout)
        equals("v42_seq_dispatches", _dispatches(count), 1)
        equals("v42_seq_state", int(state.read_text()), 2)


def test_v42_duplicate_operation_id_is_concurrently_idempotent():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v42-concurrent-") as temp:
        env, state, count, _runtime = _fake_environment(
            Path(temp), initial_mode=0, hold=0.3
        )
        operation_id = "f" * 32
        argv = [
            sys.executable,
            "-c",
            vm._GUEST_FULLSCREEN_TRANSACTION,
            operation_id,
            "toggle",
        ]
        first = subprocess.Popen(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        second = subprocess.Popen(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        first_out, first_err = first.communicate(timeout=8.0)
        second_out, second_err = second.communicate(timeout=8.0)

        equals("v42_concurrent_first_rc", first.returncode, 0)
        equals("v42_concurrent_second_rc", second.returncode, 0)
        equals("v42_concurrent_same_receipt", second_out, first_out)
        equals("v42_concurrent_dispatches", _dispatches(count), 1)
        equals("v42_concurrent_state", int(state.read_text()), 2)
        check("v42_concurrent_first_stderr", not first_err, first_err)
        check("v42_concurrent_second_stderr", not second_err, second_err)


def test_v42_dispatch_timeout_after_applied_mutation_remains_unknown():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v42-applied-") as temp:
        env, state, count, runtime = _fake_environment(
            Path(temp), initial_mode=0, behavior="timeout_applied"
        )
        operation_id = "1" * 32
        result = _run_transaction(env, operation_id, "on")

        equals("v42_applied_rc", result.returncode, 75)
        equals("v42_applied_dispatches", _dispatches(count), 1)
        equals("v42_applied_state", int(state.read_text()), 2)

        receipt = (
            runtime
            / "hyperlab-fullscreen"
            / "receipts"
            / (operation_id + ".json")
        )
        check("v42_applied_no_terminal_receipt", not receipt.exists())


def test_v42_dispatch_timeout_with_delayed_application_has_no_terminal_receipt():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v42-delayed-") as temp:
        env, state, count, runtime = _fake_environment(
            Path(temp), initial_mode=0, behavior="timeout_delayed"
        )
        operation_id = "2" * 32
        result = _run_transaction(env, operation_id, "on")

        equals("v42_delayed_rc", result.returncode, 75)
        receipt = (
            runtime
            / "hyperlab-fullscreen"
            / "receipts"
            / (operation_id + ".json")
        )
        check("v42_delayed_no_receipt", not receipt.exists())
        equals("v42_delayed_dispatches", _dispatches(count), 1)

        # V4.4 returns UNKNOWN as soon as the synchronous dispatch call itself
        # times out. The detached fake mutation intentionally lands later.
        deadline = time.monotonic() + 4.0
        late_state = None
        while time.monotonic() < deadline:
            raw_state = state.read_text(encoding="utf-8").strip()
            if raw_state:
                late_state = int(raw_state)
                if late_state == 2:
                    break
            time.sleep(0.05)
        equals("v42_delayed_late_state", late_state, 2)


def test_v42_poll_deadline_before_dispatch_is_terminal_failure():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v42-deadline-") as temp:
        env, _state, count, runtime = _fake_environment(
            Path(temp), initial_mode=0, behavior="slow_noapply"
        )
        operation_id = "3" * 32
        started = time.monotonic()
        result = _run_transaction(env, operation_id, "on")
        elapsed = time.monotonic() - started

        equals("v42_deadline_rc", result.returncode, 2)
        check("v42_deadline_bounded", elapsed < 3.0, "elapsed=%r" % elapsed)
        equals("v42_deadline_dispatches", _dispatches(count), 0)

        payload = vm._parse_fullscreen_receipt(
            result.stdout,
            operation_id,
            "on",
        )
        equals("v42_deadline_status", payload["status"], "failure")
        equals(
            "v42_deadline_failure",
            payload["failure"],
            "CLIENTS_QUERY_FAILED_TIMEOUT",
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

        check("v42_deadline_receipt_published", receipt.exists())
        check("v42_deadline_operation_retired", not operation.exists())
