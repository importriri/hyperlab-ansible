# The sender-identity contract passed only in the operator's time zone

Seen in CI on `main` at 13af138, 2026-10-25: `tests/acceptance_scripts_contract.py`
failed with "a sender of this build was refused". The same contract passed
on the operator's machine.

## What was wrong

`check_sender_identity()` (since 7be35ac) feeds
`tools/acceptance/sender_identity.py` a probe whose sender started at
`2026-10-06T22:30:39+02:00`, and gives it the test step's start as
`time.mktime(time.strptime("2026-10-06 22:30:00", ...))`. `mktime` reads
that naive time in the zone the contract runs in. In Europe/Rome (CEST on
that date) the step began 39 s before the sender, as meant. On the UTC
runner it began at 22:30 UTC, two hours after the sender, and the
"started after the test began" finding refused it.

The tool itself was right: group 16 passes `date +%s` epoch seconds and
the sender's start line carries its own offset, so both sides are
absolute times.

## Fix

The contract writes the step's start with the same explicit offset as the
probe (`datetime.fromisoformat("2026-10-06T22:30:00+02:00")`), so it
names one instant in every zone.

## Test

`check_sender_identity_in_every_zone()` runs the whole identity check
under four POSIX zone strings, UTC, the operator's CET/CEST, +14 and -10,
and first requires each one to be in effect, since the C library falls
back to UTC on a zone it does not understand. With the previous `mktime`
line it fails on the operator's machine too: "a sender of this build was
refused (TZ=UTC0)".
