# A successful operation recorded as failed when an observer left during output

Author: [importriri](https://github.com/importriri).

Status: corrected in source; covered by a deterministic case in
`tests/host_operation_lifecycle_contract.py`.

## Symptom

The full verification run went red once on
`tests/host_operation_lifecycle_contract.py`, in a change that did not touch
the operation runner:

```text
AssertionError: observer reported a stale phase: b'HyperLab reviewed operation:
vm.managed-reboot one\r\r\nBECOME password: \r\r\nauthenticated\r\r\n\r\n
[HyperLab operation failed (exit 125)]\n'
```

The fixture command had authenticated and exited 0; the record said
`failed`, rc 125. Run alone, the contract passed eight times out of eight.

## Diagnosis

rc 125 with reason `execution-unavailable` is what `run()` records when an
exception escapes the execution block. The only path that matched the
transcript is in `relay()`, the loop that pumps the PTY to the transcript and
to observers:

1. one `select` round returns both the PTY master (new output) and an
   observer that has just closed its end (readable at EOF);
2. the master is handled first: `output()` sends the data to every observer,
   the send to the departed one fails, and `output()` removes and closes it;
3. the same round then handles that observer as readable: `recv` on the
   closed socket raises `OSError`, which is read as a departure, and
   `clients.remove()` raises `ValueError` because it was already removed;
4. `ValueError` leaves `relay()`, and `run()` records the operation as
   failed although the command succeeded.

The contract's second observer closes right after reading `authenticated`,
while the fixture is still writing its last line, so the two events can land
in one round. Under load they did.

## Cause

`relay()` iterated over the `select` result without checking that an
observer was still attached by the time its turn came.

## Fix

The observer branch skips an item that is no longer in `clients`: it was
detached earlier in the same round and is already closed.

## Regression proof

`observer_race_contract` in `tests/host_operation_lifecycle_contract.py`
drives `relay()` with a scripted `select`: the observer attaches, then one
round returns the PTY output first and the departed observer second. Before
the fix it fails with `ValueError('list.remove(x): x not in list')`; after
it, the output reaches the transcript and the relay ends normally.
