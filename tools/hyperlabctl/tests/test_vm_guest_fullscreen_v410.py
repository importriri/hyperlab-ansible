import json
import tempfile
from pathlib import Path

from harness import check, equals
from hyperlabctl.commands import vm
from test_vm_guest_fullscreen_v49 import (
    _dispatch_count,
    _fake_environment,
    _operation_dirs,
    _run_v49_source,
)


def test_v410_deadline_exhaustion_before_dispatch_never_launches():
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-v410-prelaunch-"
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

        anchor = (
            "    # Resolve the dispatch timeout while the durable operation is still\n"
            "    # prepared. Deadline exhaustion here proves that no dispatch was\n"
            "    # launched, so it is a terminal pre-dispatch failure, not uncertainty.\n"
            "    try:\n"
            "        remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n"
        )

        equals(
            "v410_prelaunch_anchor",
            source.count(anchor),
            1,
        )

        replacement = (
            "    # Resolve the dispatch timeout while the durable operation is still\n"
            "    # prepared. Deadline exhaustion here proves that no dispatch was\n"
            "    # launched, so it is a terminal pre-dispatch failure, not uncertainty.\n"
            "    transaction_deadline = time.monotonic() - 1.0\n"
            "    try:\n"
            "        remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n"
        )

        source = source.replace(
            anchor,
            replacement,
            1,
        )

        result = _run_v49_source(
            env,
            source,
            "8" * 32,
            "on",
            timeout=3.0,
        )

        equals(
            "v410_prelaunch_rc",
            result.returncode,
            2,
        )

        check(
            "v410_prelaunch_has_payload",
            bool(result.stdout.strip()),
            "stdout=%r stderr=%r"
            % (
                result.stdout,
                result.stderr,
            ),
        )

        payload = json.loads(
            result.stdout.strip()
        )

        equals(
            "v410_prelaunch_status",
            payload["status"],
            "failure",
        )
        equals(
            "v410_prelaunch_failure",
            payload["failure"],
            "TRANSACTION_DEADLINE_EXCEEDED",
        )
        equals(
            "v410_prelaunch_no_dispatch",
            _dispatch_count(dispatches),
            0,
        )


def test_v410_successful_command_result_after_deadline_is_rejected():
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-v410-postrun-"
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

        source = vm._GUEST_FULLSCREEN_TRANSACTION

        anchor = (
            "        )\n"
            "    except subprocess.TimeoutExpired as exc:\n"
            "        if time.monotonic() >= transaction_deadline:\n"
            "            raise TxnFailure(\"TRANSACTION_DEADLINE_EXCEEDED\") from exc\n"
            "        raise TxnFailure(failure_code + \"_TIMEOUT\") from exc\n"
            "    if time.monotonic() >= transaction_deadline:\n"
            "        raise TxnFailure(\"TRANSACTION_DEADLINE_EXCEEDED\")\n"
            "    if result.returncode != 0:\n"
        )

        equals(
            "v410_postrun_command_anchor",
            source.count(anchor),
            1,
        )

        replacement = (
            "        )\n"
            "        if current_phase == \"dispatched\":\n"
            "            globals()[\"transaction_deadline\"] = time.monotonic() - 1.0\n"
            "    except subprocess.TimeoutExpired as exc:\n"
            "        if time.monotonic() >= transaction_deadline:\n"
            "            raise TxnFailure(\"TRANSACTION_DEADLINE_EXCEEDED\") from exc\n"
            "        raise TxnFailure(failure_code + \"_TIMEOUT\") from exc\n"
            "    if time.monotonic() >= transaction_deadline:\n"
            "        raise TxnFailure(\"TRANSACTION_DEADLINE_EXCEEDED\")\n"
            "    if result.returncode != 0:\n"
        )

        source = source.replace(
            anchor,
            replacement,
            1,
        )

        operation_id = "9" * 32

        result = _run_v49_source(
            env,
            source,
            operation_id,
            "on",
            timeout=3.0,
        )

        # Dispatch has already returned exact "ok". Once the post-dispatch
        # observation crosses the shared deadline, neither success nor a
        # terminal failure can be proven. Preserve the durable barrier.
        equals(
            "v410_postrun_rc",
            result.returncode,
            75,
        )
        equals(
            "v410_postrun_no_terminal_stdout",
            result.stdout,
            "",
        )
        equals(
            "v410_postrun_one_dispatch",
            _dispatch_count(dispatches),
            1,
        )

        receipts, operations = _operation_dirs(runtime)

        operation_path = (
            operations
            / (operation_id + ".json")
        )
        receipt_path = (
            receipts
            / (operation_id + ".json")
        )

        check(
            "v410_postrun_barrier_preserved",
            operation_path.is_file(),
            str(operation_path),
        )
        check(
            "v410_postrun_no_terminal_receipt",
            not receipt_path.exists(),
            str(receipt_path),
        )

        durable = operation_path.read_text(
            encoding="utf-8"
        )

        check(
            "v410_postrun_durable_dispatched",
            '"phase":"dispatched"' in durable,
            durable,
        )


def test_v410_remaining_timeout_never_overruns_remaining_budget():
    source = vm._GUEST_FULLSCREEN_TRANSACTION

    check(
        "v410_no_one_ms_floor",
        "max(0.001, remaining)" not in source,
    )
    check(
        "v410_exact_remaining_bound",
        "return min(float(cap), remaining)" in source,
    )


def test_v410_mixed_same_pid_inventory_is_not_bound_or_expired():
    source = vm._GUEST_FULLSCREEN_TRANSACTION

    check(
        "v410_same_pid_ambiguity_guard",
        "if len(same_pid) > 1:" in source
        and "return SESSION_UNKNOWN" in source,
    )

    check(
        "v410_single_same_pid_mismatch_unknown",
        "if same_pid[0] != expected:" in source
        and "return SESSION_UNKNOWN" in source,
    )
