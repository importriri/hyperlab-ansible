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

## Follow-up: refuse a start line without a timezone

The original fixture fix established that the valid managed writer's
offset-carrying line and group 16's epoch argument name absolute times.
It did not establish refusal of malformed input. The judge still accepted
a parseable start without an offset, including a date-only value, through
`datetime.timestamp()` in the checking machine's local zone.

The judge now parses once and requires a timezone with a defined UTC
offset before converting to epoch seconds. Missing, empty, malformed and
timezone-free starts produce an ordinary failed finding. No timezone is
assumed, and a sender starting exactly at `--since` remains accepted.

In all four existing POSIX zones, the contract checks independently
specified equivalent +02:00, +00:00, Z and negative-offset starts, the
inclusive boundary and a start one second before it. Invalid starts use
`--since 0` so refusal cannot be explained by staleness. The real local
CLI exercises both `--input` and standard input with the repository's
build pins: valid fresh starts exit 0; invalid starts exit 1 with a
`WRONG` timestamp finding and no traceback. These are software fixtures;
the physical sender and stream still need their existing acceptance run.
