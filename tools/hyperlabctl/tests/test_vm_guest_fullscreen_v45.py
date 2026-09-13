"""Adversarial V4.5 stable-id and UNKNOWN recovery regressions."""

from contextlib import contextmanager, redirect_stdout
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from harness import check, equals
from hyperlabctl.commands import vm


def _write_executable(path, content):
    path.write_text(content, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _dispatch_count(path):
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
    stable_file = root / "stable-id"
    instance_file = root / "instance"
    socket_file = root / "socket"
    dispatches = root / "dispatches"

    state.write_text(str(initial_mode), encoding="utf-8")
    behavior_file.write_text(behavior, encoding="utf-8")
    stable_file.write_text("18000001", encoding="utf-8")
    instance_file.write_text("instance-a", encoding="utf-8")
    socket_file.write_text("wayland-a", encoding="utf-8")
    dispatches.write_text("", encoding="utf-8")

    _write_executable(
        bindir / "pgrep",
        "#!/bin/sh\nprintf '%s\\n' \"$HL45_SESSION_PID\"\n",
    )

    hyprctl = r"""#!/usr/bin/env python3
import json
import os
import pathlib
import signal
import subprocess
import sys

state = pathlib.Path(os.environ["HL45_STATE"])
behavior_file = pathlib.Path(os.environ["HL45_BEHAVIOR"])
stable_file = pathlib.Path(os.environ["HL45_STABLE"])
instance_file = pathlib.Path(os.environ["HL45_INSTANCE"])
socket_file = pathlib.Path(os.environ["HL45_SOCKET"])
dispatches = pathlib.Path(os.environ["HL45_DISPATCHES"])
pid = int(os.environ["HL45_SESSION_PID"])
args = sys.argv[1:]
behavior = behavior_file.read_text().strip()

if args == ["instances", "-j"]:
    print(json.dumps([{
        "pid": pid,
        "instance": instance_file.read_text().strip(),
        "wl_socket": socket_file.read_text().strip(),
    }]))
    raise SystemExit(0)

if args == ["activewindow", "-j"]:
    print(json.dumps({
        "address": "0xabc",
        "stableId": stable_file.read_text().strip(),
        "fullscreen": int(state.read_text()),
    }))
    raise SystemExit(0)

if args == ["clients", "-j"]:
    if behavior == "query_fail":
        raise SystemExit(9)
    print(json.dumps([{
        "address": "0xabc",
        "stableId": stable_file.read_text().strip(),
        "fullscreen": int(state.read_text()),
    }]))
    raise SystemExit(0)

if len(args) == 2 and args[0] == "dispatch":
    expression = args[1]
    with dispatches.open("a", encoding="utf-8") as handle:
        handle.write("1\n")

    if 'action = "set"' in expression:
        desired_mode = 2
    elif 'action = "unset"' in expression:
        desired_mode = 0
    elif 'action = "toggle"' in expression:
        desired_mode = 0 if int(state.read_text()) in (2, 3) else 2
    else:
        raise SystemExit(21)

    selected = None
    marker = 'window = "stableid:'
    if marker in expression:
        selected = expression.split(marker, 1)[1].split('"', 1)[0]

    if behavior == "reuse_before_dispatch":
        stable_file.write_text("18000002", encoding="utf-8")

    if selected != stable_file.read_text().strip():
        raise SystemExit(4)

    if behavior == "signal_delay":
        code = (
            "import pathlib,time;"
            "time.sleep(1.0);"
            "pathlib.Path(%r).write_text(%r)"
            % (str(state), str(desired_mode))
        )
        subprocess.Popen(
            [sys.executable, "-c", code],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        os.kill(os.getpid(), signal.SIGKILL)

    if behavior == "complete_then_query_fail":
        state.write_text(str(desired_mode), encoding="utf-8")
        behavior_file.write_text("query_fail", encoding="utf-8")
        print("ok")
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
    env["HL45_STATE"] = str(state)
    env["HL45_BEHAVIOR"] = str(behavior_file)
    env["HL45_STABLE"] = str(stable_file)
    env["HL45_INSTANCE"] = str(instance_file)
    env["HL45_SOCKET"] = str(socket_file)
    env["HL45_DISPATCHES"] = str(dispatches)
    env["HL45_SESSION_PID"] = str(os.getpid())
    env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
    env.pop("WAYLAND_DISPLAY", None)
    return (
        env,
        state,
        behavior_file,
        stable_file,
        instance_file,
        socket_file,
        dispatches,
        runtime,
    )


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


def _unknown(result, operation_id):
    equals("v45_unknown_rc", result.returncode, 75)
    return vm._parse_fullscreen_unknown(result.stdout, operation_id)


def _recovery(result, operation_id):
    equals("v45_recovery_rc", result.returncode, 0)
    return vm._parse_fullscreen_recovery(result.stdout, operation_id)


def test_v45_same_session_address_reuse_cannot_prove_old_window_success():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v45-reuse-") as temp:
        (
            env,
            state,
            behavior,
            stable_file,
            _instance,
            _socket,
            dispatches,
            _runtime,
        ) = _fake_environment(
            Path(temp),
            initial_mode=0,
            behavior="complete_then_query_fail",
        )

        operation_id = "a" * 32

        first = _run(env, operation_id, "on")

        equals("v45_reuse_first_rc", first.returncode, 2)
        equals("v45_reuse_state_applied", int(state.read_text()), 2)
        equals("v45_reuse_dispatches", _dispatch_count(dispatches), 1)

        first_payload = vm._parse_fullscreen_receipt(
            first.stdout,
            operation_id,
            "on",
        )

        equals(
            "v45_reuse_first_failure",
            first_payload["failure"],
            "POST_DISPATCH_QUERY_FAILED",
        )

        behavior.write_text("normal", encoding="utf-8")
        stable_file.write_text("18000002", encoding="utf-8")

        recovered = _recovery(
            _run(env, operation_id, "recover"),
            operation_id,
        )

        equals("v45_reuse_retired", recovered["recovery"], "retired")
        equals(
            "v45_reuse_not_false_success",
            recovered["receipt"]["failure"],
            "POST_DISPATCH_QUERY_FAILED",
        )
        equals("v45_reuse_no_redispatch", _dispatch_count(dispatches), 1)



def test_v45_stableid_selector_prevents_address_reuse_before_dispatch():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v45-pre-dispatch-") as temp:
        (
            env,
            state,
            _behavior,
            stable_file,
            instance_file,
            _socket,
            dispatches,
            runtime,
        ) = _fake_environment(
            Path(temp),
            initial_mode=0,
            behavior="reuse_before_dispatch",
        )
        operation_id = "b" * 32

        result = _run(env, operation_id, "on")
        unknown = _unknown(result, operation_id)
        equals(
            "v45_pre_reuse_reason",
            unknown["reason"],
            "FULLSCREEN_DISPATCH_UNACKNOWLEDGED",
        )
        equals(
            "v45_pre_reuse_blocker",
            unknown["blocking_operation_id"],
            operation_id,
        )
        equals("v45_pre_reuse_state", int(state.read_text()), 0)
        equals("v45_pre_reuse_new_identity", stable_file.read_text(), "18000002")
        equals("v45_pre_reuse_dispatch_attempts", _dispatch_count(dispatches), 1)

        operation = (
            runtime
            / "hyperlab-fullscreen"
            / "operations"
            / (operation_id + ".json")
        )
        check("v45_pre_reuse_barrier_persisted", operation.exists())

        same = _recovery(_run(env, operation_id, "recover"), operation_id)
        equals("v45_pre_reuse_same_session", same["recovery"], "still-unresolved")
        check("v45_pre_reuse_no_redispatch", _dispatch_count(dispatches), 1)

        instance_file.write_text("instance-b", encoding="utf-8")
        conflicting = _recovery(
            _run(env, operation_id, "recover"),
            operation_id,
        )
        equals(
            "v45_pre_reuse_tuple_conflict_unresolved",
            conflicting["recovery"],
            "still-unresolved",
        )
        equals(
            "v45_pre_reuse_tuple_conflict_reason",
            conflicting["reason"],
            "SESSION_DISCOVERY_AMBIGUOUS",
        )
        check(
            "v45_pre_reuse_barrier_still_present",
            operation.exists(),
        )
        equals(
            "v45_pre_reuse_no_redispatch_after_conflict",
            _dispatch_count(dispatches),
            1,
        )

        env["HL45_SESSION_PID"] = str(
            int(env["HL45_SESSION_PID"]) + 100000
        )
        retired = _recovery(
            _run(env, operation_id, "recover"),
            operation_id,
        )
        equals(
            "v45_pre_reuse_authoritative_expiry_retired",
            retired["recovery"],
            "retired",
        )
        equals(
            "v45_pre_reuse_authoritative_expiry_reason",
            retired["receipt"]["failure"],
            "SESSION_EXPIRED",
        )
        equals(
            "v45_pre_reuse_no_redispatch_after_recovery",
            _dispatch_count(dispatches),
            1,
        )
        check(
            "v45_pre_reuse_barrier_retired",
            not operation.exists(),
        )


def test_v45_signal_killed_dispatch_keeps_barrier_until_safe_recovery():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v45-signal-") as temp:
        (
            env,
            state,
            behavior,
            _stable_file,
            instance_file,
            _socket,
            dispatches,
            runtime,
        ) = _fake_environment(
            Path(temp),
            initial_mode=0,
            behavior="signal_delay",
        )
        first_id = "c" * 32
        second_id = "d" * 32

        first = _run(env, first_id, "on")
        unknown = _unknown(first, first_id)
        equals(
            "v45_signal_reason",
            unknown["reason"],
            "FULLSCREEN_DISPATCH_SIGNALLED",
        )
        equals("v45_signal_blocker", unknown["blocking_operation_id"], first_id)
        equals("v45_signal_dispatches_once", _dispatch_count(dispatches), 1)

        behavior.write_text("normal", encoding="utf-8")
        second = _run(env, second_id, "off")
        second_unknown = _unknown(second, second_id)
        equals(
            "v45_second_reports_old_blocker",
            second_unknown["blocking_operation_id"],
            first_id,
        )
        equals(
            "v45_second_reason",
            second_unknown["reason"],
            "PREVIOUS_OPERATION_RECOVERY_REQUIRED",
        )
        equals("v45_signal_no_second_dispatch", _dispatch_count(dispatches), 1)

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and int(state.read_text()) != 2:
            time.sleep(0.05)
        equals("v45_signal_delayed_mutation_landed", int(state.read_text()), 2)

        still = _recovery(_run(env, first_id, "recover"), first_id)
        equals("v45_signal_same_session", still["recovery"], "still-unresolved")
        receipt = (
            runtime
            / "hyperlab-fullscreen"
            / "receipts"
            / (first_id + ".json")
        )
        check("v45_signal_no_false_receipt", not receipt.exists())

        instance_file.write_text("instance-b", encoding="utf-8")
        conflicting = _recovery(
            _run(env, first_id, "recover"),
            first_id,
        )
        equals(
            "v45_signal_tuple_conflict_unresolved",
            conflicting["recovery"],
            "still-unresolved",
        )
        equals(
            "v45_signal_tuple_conflict_reason",
            conflicting["reason"],
            "SESSION_DISCOVERY_AMBIGUOUS",
        )
        check(
            "v45_signal_tuple_conflict_no_receipt",
            not receipt.exists(),
        )

        env["HL45_SESSION_PID"] = str(
            int(env["HL45_SESSION_PID"]) + 100000
        )
        retired = _recovery(
            _run(env, first_id, "recover"),
            first_id,
        )
        equals(
            "v45_signal_authoritative_expiry_retired",
            retired["recovery"],
            "retired",
        )
        equals(
            "v45_signal_authoritative_expiry_reason",
            retired["receipt"]["failure"],
            "SESSION_EXPIRED",
        )

        final = _run(env, "e" * 32, "off")
        equals("v45_signal_post_recovery_rc", final.returncode, 0)
        payload = vm._parse_fullscreen_receipt(final.stdout, "e" * 32, "off")
        equals("v45_signal_post_recovery_after", payload["after_mode"], 0)
        equals("v45_signal_post_recovery_dispatches", _dispatch_count(dispatches), 2)


class Result:
    def __init__(self, rc=0, stdout="", stderr=""):
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


@contextmanager
def _patched(module, name, value):
    old = getattr(module, name)
    setattr(module, name, value)
    try:
        yield
    finally:
        setattr(module, name, old)


def test_v45_public_cli_surfaces_real_blocker_and_recovery_id():
    new_id = "f" * 32
    blocker = "1" * 32

    unknown_payload = {
        "operation_id": new_id,
        "status": "unknown",
        "reason": "PREVIOUS_OPERATION_RECOVERY_REQUIRED",
        "blocking_operation_id": blocker,
    }
    terminal = {
        "operation_id": blocker,
        "status": "success",
        "address": "0xabc",
        "before_mode": 0,
        "after_mode": 2,
        "requested": "on",
        "desired": 1,
        "transition_required": 1,
        "failure": None,
    }
    recovery_payload = {
        "operation_id": blocker,
        "recovery": "completed",
        "receipt": terminal,
        "reason": None,
    }

    def run_remote(_argv, operation_id, requested, _timeout):
        if requested == "on":
            equals("v45_public_new_id", operation_id, new_id)
            return Result(
                rc=75,
                stdout=json.dumps(unknown_payload) + "\n",
            )
        equals("v45_public_recover_id", operation_id, blocker)
        equals("v45_public_recover_mode", requested, "recover")
        return Result(
            rc=0,
            stdout=json.dumps(recovery_payload) + "\n",
        )

    args = SimpleNamespace(
        domain="demo",
        state="on",
        recover_operation=None,
    )
    output = io.StringIO()

    with (
        _patched(vm, "_require_running_domain", lambda *_args: None),
        _patched(vm, "_ssh_argv", lambda *_args: ["ssh", "demo"]),
        _patched(vm, "_wait_for_ssh_ready", lambda *_args: None),
        _patched(vm, "_run_fullscreen_remote", run_remote),
        _patched(vm.secrets, "token_hex", lambda _n: new_id),
        redirect_stdout(output),
    ):
        rc = vm.VmCommand()._guest_fullscreen(args, object())

    equals("v45_public_unknown_rc", rc, 2)
    surfaced = json.loads(output.getvalue())
    equals("v45_public_status", surfaced["status"], "unknown")
    equals("v45_public_blocker", surfaced["blocking_operation_id"], blocker)
    equals(
        "v45_public_reason",
        surfaced["reason"],
        "PREVIOUS_OPERATION_RECOVERY_REQUIRED",
    )

    args.recover_operation = blocker
    output = io.StringIO()
    with (
        _patched(vm, "_require_running_domain", lambda *_args: None),
        _patched(vm, "_ssh_argv", lambda *_args: ["ssh", "demo"]),
        _patched(vm, "_wait_for_ssh_ready", lambda *_args: None),
        _patched(vm, "_run_fullscreen_remote", run_remote),
        redirect_stdout(output),
    ):
        rc = vm.VmCommand()._guest_fullscreen(args, object())

    equals("v45_public_recovery_rc", rc, 0)
    surfaced = json.loads(output.getvalue())
    equals("v45_public_recovery_state", surfaced["recovery"], "completed")
    equals("v45_public_recovery_operation", surfaced["operation_id"], blocker)


def test_v45_unknown_parser_rejects_wrong_operation_and_bad_blocker():
    operation_id = "2" * 32
    base = {
        "operation_id": operation_id,
        "status": "unknown",
        "reason": "TEST",
        "blocking_operation_id": "3" * 32,
    }

    wrong = dict(base, operation_id="4" * 32)
    try:
        vm._parse_fullscreen_unknown(json.dumps(wrong), operation_id)
    except vm.Unavailable:
        pass
    else:
        raise AssertionError("wrong operation id was accepted")

    bad = dict(base, blocking_operation_id="not-an-operation")
    try:
        vm._parse_fullscreen_unknown(json.dumps(bad), operation_id)
    except vm.Unavailable:
        pass
    else:
        raise AssertionError("invalid blocker id was accepted")
