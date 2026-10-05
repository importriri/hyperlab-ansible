# Two fullscreen deadline tests measured the host's load, not the deadline

Author: [importriri](https://github.com/importriri).

Status: corrected in the tests; covered by the slow-host cases in
`tools/hyperlabctl/tests/test_vm_guest_fullscreen_v49.py`.

## Symptom

Re-verifying every commit on Nitro while other gates ran, commit `c96d4ed`
failed `hyperlabctl_contract.py`:

```text
FAIL test_v49_accumulated_stage_time_uses_one_shared_deadline -- raised:
subprocess.TimeoutExpired: Command '['/usr/sbin/python3', '-c', ...]' timed out after 2.0 seconds
```

The commit did not touch the guest fullscreen transaction.

## Cause

The test makes the transaction's two stages sleep 1.6 s against a 1.5 s
budget and expects a deadline failure without a dispatch. It also ran the
transaction under a 2.0 s subprocess timeout and required the whole run,
Python's own start included, to take under 1.9 s: about 0.3 s of margin for
an interpreter start on a busy laptop.

The lock contention test beside it had the same flaw twice: it required its
run to take under 0.8 s, and its lock holder released the lock after a fixed
1.0 s, so a transaction that started late found the lock free and
dispatched.

## Fix

The meaning of both tests is in their outcome, and that is kept: a
`TRANSACTION_DEADLINE_EXCEEDED` failure with no dispatch, and exit 75 with no
dispatch while the lock is held. The lock holder now keeps the lock until
the test releases it, so returning at all proves the transaction gave up on
its budget. Subprocess timeouts are 10 s; the elapsed bounds only exclude a
run that waited out another full budget.

## Regression proof

New cases run both tests with a slow start injected at the top of the
transaction (0.6 s and 1.2 s), as a loaded host does. Under the previous
2.0 s limit the first raises the same `TimeoutExpired` as the gate; both
pass now.
