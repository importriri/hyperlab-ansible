"""Adversarial V4.4 fullscreen recovery/session/ordering regressions."""

import inspect
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

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
    instance_file = root / "instance"
    socket_file = root / "socket"
    dispatches = root / "dispatches"
    state.write_text(str(initial_mode), encoding="utf-8")
    behavior_file.write_text(behavior, encoding="utf-8")
    instance_file.write_text("instance-a", encoding="utf-8")
    socket_file.write_text("wayland-a", encoding="utf-8")
    dispatches.write_text("", encoding="utf-8")

    _write_executable(
        bindir / "pgrep",
        "#!/bin/sh\nprintf '%s\\n' \"$HL44_SESSION_PID\"\n",
    )

    hyprctl = r"""#!/usr/bin/env python3
import json
import os
import pathlib
import sys
import time

state = pathlib.Path(os.environ["HL44_STATE"])
behavior_file = pathlib.Path(os.environ["HL44_BEHAVIOR"])
instance_file = pathlib.Path(os.environ["HL44_INSTANCE"])
socket_file = pathlib.Path(os.environ["HL44_SOCKET"])
dispatches = pathlib.Path(os.environ["HL44_DISPATCHES"])
pid = int(os.environ["HL44_SESSION_PID"])
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
    print(json.dumps([{
        "address": "0xabc",
        "stableId": "18000001",
        "fullscreen": int(state.read_text()),
    }]))
    raise SystemExit(0)

if len(args) == 2 and args[0] == "dispatch":
    expression = args[1]
    with dispatches.open("a", encoding="utf-8") as handle:
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

    if behavior == "hang_apply":
        state.write_text(str(desired_mode), encoding="utf-8")
        time.sleep(4.0)
        raise SystemExit(0)

    if behavior == "complete_noapply":
        print("ok")
        raise SystemExit(0)

    if behavior == "complete_then_query_fail":
        state.write_text(str(desired_mode), encoding="utf-8")
        behavior_file.write_text("query_fail", encoding="utf-8")
        print("ok")
        raise SystemExit(0)

    if behavior == "slow_apply":
        time.sleep(1.0)
        state.write_text(str(desired_mode), encoding="utf-8")
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
    env["HL44_STATE"] = str(state)
    env["HL44_BEHAVIOR"] = str(behavior_file)
    env["HL44_INSTANCE"] = str(instance_file)
    env["HL44_SOCKET"] = str(socket_file)
    env["HL44_DISPATCHES"] = str(dispatches)
    env["HL44_SESSION_PID"] = str(os.getpid())
    env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
    env.pop("WAYLAND_DISPLAY", None)
    return (
        env,
        state,
        behavior_file,
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


def _parse_recovery(result, operation_id):
    equals("v44_recovery_rc", result.returncode, 0)
    return vm._parse_fullscreen_recovery(result.stdout, operation_id)


def test_v44_public_cli_exposes_explicit_recovery():
    source = inspect.getsource(vm.VmCommand._guest_fullscreen)
    check(
        "v44_cli_recovery_route",
        "recover_operation" in source
        and '_run_fullscreen_remote(' in source
        and '"recover"' in source,
        source,
    )


def test_v44_dispatching_state_never_proves_completion():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v44-dispatching-") as temp:
        env, state, _behavior, instance, _socket, dispatches, runtime = (
            _fake_environment(Path(temp), initial_mode=0, behavior="hang_apply")
        )
        operation_id = "c" * 32

        first = _run(env, operation_id, "on")
        equals("v44_dispatching_first_rc", first.returncode, 75)
        equals("v44_dispatching_applied_visual_state", int(state.read_text()), 2)
        equals("v44_dispatching_count", _dispatch_count(dispatches), 1)

        recovery = _parse_recovery(
            _run(env, operation_id, "recover"),
            operation_id,
        )
        equals(
            "v44_dispatching_same_session_unresolved",
            recovery["recovery"],
            "still-unresolved",
        )
        receipt = (
            runtime
            / "hyperlab-fullscreen"
            / "receipts"
            / (operation_id + ".json")
        )
        check("v44_dispatching_no_receipt", not receipt.exists())

        instance.write_text("instance-b", encoding="utf-8")
        conflicting = _parse_recovery(
            _run(env, operation_id, "recover"),
            operation_id,
        )
        equals(
            "v44_dispatching_tuple_conflict_unresolved",
            conflicting["recovery"],
            "still-unresolved",
        )
        equals(
            "v44_dispatching_tuple_conflict_reason",
            conflicting["reason"],
            "SESSION_DISCOVERY_AMBIGUOUS",
        )
        check(
            "v44_dispatching_tuple_conflict_no_receipt",
            not receipt.exists(),
        )

        env["HL44_SESSION_PID"] = str(
            int(env["HL44_SESSION_PID"]) + 100000
        )
        recovery = _parse_recovery(
            _run(env, operation_id, "recover"),
            operation_id,
        )
        equals(
            "v44_dispatching_authoritative_expiry_retires",
            recovery["recovery"],
            "retired",
        )
        equals(
            "v44_dispatching_authoritative_expiry_failure",
            recovery["receipt"]["failure"],
            "SESSION_EXPIRED",
        )


def test_v44_fresh_ssh_recovers_completed_dispatch_by_identity():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v44-fresh-ssh-") as temp:
        env, state, behavior, _instance, _socket, dispatches, _runtime = (
            _fake_environment(
                Path(temp),
                initial_mode=0,
                behavior="complete_then_query_fail",
            )
        )

        operation_id = "d" * 32

        first = _run(env, operation_id, "on")

        equals("v44_fresh_first_rc", first.returncode, 2)
        equals("v44_fresh_state", int(state.read_text()), 2)
        equals("v44_fresh_dispatches", _dispatch_count(dispatches), 1)

        first_payload = vm._parse_fullscreen_receipt(
            first.stdout,
            operation_id,
            "on",
        )

        equals(
            "v44_fresh_failure",
            first_payload["failure"],
            "POST_DISPATCH_QUERY_FAILED",
        )

        behavior.write_text("normal", encoding="utf-8")

        recovery = _parse_recovery(
            _run(env, operation_id, "recover"),
            operation_id,
        )

        equals("v44_fresh_recovery", recovery["recovery"], "retired")
        equals(
            "v44_fresh_recovery_failure",
            recovery["receipt"]["failure"],
            "POST_DISPATCH_QUERY_FAILED",
        )
        equals("v44_fresh_no_redispatch", _dispatch_count(dispatches), 1)



def test_v44_address_reuse_across_compositor_restart_is_not_success():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v44-address-reuse-") as temp:
        env, state, behavior, instance, socket_file, dispatches, _runtime = (
            _fake_environment(
                Path(temp),
                initial_mode=0,
                behavior="complete_then_query_fail",
            )
        )

        operation_id = "e" * 32

        first = _run(env, operation_id, "on")

        equals("v44_reuse_first_rc", first.returncode, 2)
        equals("v44_reuse_dispatches", _dispatch_count(dispatches), 1)

        # Later session replacement and matching visible state cannot convert
        # the already terminal proof loss into success.
        instance.write_text("instance-new", encoding="utf-8")
        socket_file.write_text("wayland-new", encoding="utf-8")
        behavior.write_text("normal", encoding="utf-8")
        state.write_text("2", encoding="utf-8")

        recovery = _parse_recovery(
            _run(env, operation_id, "recover"),
            operation_id,
        )

        equals("v44_reuse_recovery", recovery["recovery"], "retired")
        equals(
            "v44_reuse_session_failure",
            recovery["receipt"]["failure"],
            "POST_DISPATCH_QUERY_FAILED",
        )
        equals("v44_reuse_no_redispatch", _dispatch_count(dispatches), 1)



def test_v44_synchronous_completion_orders_opposite_request():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v44-order-") as temp:
        env, state, _behavior, _instance, _socket, dispatches, _runtime = (
            _fake_environment(Path(temp), initial_mode=0, behavior="slow_apply")
        )

        first = subprocess.Popen(
            [
                sys.executable,
                "-c",
                vm._GUEST_FULLSCREEN_TRANSACTION,
                "f" * 32,
                "on",
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )
        dispatch_deadline = time.monotonic() + 2.0
        while (
            _dispatch_count(dispatches) < 1
            and time.monotonic() < dispatch_deadline
        ):
            time.sleep(0.02)
        equals(
            "v44_order_first_entered_dispatch",
            _dispatch_count(dispatches),
            1,
        )

        state.write_text("2", encoding="utf-8")
        started = time.monotonic()
        second = _run(env, "1" * 32, "off")
        elapsed = time.monotonic() - started
        first_out, first_err = first.communicate(timeout=8.0)

        equals("v44_order_first_rc", first.returncode, 0)
        equals("v44_order_second_rc", second.returncode, 0)
        check("v44_order_first_stderr", not first_err, first_err)
        check("v44_order_first_receipt", '"status":"success"' in first_out)
        check(
            "v44_order_second_waited_for_completion",
            elapsed >= 0.6,
            "elapsed=%r" % elapsed,
        )
        second_payload = vm._parse_fullscreen_receipt(
            second.stdout,
            "1" * 32,
            "off",
        )
        equals("v44_order_second_before", second_payload["before_mode"], 2)
        equals("v44_order_second_desired", second_payload["desired"], 0)
        equals("v44_order_second_changed", second_payload["transition_required"], 1)
        equals("v44_order_second_after", second_payload["after_mode"], 0)
        equals("v44_order_final_state", int(state.read_text()), 0)


def test_v44_completed_dispatch_that_never_applies_is_terminal_mismatch():
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-v44-noapply-"
    ) as temp:
        (
            env,
            state,
            _behavior,
            _instance,
            _socket,
            dispatches,
            runtime,
        ) = _fake_environment(
            Path(temp),
            initial_mode=0,
            behavior="complete_noapply",
        )
        operation_id = "2" * 32

        result = _run(env, operation_id, "on")

        equals("v44_noapply_rc", result.returncode, 2)

        payload = vm._parse_fullscreen_receipt(
            result.stdout,
            operation_id,
            "on",
        )

        equals(
            "v44_noapply_status",
            payload["status"],
            "failure",
        )
        equals(
            "v44_noapply_reason",
            payload["failure"],
            "POST_DISPATCH_STATE_MISMATCH",
        )
        equals(
            "v44_noapply_before",
            payload["before_mode"],
            0,
        )
        equals(
            "v44_noapply_after",
            payload["after_mode"],
            0,
        )
        equals(
            "v44_noapply_desired",
            payload["desired"],
            1,
        )
        equals(
            "v44_noapply_state",
            int(state.read_text()),
            0,
        )
        equals(
            "v44_noapply_dispatches",
            _dispatch_count(dispatches),
            1,
        )

        operation = (
            runtime
            / "hyperlab-fullscreen"
            / "operations"
            / (operation_id + ".json")
        )
        receipt = (
            runtime
            / "hyperlab-fullscreen"
            / "receipts"
            / (operation_id + ".json")
        )

        check(
            "v44_noapply_barrier_retired",
            not operation.exists(),
        )
        check(
            "v44_noapply_terminal_receipt",
            receipt.exists(),
        )

        replay = _run(env, operation_id, "on")

        equals(
            "v44_noapply_replay_rc",
            replay.returncode,
            2,
        )
        equals(
            "v44_noapply_replay_same_receipt",
            replay.stdout,
            result.stdout,
        )
        equals(
            "v44_noapply_no_redispatch",
            _dispatch_count(dispatches),
            1,
        )



def test_v44_permanent_target_loss_after_completion_is_recoverable():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v44-target-loss-") as temp:
        env, _state, behavior, _instance, _socket, dispatches, _runtime = (
            _fake_environment(
                Path(temp),
                initial_mode=0,
                behavior="complete_then_query_fail",
            )
        )

        operation_id = "3" * 32

        first = _run(env, operation_id, "on")

        equals("v44_loss_first_rc", first.returncode, 2)
        equals("v44_loss_dispatches", _dispatch_count(dispatches), 1)

        behavior.write_text("target_missing", encoding="utf-8")

        recovery = _parse_recovery(
            _run(env, operation_id, "recover"),
            operation_id,
        )

        equals("v44_loss_recovery", recovery["recovery"], "retired")
        equals(
            "v44_loss_failure",
            recovery["receipt"]["failure"],
            "POST_DISPATCH_QUERY_FAILED",
        )
        equals("v44_loss_no_redispatch", _dispatch_count(dispatches), 1)
