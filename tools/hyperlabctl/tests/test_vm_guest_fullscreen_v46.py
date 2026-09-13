"""Adversarial V4.6 journal durability and dispatch-fence regressions."""

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
    stable_file = root / "stable"
    dispatches = root / "dispatches"
    active_calls = root / "active-calls"

    state.write_text(str(initial_mode), encoding="utf-8")
    behavior_file.write_text(behavior, encoding="utf-8")
    instance_file.write_text("instance-a", encoding="utf-8")
    socket_file.write_text("wayland-a", encoding="utf-8")
    stable_file.write_text("18000001", encoding="utf-8")
    dispatches.write_text("", encoding="utf-8")
    active_calls.write_text("", encoding="utf-8")

    _write_executable(
        bindir / "pgrep",
        "#!/bin/sh\nprintf '%s\\n' \"$HL46_SESSION_PID\"\n",
    )

    hyprctl = r"""#!/usr/bin/env python3
import json
import os
import pathlib
import subprocess
import sys
import time

state = pathlib.Path(os.environ["HL46_STATE"])
behavior_file = pathlib.Path(os.environ["HL46_BEHAVIOR"])
instance_file = pathlib.Path(os.environ["HL46_INSTANCE"])
socket_file = pathlib.Path(os.environ["HL46_SOCKET"])
stable_file = pathlib.Path(os.environ["HL46_STABLE"])
dispatches = pathlib.Path(os.environ["HL46_DISPATCHES"])
active_calls = pathlib.Path(os.environ["HL46_ACTIVE_CALLS"])
pid = int(os.environ["HL46_SESSION_PID"])
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
    with active_calls.open("a", encoding="utf-8") as handle:
        handle.write("1\n")
    if behavior == "active_forbidden":
        raise SystemExit(9)
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
    with dispatches.open("a", encoding="utf-8") as handle:
        handle.write("1\n")

    expression = args[1]
    if 'window = "stableid:' not in expression:
        raise SystemExit(20)
    selected = expression.split('window = "stableid:', 1)[1].split('"', 1)[0]
    if selected != stable_file.read_text().strip():
        raise SystemExit(21)

    if behavior == "toggle_race":
        state.write_text("2", encoding="utf-8")

    if 'action = "set"' in expression:
        desired_mode = 2
    elif 'action = "unset"' in expression:
        desired_mode = 0
    elif 'action = "toggle"' in expression:
        desired_mode = 0 if int(state.read_text()) in (2, 3) else 2
    else:
        raise SystemExit(22)

    if behavior == "zero_delay":
        time.sleep(0.05)
        state.write_text(str(desired_mode), encoding="utf-8")
        print("ok")
        raise SystemExit(0)

    if behavior == "nonzero_delay":
        code = (
            "import pathlib,time;"
            "time.sleep(0.8);"
            "pathlib.Path(%r).write_text(%r)"
            % (str(state), str(desired_mode))
        )
        subprocess.Popen(
            [sys.executable, "-c", code],
            start_new_session=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        print("dispatch failed")
        raise SystemExit(4)

    if behavior == "ack_noapply_query_fail":
        behavior_file.write_text(
            "query_fail",
            encoding="utf-8",
        )
        print("ok")
        raise SystemExit(0)

    if behavior == "complete_noapply":
        print("ok")
        raise SystemExit(0)

    state.write_text(str(desired_mode), encoding="utf-8")
    print("ok")
    raise SystemExit(0)

raise SystemExit(23)
"""
    _write_executable(bindir / "hyprctl", hyprctl)

    env = os.environ.copy()
    env["PATH"] = str(bindir) + os.pathsep + "/usr/bin:/bin"
    env["XDG_RUNTIME_DIR"] = str(runtime)
    env["HL46_STATE"] = str(state)
    env["HL46_BEHAVIOR"] = str(behavior_file)
    env["HL46_INSTANCE"] = str(instance_file)
    env["HL46_SOCKET"] = str(socket_file)
    env["HL46_STABLE"] = str(stable_file)
    env["HL46_DISPATCHES"] = str(dispatches)
    env["HL46_ACTIVE_CALLS"] = str(active_calls)
    env["HL46_SESSION_PID"] = str(os.getpid())
    env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
    env.pop("WAYLAND_DISPLAY", None)

    return (
        env,
        state,
        behavior_file,
        instance_file,
        stable_file,
        dispatches,
        active_calls,
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
    equals("v46_unknown_rc", result.returncode, 75)
    return vm._parse_fullscreen_unknown(result.stdout, operation_id)


def _recovery(result, operation_id):
    equals("v46_recovery_rc", result.returncode, 0)
    return vm._parse_fullscreen_recovery(result.stdout, operation_id)


def _operation_dirs(runtime):
    base = runtime / "hyperlab-fullscreen"
    receipts = base / "receipts"
    operations = base / "operations"
    for path in (base, receipts, operations):
        path.mkdir(mode=0o700, exist_ok=True)
        path.chmod(0o700)
    return receipts, operations


def _seed_prepared(env, runtime, operation_id, requested="toggle"):
    _receipts, operations = _operation_dirs(runtime)
    before = 0
    desired = 1
    record = {
        "operation_id": operation_id,
        "phase": "prepared",
        "requested": requested,
        "address": "0xabc",
        "stable_id": "18000001",
        "before_mode": before,
        "desired": desired,
        "requires_dispatch": 1,
        "hyprland_pid": int(env["HL46_SESSION_PID"]),
        "instance": "instance-a",
        "wl_socket": "wayland-a",
        "dispatch_rc": None,
    }
    path = operations / (operation_id + ".json")
    path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def test_v46_initial_publish_is_atomic_and_invalid_journal_stays_blocking():
    source = vm._GUEST_FULLSCREEN_TRANSACTION

    check(
        "v46_atomic_create_uses_link",
        "os.link(tmp, path" in source,
        source,
    )
    check(
        "v46_all_state_writes_are_looped",
        "def write_all(" in source,
        source,
    )

    with tempfile.TemporaryDirectory(prefix="hyperlab-v46-atomic-") as temp:
        (
            env,
            _state,
            _behavior,
            _instance,
            _stable,
            _dispatches,
            _active_calls,
            runtime,
        ) = _fake_environment(
            Path(temp),
            initial_mode=0,
            behavior="normal",
        )

        operation_id = "1" * 32
        _receipts, operations = _operation_dirs(runtime)

        partial_tmp = operations / (
            "." + operation_id + ".json.crash.tmp"
        )
        partial_tmp.write_text("{", encoding="utf-8")
        partial_tmp.chmod(0o600)

        result = _run(env, operation_id, "on")

        equals("v46_partial_tmp_rc", result.returncode, 0)

        payload = vm._parse_fullscreen_receipt(
            result.stdout,
            operation_id,
            "on",
        )

        equals(
            "v46_partial_tmp_success",
            payload["status"],
            "success",
        )
        check(
            "v46_partial_tmp_preserved",
            partial_tmp.exists(),
        )

    for label in ("truncated", "permissions", "oversized"):
        with tempfile.TemporaryDirectory(
            prefix="hyperlab-v46-invalid-" + label + "-"
        ) as temp:
            (
                env,
                _state,
                _behavior,
                _instance,
                _stable,
                dispatches,
                _active_calls,
                runtime,
            ) = _fake_environment(
                Path(temp),
                initial_mode=0,
                behavior="normal",
            )

            blocker_id = "2" * 32

            blocker = _seed_prepared(
                env,
                runtime,
                blocker_id,
                requested="on",
            )

            # The permissions fixture must begin as genuinely valid JSON.
            parsed = json.loads(
                blocker.read_text(encoding="utf-8")
            )
            equals(
                "v46_invalid_valid_seed_" + label,
                parsed["operation_id"],
                blocker_id,
            )

            if label == "permissions":
                blocker.chmod(0o644)

            elif label == "truncated":
                blocker.write_text("{", encoding="utf-8")

            else:
                blocker.write_text(
                    blocker.read_text(encoding="utf-8")
                    + (" " * 9000),
                    encoding="utf-8",
                )

            other_id = "3" * 32

            blocked = _unknown(
                _run(env, other_id, "on"),
                other_id,
            )

            equals(
                "v46_invalid_blocker_" + label,
                blocked["blocking_operation_id"],
                blocker_id,
            )
            equals(
                "v46_invalid_no_dispatch_" + label,
                _dispatch_count(dispatches),
                0,
            )

            recovered = _recovery(
                _run(env, blocker_id, "recover"),
                blocker_id,
            )

            equals(
                "v46_invalid_recovery_" + label,
                recovered["recovery"],
                "still-unresolved",
            )
            equals(
                "v46_invalid_reason_" + label,
                recovered["reason"],
                "STATE_FILE_INVALID",
            )
            check(
                "v46_invalid_preserved_" + label,
                blocker.exists(),
            )




def test_v46_prepared_record_is_a_durable_binding_and_same_id_replays_it():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v46-prepared-") as temp:
        (
            env,
            state,
            behavior,
            _instance,
            _stable,
            dispatches,
            active_calls,
            runtime,
        ) = _fake_environment(Path(temp), initial_mode=0, behavior="normal")
        prepared_id = "5" * 32
        prepared = _seed_prepared(env, runtime, prepared_id)

        other_id = "6" * 32
        other = _unknown(_run(env, other_id, "on"), other_id)
        equals(
            "v46_prepared_blocks_other",
            other["blocking_operation_id"],
            prepared_id,
        )
        check("v46_prepared_not_erased", prepared.exists())
        equals("v46_prepared_no_dispatch_by_other", _dispatch_count(dispatches), 0)

        behavior.write_text("active_forbidden", encoding="utf-8")
        replay = _run(env, prepared_id, "toggle")
        equals("v46_prepared_replay_rc", replay.returncode, 0)
        payload = vm._parse_fullscreen_receipt(
            replay.stdout,
            prepared_id,
            "toggle",
        )
        equals("v46_prepared_replay_after", payload["after_mode"], 2)
        equals("v46_prepared_replay_dispatches", _dispatch_count(dispatches), 1)
        equals(
            "v46_prepared_replay_did_not_reselect_active",
            len([x for x in active_calls.read_text().splitlines() if x]),
            0,
        )
        equals("v46_prepared_replay_final_state", int(state.read_text()), 2)

    with tempfile.TemporaryDirectory(prefix="hyperlab-v46-prepared-drift-") as temp:
        (
            env,
            state,
            _behavior,
            _instance,
            _stable,
            dispatches,
            _active_calls,
            runtime,
        ) = _fake_environment(Path(temp), initial_mode=0, behavior="normal")
        prepared_id = "7" * 32
        prepared = _seed_prepared(env, runtime, prepared_id)
        state.write_text("2", encoding="utf-8")

        drift = _run(env, prepared_id, "toggle")
        equals("v46_prepared_drift_rc", drift.returncode, 2)
        receipt = vm._parse_fullscreen_receipt(
            drift.stdout,
            prepared_id,
            "toggle",
        )
        equals(
            "v46_prepared_drift_failure",
            receipt["failure"],
            "PREPARED_STATE_DRIFT",
        )
        equals("v46_prepared_drift_dispatches", _dispatch_count(dispatches), 0)
        check("v46_prepared_drift_retired", not prepared.exists())


def test_v46_zero_ack_obeys_synchronous_completion_fence():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v46-zero-sync-") as temp:
        (
            env,
            state,
            _behavior,
            _instance,
            _stable,
            dispatches,
            _active_calls,
            runtime,
        ) = _fake_environment(
            Path(temp), initial_mode=0, behavior="zero_delay"
        )
        operation_id = "8" * 32

        result = _run(env, operation_id, "on")
        equals("v46_zero_sync_rc", result.returncode, 0)
        payload = vm._parse_fullscreen_receipt(
            result.stdout, operation_id, "on"
        )
        equals("v46_zero_sync_status", payload["status"], "success")
        equals("v46_zero_sync_after", payload["after_mode"], 2)
        equals("v46_zero_sync_state", int(state.read_text()), 2)
        equals(
            "v46_zero_sync_dispatches",
            _dispatch_count(dispatches),
            1,
        )

        operation = (
            runtime
            / "hyperlab-fullscreen"
            / "operations"
            / (operation_id + ".json")
        )
        check("v46_zero_sync_no_barrier", not operation.exists())

    with tempfile.TemporaryDirectory(prefix="hyperlab-v46-noeffect-") as temp:
        (
            env,
            state,
            _behavior,
            _instance,
            _stable,
            dispatches,
            _active_calls,
            runtime,
        ) = _fake_environment(
            Path(temp), initial_mode=0, behavior="complete_noapply"
        )
        operation_id = "9" * 32

        result = _run(env, operation_id, "on")
        equals("v46_noeffect_rc", result.returncode, 2)
        payload = vm._parse_fullscreen_receipt(
            result.stdout, operation_id, "on"
        )
        equals("v46_noeffect_status", payload["status"], "failure")
        equals(
            "v46_noeffect_reason",
            payload["failure"],
            "POST_DISPATCH_STATE_MISMATCH",
        )
        equals("v46_noeffect_after", payload["after_mode"], 0)
        equals("v46_noeffect_state", int(state.read_text()), 0)
        equals(
            "v46_noeffect_dispatches",
            _dispatch_count(dispatches),
            1,
        )

        operation = (
            runtime
            / "hyperlab-fullscreen"
            / "operations"
            / (operation_id + ".json")
        )
        check("v46_noeffect_no_barrier", not operation.exists())



def test_v46_nonzero_exit_with_delayed_application_never_claims_completion():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v46-nonzero-delay-") as temp:
        (
            env,
            state,
            behavior,
            instance,
            _stable,
            dispatches,
            _active_calls,
            runtime,
        ) = _fake_environment(
            Path(temp),
            initial_mode=0,
            behavior="nonzero_delay",
        )
        first_id = "b" * 32
        second_id = "c" * 32

        first = _unknown(_run(env, first_id, "on"), first_id)
        equals(
            "v46_nonzero_reason",
            first["reason"],
            "FULLSCREEN_DISPATCH_UNACKNOWLEDGED",
        )
        equals("v46_nonzero_blocker", first["blocking_operation_id"], first_id)
        equals("v46_nonzero_dispatches", _dispatch_count(dispatches), 1)

        behavior.write_text("normal", encoding="utf-8")
        second = _unknown(_run(env, second_id, "off"), second_id)
        equals(
            "v46_nonzero_opposite_blocked",
            second["blocking_operation_id"],
            first_id,
        )
        equals("v46_nonzero_no_second_dispatch", _dispatch_count(dispatches), 1)

        deadline = time.monotonic() + 3.0
        while time.monotonic() < deadline and int(state.read_text()) != 2:
            time.sleep(0.05)
        equals("v46_nonzero_late_state", int(state.read_text()), 2)

        same = _recovery(_run(env, first_id, "recover"), first_id)
        equals("v46_nonzero_same_session", same["recovery"], "still-unresolved")

        operation = (
            runtime
            / "hyperlab-fullscreen"
            / "operations"
            / (first_id + ".json")
        )
        check("v46_nonzero_barrier_still_present", operation.exists())

        instance.write_text("instance-b", encoding="utf-8")
        conflicting = _recovery(
            _run(env, first_id, "recover"),
            first_id,
        )
        equals(
            "v46_nonzero_tuple_conflict_unresolved",
            conflicting["recovery"],
            "still-unresolved",
        )
        equals(
            "v46_nonzero_tuple_conflict_reason",
            conflicting["reason"],
            "SESSION_DISCOVERY_AMBIGUOUS",
        )
        check(
            "v46_nonzero_barrier_after_tuple_conflict",
            operation.exists(),
        )
        equals(
            "v46_nonzero_no_redispatch_after_tuple_conflict",
            _dispatch_count(dispatches),
            1,
        )

        env["HL46_SESSION_PID"] = str(
            int(env["HL46_SESSION_PID"]) + 100000
        )
        retired = _recovery(
            _run(env, first_id, "recover"),
            first_id,
        )
        equals(
            "v46_nonzero_authoritative_expiry_retired",
            retired["recovery"],
            "retired",
        )
        equals(
            "v46_nonzero_authoritative_expiry_reason",
            retired["receipt"]["failure"],
            "SESSION_EXPIRED",
        )
        check(
            "v46_nonzero_barrier_retired",
            not operation.exists(),
        )

def test_v46_toggle_is_evaluated_at_compositor_dispatch_time():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v46-toggle-race-") as temp:
        (
            env,
            state,
            _behavior,
            _instance,
            _stable,
            dispatches,
            _active_calls,
            _runtime,
        ) = _fake_environment(
            Path(temp),
            initial_mode=0,
            behavior="toggle_race",
        )

        operation_id = "d" * 32

        result = _run(env, operation_id, "toggle")

        equals("v46_toggle_race_rc", result.returncode, 0)

        payload = vm._parse_fullscreen_receipt(
            result.stdout,
            operation_id,
            "toggle",
        )

        equals(
            "v46_toggle_race_status",
            payload["status"],
            "success",
        )
        equals(
            "v46_toggle_race_before",
            payload["before_mode"],
            0,
        )
        equals(
            "v46_toggle_race_after",
            payload["after_mode"],
            2,
        )
        equals(
            "v46_toggle_race_desired",
            payload["desired"],
            1,
        )
        equals(
            "v46_toggle_race_dispatches",
            _dispatch_count(dispatches),
            1,
        )
        equals(
            "v46_toggle_race_final_state",
            int(state.read_text()),
            2,
        )

        source = vm._GUEST_FULLSCREEN_TRANSACTION

        check(
            "v46_toggle_no_live_toggle",
            'dispatch_action = "toggle"' not in source,
            source,
        )
        check(
            "v46_toggle_snapshot_set_unset",
            'dispatch_action = "set" if record["desired"] else "unset"'
            in source,
            source,
        )



def test_v48_lost_postdispatch_proof_never_becomes_success():
    with tempfile.TemporaryDirectory(prefix="hyperlab-v48-proof-loss-") as temp:
        (
            env,
            state,
            behavior,
            _instance,
            _stable,
            dispatches,
            _active_calls,
            runtime,
        ) = _fake_environment(
            Path(temp),
            initial_mode=0,
            behavior="ack_noapply_query_fail",
        )

        operation_id = "7" * 32

        first = _run(env, operation_id, "on")

        equals("v48_proof_first_rc", first.returncode, 2)
        equals(
            "v48_proof_dispatches",
            _dispatch_count(dispatches),
            1,
        )

        first_payload = vm._parse_fullscreen_receipt(
            first.stdout,
            operation_id,
            "on",
        )

        equals(
            "v48_proof_first_status",
            first_payload["status"],
            "failure",
        )
        equals(
            "v48_proof_first_failure",
            first_payload["failure"],
            "POST_DISPATCH_QUERY_FAILED",
        )

        receipts, operations = _operation_dirs(runtime)

        receipt_path = receipts / (operation_id + ".json")
        operation_path = operations / (operation_id + ".json")

        check(
            "v48_proof_receipt_exists",
            receipt_path.exists(),
            str(receipt_path),
        )
        check(
            "v48_proof_operation_retired",
            not operation_path.exists(),
            str(operation_path),
        )

        # A later unrelated actor reaches the desired visual state. That
        # convergence cannot be attributed to the completed HyperLab request.
        state.write_text("2", encoding="utf-8")
        behavior.write_text("normal", encoding="utf-8")

        replay = _run(env, operation_id, "on")

        equals("v48_proof_replay_rc", replay.returncode, 2)
        equals(
            "v48_proof_no_redispatch",
            _dispatch_count(dispatches),
            1,
        )
        equals(
            "v48_proof_receipt_immutable",
            replay.stdout,
            first.stdout,
        )

        recovery = _recovery(
            _run(env, operation_id, "recover"),
            operation_id,
        )

        equals(
            "v48_proof_recovery_state",
            recovery["recovery"],
            "retired",
        )
        equals(
            "v48_proof_recovery_status",
            recovery["receipt"]["status"],
            "failure",
        )
        equals(
            "v48_proof_recovery_reason",
            recovery["receipt"]["failure"],
            "POST_DISPATCH_QUERY_FAILED",
        )


def test_v48_dispatch_counters_detect_two_dispatches():
    from test_vm_guest_fullscreen_v42 import _dispatches as count_v42
    from test_vm_guest_fullscreen_v43 import _dispatches as count_v43
    from test_vm_guest_fullscreen_v44 import _dispatch_count as count_v44

    with tempfile.TemporaryDirectory(prefix="hyperlab-v48-counter-") as temp:
        path = Path(temp) / "dispatches"

        path.write_text(
            "1\n1\n",
            encoding="utf-8",
        )

        equals("v48_counter_v42", count_v42(path), 2)
        equals("v48_counter_v43", count_v43(path), 2)
        equals("v48_counter_v44", count_v44(path), 2)
