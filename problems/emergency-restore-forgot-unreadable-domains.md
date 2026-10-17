# Emergency restore forgot domains whose state could not be read

## Failure

After an emergency stop, a failed `virsh domstate` during Restore was treated
as evidence that the domain was gone. Restore deleted that domain's record
and could report success while the Machine remained paused and disconnected.
A later retry no longer knew what to restore.

## Cause and fix

`domain_state` returns `None` when libvirt does not answer successfully.
Restore grouped that unknown result with confirmed inactive domain states.
It now reports a failure, retains the record and leaves that domain untouched
until its state is confirmed. Other domains still get restored. Only confirmed
shut-off or crashed states permit discarding the live-state record. Unknown,
shutting-down, power-management-suspended and undefined domains stay recorded
rather than being guessed away.

## Regression proof

`test_panic_restore_keeps_a_domain_whose_state_cannot_be_read` in
`tools/hyperlabctl/tests/test_panic.py` injects a state-query failure for one
paused domain. Before the fix Restore returned 0 instead of 1 and discarded
the record. After the fix it reports the error, retains the on-disk record,
restores the other domain, and a successful retry reconnects and resumes the
retained domain. The test uses a fake libvirt; no live domain is touched.
`test_panic_restore_keeps_unconfirmed_inactive_states` also covers unknown,
shutting-down and power-management-suspended states, each followed by a retry.
