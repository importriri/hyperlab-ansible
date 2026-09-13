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


def test_v411_expiry_after_dispatching_persist_never_launches():
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-v411-persist-expiry-"
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
            "    # Recompute the budget immediately before launch. The durable dispatching\n"
            "    # transition can itself consume the remaining transaction budget.\n"
            "    # If no launch can occur, restore the durable pre-dispatch phase before\n"
            "    # publishing a terminal failure so recovery never mistakes this for an\n"
            "    # uncertain mutation.\n"
            "    try:\n"
            "        dispatch_timeout = remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n"
        )

        equals(
            "v411_persist_expiry_anchor",
            source.count(anchor),
            1,
        )

        replacement = (
            "    # Recompute the budget immediately before launch. The durable dispatching\n"
            "    # transition can itself consume the remaining transaction budget.\n"
            "    # If no launch can occur, restore the durable pre-dispatch phase before\n"
            "    # publishing a terminal failure so recovery never mistakes this for an\n"
            "    # uncertain mutation.\n"
            "    transaction_deadline = time.monotonic() - 1.0\n"
            "    try:\n"
            "        dispatch_timeout = remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n"
        )

        source = source.replace(
            anchor,
            replacement,
            1,
        )

        operation_id = "1" * 32

        result = _run_v49_source(
            env,
            source,
            operation_id,
            "on",
            timeout=3.0,
        )

        equals(
            "v411_persist_expiry_rc",
            result.returncode,
            2,
        )
        equals(
            "v411_persist_expiry_dispatches",
            _dispatch_count(dispatches),
            0,
        )

        payload = json.loads(
            result.stdout.strip()
        )

        equals(
            "v411_persist_expiry_status",
            payload["status"],
            "failure",
        )
        equals(
            "v411_persist_expiry_reason",
            payload["failure"],
            "TRANSACTION_DEADLINE_EXCEEDED",
        )

        receipts, operations = _operation_dirs(runtime)

        check(
            "v411_persist_expiry_receipt",
            (
                receipts
                / (operation_id + ".json")
            ).is_file(),
        )
        check(
            "v411_persist_expiry_barrier_retired",
            not (
                operations
                / (operation_id + ".json")
            ).exists(),
        )


def test_v411_dispatch_return_after_deadline_retains_barrier():
    with tempfile.TemporaryDirectory(
        prefix="hyperlab-v411-return-expiry-"
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
            "        dispatch_result = subprocess.run(\n"
            "            [\"hyprctl\", \"dispatch\", expression],\n"
            "            text=True,\n"
            "            stdout=subprocess.PIPE,\n"
            "            stderr=subprocess.PIPE,\n"
            "            check=False,\n"
            "            timeout=dispatch_timeout,\n"
            "            env=os.environ.copy(),\n"
            "        )\n"
            "    except subprocess.TimeoutExpired:\n"
        )

        equals(
            "v411_return_expiry_anchor",
            source.count(anchor),
            1,
        )

        replacement = (
            "        dispatch_result = subprocess.run(\n"
            "            [\"hyprctl\", \"dispatch\", expression],\n"
            "            text=True,\n"
            "            stdout=subprocess.PIPE,\n"
            "            stderr=subprocess.PIPE,\n"
            "            check=False,\n"
            "            timeout=dispatch_timeout,\n"
            "            env=os.environ.copy(),\n"
            "        )\n"
            "        transaction_deadline = time.monotonic() - 1.0\n"
            "    except subprocess.TimeoutExpired:\n"
        )

        source = source.replace(
            anchor,
            replacement,
            1,
        )

        operation_id = "2" * 32

        result = _run_v49_source(
            env,
            source,
            operation_id,
            "on",
            timeout=3.0,
        )

        equals(
            "v411_return_expiry_rc",
            result.returncode,
            75,
        )
        equals(
            "v411_return_expiry_dispatches",
            _dispatch_count(dispatches),
            1,
        )

        envelope = json.loads(
            result.stdout.strip()
        )

        equals(
            "v411_return_expiry_status",
            envelope["status"],
            "unknown",
        )
        equals(
            "v411_return_expiry_reason",
            envelope["reason"],
            "TRANSACTION_DEADLINE_EXCEEDED",
        )
        equals(
            "v411_return_expiry_blocker",
            envelope["blocking_operation_id"],
            operation_id,
        )

        receipts, operations = _operation_dirs(runtime)

        receipt_path = (
            receipts
            / (operation_id + ".json")
        )
        operation_path = (
            operations
            / (operation_id + ".json")
        )

        check(
            "v411_return_expiry_no_receipt",
            not receipt_path.exists(),
            str(receipt_path),
        )
        check(
            "v411_return_expiry_barrier_preserved",
            operation_path.is_file(),
            str(operation_path),
        )

        durable = json.loads(
            operation_path.read_text(
                encoding="utf-8"
            )
        )

        equals(
            "v411_return_expiry_durable_phase",
            durable["phase"],
            "dispatching",
        )


def test_v411_launch_budget_is_recomputed_after_durable_transition():
    source = vm._GUEST_FULLSCREEN_TRANSACTION

    first = source.index(
        'record["phase"] = "dispatching"'
    )
    second = source.index(
        "dispatch_timeout = remaining_timeout(DISPATCH_TIMEOUT_SECONDS)",
        first,
    )
    launch = source.index(
        "dispatch_result = subprocess.run(",
        second,
    )

    check(
        "v411_launch_budget_order",
        first < second < launch,
        "dispatching=%r recompute=%r launch=%r"
        % (
            first,
            second,
            launch,
        ),
    )

    between = source[second:launch]

    check(
        "v411_expired_launch_restores_pre_dispatch_phase",
        'record["phase"] = "prepared"' in between
        and 'current_phase = "prepared"' in between
        and "finalize_failure(record, exc.code)" in between,
        between,
    )
