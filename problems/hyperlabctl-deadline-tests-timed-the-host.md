# Two fullscreen deadline tests measured the host's load, not the deadline

Author: [importriri](https://github.com/importriri).

Status: corrected in the tests; covered by the slow-host cases in
`tools/hyperlabctl/tests/test_vm_guest_fullscreen.py`
(`test_stages_share_deadline_even_after_slow_start` and
`test_held_lock_uses_shared_deadline_even_after_slow_start`).

## Symptom

Re-verifying every commit on Nitro while other gates ran, commit `c96d4ed`
failed `hyperlabctl_contract.py`:

```text
FAIL test_v49_accumulated_stage_time_uses_one_shared_deadline -- raised:
subprocess.TimeoutExpired: Command '['/usr/sbin/python3', '-c', ...]' timed out after 2.0 seconds
```

The commit did not touch the guest fullscreen transaction.

## Cause

The affected test made the transaction's two stages sleep 1.6 s against a
1.5 s budget and expected a deadline failure without a dispatch. It also
ran the transaction under a 2.0 s subprocess timeout and required the whole run,
Python's own start included, to take under 1.9 s: about 0.3 s of margin for
an interpreter start on a busy laptop.

The lock contention test beside it had the same flaw twice: it required its
run to take under 0.8 s, and its lock holder released the lock after a fixed
1.0 s, so a transaction that started late found the lock free and
dispatched.

## Fix

The meaning of both tests is in their outcome, and that is kept: a
`TRANSACTION_DEADLINE_EXCEEDED` failure with no dispatch, and exit 75 with no
dispatch while the lock is held. The original correction made the lock
holder keep the lock until the test releases it, so returning at all proves
the transaction gave up on its budget. Subprocess timeouts became 10 s;
the elapsed bounds only excluded a run that waited out another full budget.

## Regression proof

The original regression cases ran both tests with a slow start injected at
the top of the transaction (0.6 s and 1.2 s), as a loaded host does. Under the previous
2.0 s limit the first raised the same `TimeoutExpired` as the gate; both
passed after the original correction.

## Current coverage

The behavioral module now shares the file-backed compositor, transaction
runner and cleanup. The accumulated-stage case advances a controlled clock
by 0.25 s and 1.35 s against the same 1.5 s budget, while still executing
the real embedded transaction. It requires the deadline failure and zero
dispatches both with normal startup and with the original 0.6 s slow start.
The lock case still uses a real lock-holder subprocess and an explicit
ready/release handshake, with the original 1.2 s slow start. It additionally
advances a controlled clock at each lock poll and records elapsed transaction
time at refusal. The wait must use at most the 0.2 s shared budget plus one
0.05 s poll, which distinguishes that deadline from the separate 3 s lock
cap. The holder must still be alive when the transaction refuses; only then
does the test release and reap it. There is no fixed-time lock release.

The 10 s subprocess watchdog bounds cleanup; interpreter startup speed is
no longer an assertion. Ordering uses a separate lock-wait handshake, with
larger first-transaction fixture caps so a slow second interpreter cannot
expire the held dispatch. Both replay and opposite-request cases also run
with a 2.5 s second-interpreter delay. The query-timeout case observes the
actual instances, active-window and clients subprocess timeouts and requires
at most 2 s for each. The clients query has its own explicit 0.5 s cap;
observing the other queries also covers the command's 2 s default. Finally,
persistence time is checked through the timeout passed to the actual dispatch
subprocess. These remain software fixtures, without contacting a compositor
session or a guest.

Removing the shared bound from the lock deadline was observed red at the
controlled elapsed-time assertion. Raising the command default or the explicit
clients cap to 7 s was red at the corresponding timeout assertions.
Restoring the short first-dispatch fixture
cap broke both delayed ordering handshakes. Each restored complete module
passed; the disposable replay commands are in `tests/MUTATIONS.md`.
