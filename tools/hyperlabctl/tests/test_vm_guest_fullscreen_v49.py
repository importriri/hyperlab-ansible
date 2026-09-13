import json
import os
import time
import sys
import subprocess
import tempfile
from pathlib import Path

from harness import check, equals
from hyperlabctl.commands import vm
from hyperlabctl.errors import Unavailable
from test_vm_guest_fullscreen_v46 import (
    _dispatch_count,
    _fake_environment,
    _operation_dirs,
    _run,
    _seed_prepared,
)


def _seed_dispatching(env, runtime, operation_id):
    path = _seed_prepared(
        env,
        runtime,
        operation_id,
        requested="on",
    )
    record = json.loads(path.read_text(encoding="utf-8"))
    record["phase"] = "dispatching"
    path.write_text(
        json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    path.chmod(0o600)
    return path


def _extend_fake_instances(env):
    bindir = Path(env["PATH"].split(os.pathsep, 1)[0])
    path = bindir / "hyprctl"
    text = path.read_text(encoding="utf-8")

    old = """if args == ["instances", "-j"]:
    print(json.dumps([{
        "pid": pid,
        "instance": instance_file.read_text().strip(),
        "wl_socket": socket_file.read_text().strip(),
    }]))
    raise SystemExit(0)
"""

    new = """if args == ["instances", "-j"]:
    exact = {
        "pid": pid,
        "instance": instance_file.read_text().strip(),
        "wl_socket": socket_file.read_text().strip(),
    }
    mode = os.environ.get("HL49_MODE", "normal")
    if mode == "malformed":
        print(json.dumps([exact, {"pid": pid}]))
    elif mode == "duplicate":
        print(json.dumps([exact, exact]))
    elif mode == "mixed":
        conflicting = dict(exact)
        conflicting["wl_socket"] = exact["wl_socket"] + "-conflict"
        print(json.dumps([exact, conflicting]))
    elif mode == "replacement":
        conflicting = dict(exact)
        conflicting["instance"] = exact["instance"] + "-replacement"
        conflicting["wl_socket"] = exact["wl_socket"] + "-replacement"
        print(json.dumps([conflicting]))
    elif mode == "omit":
        print("[]")
    else:
        print(json.dumps([exact]))
    raise SystemExit(0)
"""

    equals("v49_instances_anchor", text.count(old), 1)
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
    path.chmod(0o700)


def test_v49_ambiguous_discovery_preserves_dispatching_barrier():
    for mode, operation_id in (
        ("malformed", "a" * 32),
        ("duplicate", "b" * 32),
        ("mixed", "6" * 32),
        ("replacement", "7" * 32),
        ("omit", "c" * 32),
    ):
        with tempfile.TemporaryDirectory(prefix="hyperlab-v49-") as temp:
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

            _extend_fake_instances(env)
            env["HL49_MODE"] = mode

            operation = _seed_dispatching(
                env,
                runtime,
                operation_id,
            )

            result = _run(
                env,
                operation_id,
                "recover",
            )

            equals("v49_%s_rc" % mode, result.returncode, 0)

            recovery = vm._parse_fullscreen_recovery(
                result.stdout,
                operation_id,
            )

            equals(
                "v49_%s_recovery" % mode,
                recovery["recovery"],
                "still-unresolved",
            )
            equals(
                "v49_%s_reason" % mode,
                recovery["reason"],
                "SESSION_DISCOVERY_AMBIGUOUS",
            )
            equals(
                "v49_%s_receipt" % mode,
                recovery["receipt"],
                None,
            )
            check(
                "v49_%s_barrier_preserved" % mode,
                operation.exists(),
            )

            receipts, _operations = _operation_dirs(runtime)

            check(
                "v49_%s_no_terminal_receipt" % mode,
                not (receipts / (operation_id + ".json")).exists(),
            )
            equals(
                "v49_%s_no_dispatch" % mode,
                _dispatch_count(dispatches),
                0,
            )

def _expect_unavailable(name, callback):
    try:
        callback()
    except Unavailable:
        check(name, True)
    else:
        check(name, False, "expected Unavailable")


def test_v49_recovery_envelope_status_must_match_recovery_kind():
    operation_id = "d" * 32

    success = {
        "operation_id": operation_id,
        "status": "success",
        "address": "0xabc",
        "before_mode": 0,
        "after_mode": 2,
        "requested": "on",
        "desired": 1,
        "transition_required": 1,
        "failure": None,
    }

    failure = {
        "operation_id": operation_id,
        "status": "failure",
        "address": "0xabc",
        "before_mode": 0,
        "after_mode": None,
        "requested": "on",
        "desired": 1,
        "transition_required": 1,
        "failure": "POST_DISPATCH_QUERY_FAILED",
    }

    completed_with_failure = {
        "operation_id": operation_id,
        "recovery": "completed",
        "receipt": failure,
        "reason": None,
    }

    retired_with_success = {
        "operation_id": operation_id,
        "recovery": "retired",
        "receipt": success,
        "reason": None,
    }

    _expect_unavailable(
        "v49_completed_failure_refused",
        lambda: vm._parse_fullscreen_recovery(
            json.dumps(completed_with_failure) + "\n",
            operation_id,
        ),
    )

    _expect_unavailable(
        "v49_retired_success_refused",
        lambda: vm._parse_fullscreen_recovery(
            json.dumps(retired_with_success) + "\n",
            operation_id,
        ),
    )

def _run_v49_source(
    env,
    source,
    operation_id,
    requested,
    timeout=3.0,
):
    return subprocess.run(
        [
            sys.executable,
            "-c",
            source,
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


def test_v49_accumulated_stage_time_uses_one_shared_deadline():
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-v49-budget-"
    ) as temp:
        (
            env,
            _state,
            _behavior,
            _instance,
            _stable,
            dispatches,
            _active_calls,
            _runtime,
        ) = _fake_environment(
            Path(temp),
            initial_mode=0,
            behavior="normal",
        )

        source = vm._GUEST_FULLSCREEN_TRANSACTION

        equals(
            "v49_budget_constant_anchor",
            source.count(
                "TRANSACTION_BUDGET_SECONDS = 8.0"
            ),
            1,
        )

        source = source.replace(
            "TRANSACTION_BUDGET_SECONDS = 8.0",
            "TRANSACTION_BUDGET_SECONDS = 0.20",
            1,
        )

        first_anchor = "        session = select_session()"
        equals(
            "v49_budget_first_stage_anchor",
            source.count(first_anchor),
            1,
        )
        source = source.replace(
            first_anchor,
            "        time.sleep(0.08)\n"
            + first_anchor,
            1,
        )

        second_anchor = (
            '        current_phase = "prepared"\n'
            "\n"
            "    # Prepared replay must preserve its original target"
        )
        equals(
            "v49_budget_second_stage_anchor",
            source.count(second_anchor),
            1,
        )
        source = source.replace(
            second_anchor,
            '        current_phase = "prepared"\n'
            "        time.sleep(0.15)\n"
            "\n"
            "    # Prepared replay must preserve its original target",
            1,
        )

        started = time.monotonic()

        result = _run_v49_source(
            env,
            source,
            "3" * 32,
            "on",
            timeout=2.0,
        )

        elapsed = time.monotonic() - started

        equals(
            "v49_budget_rc",
            result.returncode,
            2,
        )

        payload = json.loads(
            result.stdout.strip()
        )

        equals(
            "v49_budget_status",
            payload["status"],
            "failure",
        )
        equals(
            "v49_budget_failure",
            payload["failure"],
            "TRANSACTION_DEADLINE_EXCEEDED",
        )
        equals(
            "v49_budget_no_dispatch",
            _dispatch_count(dispatches),
            0,
        )

        check(
            "v49_budget_elapsed_bounded",
            elapsed < 0.8,
            "elapsed=%r stdout=%r stderr=%r"
            % (
                elapsed,
                result.stdout,
                result.stderr,
            ),
        )


def test_v49_lock_contention_uses_same_shared_deadline():
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-v49-lock-"
    ) as temp:
        root = Path(temp)

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
            root,
            initial_mode=0,
            behavior="normal",
        )

        base = runtime / "hyperlab-fullscreen"
        base.mkdir(
            mode=0o700,
            exist_ok=True,
        )

        lock_path = base / "transaction.lock"
        ready_path = root / "holder-ready"

        holder_source = "\n".join(
            [
                "import fcntl",
                "import pathlib",
                "import sys",
                "import time",
                "lock_path = pathlib.Path(sys.argv[1])",
                "ready_path = pathlib.Path(sys.argv[2])",
                'with lock_path.open("a+") as handle:',
                "    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)",
                '    ready_path.write_text("ready", encoding="utf-8")',
                "    time.sleep(1.0)",
            ]
        )

        holder = subprocess.Popen(
            [
                sys.executable,
                "-c",
                holder_source,
                str(lock_path),
                str(ready_path),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        ready_deadline = time.monotonic() + 1.0

        while (
            not ready_path.exists()
            and time.monotonic() < ready_deadline
        ):
            time.sleep(0.01)

        check(
            "v49_lock_holder_ready",
            ready_path.exists(),
        )

        source = vm._GUEST_FULLSCREEN_TRANSACTION

        equals(
            "v49_lock_budget_anchor",
            source.count(
                "TRANSACTION_BUDGET_SECONDS = 8.0"
            ),
            1,
        )

        source = source.replace(
            "TRANSACTION_BUDGET_SECONDS = 8.0",
            "TRANSACTION_BUDGET_SECONDS = 0.20",
            1,
        )

        started = time.monotonic()

        result = _run_v49_source(
            env,
            source,
            "4" * 32,
            "on",
            timeout=2.0,
        )

        elapsed = time.monotonic() - started

        equals(
            "v49_lock_rc",
            result.returncode,
            75,
        )
        equals(
            "v49_lock_no_dispatch",
            _dispatch_count(dispatches),
            0,
        )

        check(
            "v49_lock_elapsed_bounded",
            elapsed < 0.8,
            "elapsed=%r stdout=%r stderr=%r"
            % (
                elapsed,
                result.stdout,
                result.stderr,
            ),
        )

        holder.wait(timeout=2.0)

def test_v49_real_crash_after_durable_dispatched_never_recovers_success():
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-v49-real-crash-"
    ) as temp:
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
            behavior="normal",
        )

        operation_id = "5" * 32

        source = vm._GUEST_FULLSCREEN_TRANSACTION

        crash_anchor = (
            '    record = dict(record)\n'
            '    record["phase"] = "dispatched"\n'
            '    record["dispatch_rc"] = 0\n'
            '    replace_json(operation_path, record)\n'
            '    current_phase = "dispatched"\n'
            '\n'
            '    settle_dispatched(record, emit_terminal=True)'
        )

        equals(
            "v49_crash_anchor",
            source.count(crash_anchor),
            1,
        )

        crash_replacement = (
            '    record = dict(record)\n'
            '    record["phase"] = "dispatched"\n'
            '    record["dispatch_rc"] = 0\n'
            '    replace_json(operation_path, record)\n'
            '    current_phase = "dispatched"\n'
            '    os._exit(97)\n'
            '\n'
            '    settle_dispatched(record, emit_terminal=True)'
        )

        crashed_source = source.replace(
            crash_anchor,
            crash_replacement,
            1,
        )

        compile(
            crashed_source,
            "<v49-dispatched-crash>",
            "exec",
        )

        crashed = _run_v49_source(
            env,
            crashed_source,
            operation_id,
            "on",
            timeout=3.0,
        )

        equals(
            "v49_crash_process_rc",
            crashed.returncode,
            97,
        )

        equals(
            "v49_crash_dispatch_count",
            _dispatch_count(dispatches),
            1,
        )

        equals(
            "v49_crash_dispatch_applied",
            int(state.read_text(encoding="utf-8")),
            2,
        )

        receipts, operations = _operation_dirs(
            runtime
        )

        operation_path = (
            operations
            / (operation_id + ".json")
        )

        receipt_path = (
            receipts
            / (operation_id + ".json")
        )

        check(
            "v49_crash_operation_survived",
            operation_path.is_file(),
            str(operation_path),
        )

        check(
            "v49_crash_no_receipt",
            not receipt_path.exists(),
            str(receipt_path),
        )

        durable = json.loads(
            operation_path.read_text(
                encoding="utf-8"
            )
        )

        equals(
            "v49_crash_durable_phase",
            durable["phase"],
            "dispatched",
        )

        equals(
            "v49_crash_durable_dispatch_rc",
            durable["dispatch_rc"],
            0,
        )

        # Simulate unrelated post-crash activity. Even though the compositor
        # later converges to the requested visual state again, that observation
        # cannot reconstruct the lost same-attempt postcondition proof.
        state.write_text(
            "0",
            encoding="utf-8",
        )
        state.write_text(
            "2",
            encoding="utf-8",
        )
        behavior.write_text(
            "normal",
            encoding="utf-8",
        )

        recovered_result = _run(
            env,
            operation_id,
            "recover",
        )

        equals(
            "v49_crash_recovery_transport",
            recovered_result.returncode,
            0,
        )

        recovery = vm._parse_fullscreen_recovery(
            recovered_result.stdout,
            operation_id,
        )

        equals(
            "v49_crash_recovery_kind",
            recovery["recovery"],
            "retired",
        )

        equals(
            "v49_crash_recovery_status",
            recovery["receipt"]["status"],
            "failure",
        )

        equals(
            "v49_crash_recovery_failure",
            recovery["receipt"]["failure"],
            "POST_DISPATCH_PROOF_LOST",
        )

        equals(
            "v49_crash_no_redispatch",
            _dispatch_count(dispatches),
            1,
        )

        check(
            "v49_crash_operation_retired",
            not operation_path.exists(),
            str(operation_path),
        )

        check(
            "v49_crash_failure_receipt_published",
            receipt_path.is_file(),
            str(receipt_path),
        )

        replay = _run(
            env,
            operation_id,
            "on",
        )

        equals(
            "v49_crash_replay_rc",
            replay.returncode,
            2,
        )

        replay_payload = json.loads(
            replay.stdout.strip()
        )

        equals(
            "v49_crash_replay_status",
            replay_payload["status"],
            "failure",
        )

        equals(
            "v49_crash_replay_failure",
            replay_payload["failure"],
            "POST_DISPATCH_PROOF_LOST",
        )

        equals(
            "v49_crash_replay_still_no_redispatch",
            _dispatch_count(dispatches),
            1,
        )
