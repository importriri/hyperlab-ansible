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


ROLLBACK = (
    "    try:\n"
    "        dispatch_timeout = remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n"
    "    except TxnFailure as exc:\n"
    "        record = dict(record)\n"
    "        record[\"phase\"] = \"prepared\"\n"
    "        replace_json(operation_path, record)\n"
    "        current_phase = \"prepared\"\n"
    "        finalize_failure(record, exc.code)\n"
)


def test_v412_rollback_write_failure_keeps_conservative_barrier():
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-v412-write-failure-"
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

        transaction = vm._GUEST_FULLSCREEN_TRANSACTION

        equals(
            "v412_write_failure_anchor",
            transaction.count(ROLLBACK),
            1,
        )

        replacement = (
            "    transaction_deadline = time.monotonic() - 1.0\n"
            "    try:\n"
            "        dispatch_timeout = remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n"
            "    except TxnFailure as exc:\n"
            "        record = dict(record)\n"
            "        record[\"phase\"] = \"prepared\"\n"
            "        raise OSError(\"injected rollback persistence failure\")\n"
            "        current_phase = \"prepared\"\n"
            "        finalize_failure(record, exc.code)\n"
        )

        transaction = transaction.replace(
            ROLLBACK,
            replacement,
            1,
        )

        operation_id = "3" * 32

        result = _run_v49_source(
            env,
            transaction,
            operation_id,
            "on",
            timeout=3.0,
        )

        equals(
            "v412_write_failure_zero_dispatch",
            _dispatch_count(dispatches),
            0,
        )

        receipts, operations = _operation_dirs(runtime)
        operation = operations / (operation_id + ".json")
        receipt = receipts / (operation_id + ".json")

        check(
            "v412_write_failure_barrier_present",
            operation.is_file(),
            str(operation),
        )
        check(
            "v412_write_failure_no_receipt",
            not receipt.exists(),
            str(receipt),
        )

        durable = json.loads(
            operation.read_text(encoding="utf-8")
        )

        equals(
            "v412_write_failure_durable_phase",
            durable["phase"],
            "dispatching",
        )

        check(
            "v412_write_failure_not_false_success",
            result.returncode != 0,
            result.stdout,
        )

        recovered = _run_v49_source(
            env,
            vm._GUEST_FULLSCREEN_TRANSACTION,
            operation_id,
            "recover",
            timeout=3.0,
        )

        equals(
            "v412_write_failure_recovery_rc",
            recovered.returncode,
            0,
        )

        recovery = json.loads(
            recovered.stdout.strip()
        )

        equals(
            "v412_write_failure_recovery_state",
            recovery["recovery"],
            "still-unresolved",
        )

        equals(
            "v412_write_failure_recovery_dispatches",
            _dispatch_count(dispatches),
            0,
        )

        check(
            "v412_write_failure_barrier_after_recovery",
            operation.is_file(),
            str(operation),
        )
        check(
            "v412_write_failure_no_receipt_after_recovery",
            not receipt.exists(),
            str(receipt),
        )


