# Behavioral tests for the managed guest fullscreen transaction.

import io
import json
import os
import stat
import subprocess
import sys
import tempfile
from contextlib import contextmanager, redirect_stdout
from pathlib import Path
from types import SimpleNamespace

from harness import check, equals
from hyperlabctl.commands import vm
from hyperlabctl.errors import Unavailable


class Result:
    def __init__(self, rc=0, stdout="", stderr=""):
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


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


def _expect_unavailable(name, callback, contains=None):
    try:
        callback()
    except Unavailable as exc:
        if contains is not None:
            check(name + "_message", contains in str(exc), str(exc))
        check(name, True)
    else:
        check(name, False, "expected Unavailable")


@contextmanager
def _runtime(run_transaction, read_receipt=None):
    original_require = vm._require_running_domain
    original_ssh_argv = vm._ssh_argv
    original_wait = vm._wait_for_ssh_ready
    original_run = vm._run_fullscreen_remote
    original_read = vm._run_fullscreen_receipt_remote
    original_token = vm.secrets.token_hex
    original_window = vm._GUEST_FULLSCREEN_RECEIPT_RECONCILE_SECONDS
    original_poll = vm._GUEST_FULLSCREEN_RECEIPT_POLL_SECONDS

    vm._require_running_domain = lambda _ctx, _domain: None
    vm._ssh_argv = lambda _ctx, _domain: ["ssh", "demo@example.invalid"]
    vm._wait_for_ssh_ready = lambda _argv, _domain: None
    vm._run_fullscreen_remote = run_transaction
    vm._run_fullscreen_receipt_remote = (
        read_receipt if read_receipt is not None else lambda *_args: Result(rc=44)
    )
    vm.secrets.token_hex = lambda _size: "a" * 32
    vm._GUEST_FULLSCREEN_RECEIPT_RECONCILE_SECONDS = 0.02
    vm._GUEST_FULLSCREEN_RECEIPT_POLL_SECONDS = 0.001
    try:
        yield
    finally:
        vm._require_running_domain = original_require
        vm._ssh_argv = original_ssh_argv
        vm._wait_for_ssh_ready = original_wait
        vm._run_fullscreen_remote = original_run
        vm._run_fullscreen_receipt_remote = original_read
        vm.secrets.token_hex = original_token
        vm._GUEST_FULLSCREEN_RECEIPT_RECONCILE_SECONDS = original_window
        vm._GUEST_FULLSCREEN_RECEIPT_POLL_SECONDS = original_poll


def _invoke(run_transaction, state="toggle", read_receipt=None):
    args = SimpleNamespace(domain="demo", state=state)
    output = io.StringIO()
    with _runtime(run_transaction, read_receipt), redirect_stdout(output):
        rc = vm.VmCommand()._guest_fullscreen(args, object())
    return rc, output.getvalue()


def test_guest_fullscreen_accepts_exact_terminal_success_receipt():
    def run_transaction(_argv, operation_id, requested, _timeout):
        equals("operation_id_bound", operation_id, "a" * 32)
        equals("requested_bound", requested, "toggle")
        return Result(stdout=_receipt())

    rc, output = _invoke(run_transaction)
    equals("terminal_success_rc", rc, 0)
    check("terminal_success_not_reconciled", '"reconciled": 0' in output)
    check("terminal_success_mode_preserved", '"after_mode": 2' in output)


def test_guest_fullscreen_timeout_requires_exact_terminal_receipt():
    def run_transaction(*_args):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=1)

    def read_receipt(_argv, operation_id, _timeout):
        return Result(
            stdout=_receipt(
                operation_id=operation_id,
                before_mode=1,
                after_mode=3,
                requested="on",
                desired=1,
                transition_required=1,
            )
        )

    rc, output = _invoke(run_transaction, "on", read_receipt)
    equals("timeout_receipt_rc", rc, 0)
    check("timeout_receipt_reconciled", '"reconciled": 1' in output)
    check("timeout_receipt_mode3_preserved", '"after_mode": 3' in output)


def test_guest_fullscreen_timeout_without_receipt_is_unknown():
    def run_transaction(*_args):
        raise subprocess.TimeoutExpired(cmd="ssh", timeout=1)

    _expect_unavailable(
        "timeout_without_receipt_unknown",
        lambda: _invoke(run_transaction),
        "UNKNOWN",
    )


def test_guest_fullscreen_terminal_failure_receipt_is_refused():
    def run_transaction(*_args):
        return Result(rc=2)

    def read_receipt(_argv, operation_id, _timeout):
        return Result(
            stdout=_receipt(
                operation_id=operation_id,
                status="failure",
                address=None,
                before_mode=None,
                after_mode=None,
                desired=None,
                transition_required=None,
                failure="LOCK_BUSY",
            )
        )

    _expect_unavailable(
        "terminal_failure_refused",
        lambda: _invoke(run_transaction, read_receipt=read_receipt),
        "LOCK_BUSY",
    )


def test_guest_fullscreen_non_object_json_is_refused():
    for index, raw in enumerate(("null\n", "[]\n", "1\n", '"value"\n')):
        _expect_unavailable(
            "non_object_%d" % index,
            lambda raw=raw: vm._parse_fullscreen_receipt(raw, "a" * 32, "toggle"),
        )


