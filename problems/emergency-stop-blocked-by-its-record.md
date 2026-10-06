# The emergency stop did nothing when its record was unusable

Found in review of the emergency stop (ADR 0047) before it reached main.

## What happened

`hyperlabctl panic engage` read its record
(`$XDG_RUNTIME_DIR/hyperlab/panic.json`) and wrote it before touching any
domain. A record that could not be read (malformed, wrong mode, a symlink)
or a directory it could not write raised an error at that point, so the
key cut no network and paused no Machine: the one control meant to work
when something is wrong failed closed in the wrong direction.

## Fix

The stop no longer waits on its record. An unreadable record is reported,
left as it is, and every running Machine is still cut and paused; a record
that cannot be written is reported and the stop carries on. The output
then says Restore cannot undo that press and the Machines must be resumed
by hand.

## Test

`tools/hyperlabctl/tests/test_panic.py`,
`test_panic_engage_stops_even_when_its_record_is_unusable`: a malformed
record and a read-only record directory; both still pause and cut every
running domain, exit non-zero and say so. It fails on the code before the
fix.