def test_v412_interruption_after_rollback_retries_and_replays_same_operation():
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-v412-interruption-"
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

        transaction = vm._GUEST_FULLSCREEN_TRANSACTION

        equals(
            "v412_interruption_anchor",
            transaction.count(ROLLBACK),
            1,
        )

        replacement = (
            "    transaction_deadline = time.monotonic() - 1.0\n"
            "    try:\n"
            "        dispatch_timeout = remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n"
            "    except TxnFailure as exc:\n"
            "        record = dict(record)\n"
            "        record[\"phase\"] = \"prepared\"\n"
            "        replace_json(operation_path, record)\n"
            "        current_phase = \"prepared\"\n"
            "        raise SystemExit(99)\n"
            "        finalize_failure(record, exc.code)\n"
        )

        interrupted = transaction.replace(
            ROLLBACK,
            replacement,
            1,
        )

        operation_id = "4" * 32

        first = _run_v49_source(
            env,
            interrupted,
            operation_id,
            "on",
            timeout=3.0,
        )

        equals(
            "v412_interruption_first_rc",
            first.returncode,
            99,
        )
        equals(
            "v412_interruption_zero_dispatch",
            _dispatch_count(dispatches),
            0,
        )

        receipts, operations = _operation_dirs(runtime)
        operation = operations / (operation_id + ".json")
        receipt = receipts / (operation_id + ".json")

        check(
            "v412_interruption_prepared_barrier",
            operation.is_file(),
            str(operation),
        )
        check(
            "v412_interruption_no_receipt",
            not receipt.exists(),
            str(receipt),
        )

        durable = json.loads(
            operation.read_text(encoding="utf-8")
        )

        equals(
            "v412_interruption_phase",
            durable["phase"],
            "prepared",
        )

        resumed = _run_v49_source(
            env,
            vm._GUEST_FULLSCREEN_TRANSACTION,
            operation_id,
            "on",
            timeout=3.0,
        )

        equals(
            "v412_same_operation_resume_rc",
            resumed.returncode,
            0,
        )
        equals(
            "v412_same_operation_exactly_one_dispatch",
            _dispatch_count(dispatches),
            1,
        )

        payload = json.loads(
            resumed.stdout.strip()
        )

        equals(
            "v412_same_operation_resume_status",
            payload["status"],
            "success",
        )

        check(
            "v412_same_operation_receipt",
            receipt.is_file(),
            str(receipt),
        )
        check(
            "v412_same_operation_barrier_retired",
            not operation.exists(),
            str(operation),
        )

        replayed = _run_v49_source(
            env,
            vm._GUEST_FULLSCREEN_TRANSACTION,
            operation_id,
            "on",
            timeout=3.0,
        )

        equals(
            "v412_same_operation_replay_rc",
            replayed.returncode,
            0,
        )
        equals(
            "v412_same_operation_replay_no_redispatch",
            _dispatch_count(dispatches),
            1,
        )

        replay_payload = json.loads(
            replayed.stdout.strip()
        )

        equals(
            "v412_same_operation_replay_status",
            replay_payload["status"],
            "success",
        )
        equals(
            "v412_same_operation_replay_id",
            replay_payload["operation_id"],
            operation_id,
        )


def test_v412_persistence_time_reduces_effective_launch_budget():
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-v412-budget-"
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

        probe = Path(temp) / "budget.txt"
        env["HL412_BUDGET_FILE"] = str(probe)

        transaction = vm._GUEST_FULLSCREEN_TRANSACTION

        initial = (
            "    try:\n"
            "        remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n"
            "    except TxnFailure as exc:\n"
        )

        equals(
            "v412_budget_initial_anchor",
            transaction.count(initial),
            1,
        )

        transaction = transaction.replace(
            initial,
            (
                "    transaction_deadline = time.monotonic() + 1.5\n"
                "    try:\n"
                "        probe_initial_timeout = remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n"
                "    except TxnFailure as exc:\n"
            ),
            1,
        )

        phase = (
            "    record[\"phase\"] = \"dispatching\"\n"
            "    replace_json(operation_path, record)\n"
            "    current_phase = \"dispatching\"\n"
        )

        equals(
            "v412_budget_phase_anchor",
            transaction.count(phase),
            1,
        )

        transaction = transaction.replace(
            phase,
            phase + "    time.sleep(0.15)\n",
            1,
        )

        launch = (
            "        dispatch_timeout = remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n"
        )

        equals(
            "v412_budget_launch_anchor",
            transaction.count(launch),
            1,
        )

        transaction = transaction.replace(
            launch,
            launch
            + (
                "        with open(os.environ[\"HL412_BUDGET_FILE\"], "
                "\"w\", encoding=\"utf-8\") as probe_handle:\n"
                "            probe_handle.write("
                "str(probe_initial_timeout) + \"\\n\" + "
                "str(dispatch_timeout) + \"\\n\")\n"
            ),
            1,
        )

        result = _run_v49_source(
            env,
            transaction,
            "5" * 32,
            "on",
            timeout=3.0,
        )

        equals(
            "v412_budget_rc",
            result.returncode,
            0,
        )
        equals(
            "v412_budget_one_dispatch",
            _dispatch_count(dispatches),
            1,
        )

        values = [
            float(item)
            for item in probe.read_text(
                encoding="utf-8"
            ).splitlines()
            if item.strip()
        ]

        equals(
            "v412_budget_probe_values",
            len(values),
            2,
        )

        before, launch_budget = values

        check(
            "v412_budget_initial_below_dispatch_cap",
            1.0 < before < 1.6,
            repr(values),
        )
        check(
            "v412_budget_positive_launch",
            launch_budget > 0,
            repr(values),
        )
        check(
            "v412_budget_reduced",
            launch_budget < before - 0.08,
            repr(values),
        )
        check(
            "v412_budget_elapsed_accounted",
            launch_budget < 1.45,
            repr(values),
        )