def test_guest_fullscreen_wrong_operation_id_is_refused():
    _expect_unavailable(
        "wrong_operation_id",
        lambda: vm._parse_fullscreen_receipt(
            _receipt(operation_id="b" * 32),
            "a" * 32,
            "toggle",
        ),
    )


def test_maximized_mode_is_not_true_fullscreen():
    check("mode_1_not_true_fullscreen", not vm._is_true_fullscreen(1))
    check("mode_2_true_fullscreen", vm._is_true_fullscreen(2))
    check("mode_3_true_fullscreen", vm._is_true_fullscreen(3))
    _expect_unavailable(
        "maximized_not_accepted_for_on",
        lambda: vm._parse_fullscreen_receipt(
            _receipt(
                before_mode=0,
                after_mode=1,
                requested="on",
                desired=1,
                transition_required=1,
            ),
            "a" * 32,
            "on",
        ),
    )


def _write_executable(path, content):
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _run_fake_guest_transaction(initial_mode, requested, operation_id):
    with tempfile.TemporaryDirectory(prefix="hyperlab-fs-test-") as temp:
        root = Path(temp)
        runtime = root / "runtime"
        bindir = root / "bin"
        runtime.mkdir(mode=0o700)
        bindir.mkdir()
        state_file = root / "state"
        dispatch_log = root / "dispatch.log"
        state_file.write_text(str(initial_mode), encoding="utf-8")

        _write_executable(bindir / "pgrep", "#!/bin/sh\nprintf '4242\\n'\n")

        hyprctl = r'''#!/usr/bin/env python3
import json
import os
import pathlib
import sys

state = pathlib.Path(os.environ["HL_TEST_STATE"])
log = pathlib.Path(os.environ["HL_TEST_DISPATCH_LOG"])
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
    print(json.dumps([{"address": "0xabc", "stableId": "18000001", "fullscreen": mode}]))
    raise SystemExit(0)

if len(args) == 2 and args[0] == "dispatch":
    expression = args[1]
    log.write_text(expression, encoding="utf-8")
    if 'window = "stableid:18000001"' not in expression:
        raise SystemExit(20)
    if 'action = "set"' in expression:
        state.write_text("3" if mode == 1 else "2", encoding="utf-8")
    elif 'action = "unset"' in expression:
        state.write_text("1" if mode == 3 else "0", encoding="utf-8")
    else:
        raise SystemExit(21)
    print("ok")
    raise SystemExit(0)

raise SystemExit(22)
'''
        _write_executable(bindir / "hyprctl", hyprctl)

        env = os.environ.copy()
        env["PATH"] = str(bindir) + os.pathsep + "/usr/bin:/bin"
        env["XDG_RUNTIME_DIR"] = str(runtime)
        env["HL_TEST_STATE"] = str(state_file)
        env["HL_TEST_DISPATCH_LOG"] = str(dispatch_log)

        result = subprocess.run(
            [sys.executable, "-c", vm._GUEST_FULLSCREEN_TRANSACTION, operation_id, requested],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=5.0,
            env=env,
        )

        expression = dispatch_log.read_text(encoding="utf-8") if dispatch_log.exists() else ""
        final_mode = int(state_file.read_text(encoding="utf-8"))
        return result, expression, final_mode


def test_remote_transaction_targets_address_and_sets_from_maximized():
    operation_id = "c" * 32
    result, expression, final_mode = _run_fake_guest_transaction(1, "on", operation_id)
    equals("fake_set_rc", result.returncode, 0)
    payload = vm._parse_fullscreen_receipt(result.stdout, operation_id, "on")
    equals("fake_set_before_mode", payload["before_mode"], 1)
    equals("fake_set_after_mode", payload["after_mode"], 3)
    equals("fake_set_final_mode", final_mode, 3)
    check("fake_set_address_bound", 'window = "stableid:18000001"' in expression)
    check("fake_set_explicit", 'action = "set"' in expression)
    check("fake_set_fullscreen_mode", 'mode = "fullscreen"' in expression)
    check("fake_set_never_focuses", "focuswindow" not in expression)


def test_remote_transaction_unsets_fullscreen_without_losing_maximized():
    operation_id = "d" * 32
    result, expression, final_mode = _run_fake_guest_transaction(3, "off", operation_id)
    equals("fake_unset_rc", result.returncode, 0)
    payload = vm._parse_fullscreen_receipt(result.stdout, operation_id, "off")
    equals("fake_unset_before_mode", payload["before_mode"], 3)
    equals("fake_unset_after_mode", payload["after_mode"], 1)
    equals("fake_unset_final_mode", final_mode, 1)
    check("fake_unset_address_bound", 'window = "stableid:18000001"' in expression)
    check("fake_unset_explicit", 'action = "unset"' in expression)


def test_receipt_rejects_unexpected_fields_and_invalid_modes():
    payload = json.loads(_receipt())
    payload["extra"] = "not allowed"
    _expect_unavailable(
        "unexpected_receipt_field",
        lambda: vm._parse_fullscreen_receipt(json.dumps(payload), "a" * 32, "toggle"),
    )
    _expect_unavailable(
        "boolean_mode_refused",
        lambda: vm._parse_fullscreen_receipt(
            _receipt(before_mode=True),
            "a" * 32,
            "toggle",
        ),
    )
