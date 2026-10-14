# Group 12 asked about the ring without knowing dev-01's stream was live

Seen on Nitro, 2026-10-06, in group 12 (`12-fullscreen-ring-215924`): the
operator answered the three ring questions, and afterwards could not say
whether Looking Glass had shown dev-01's desktop or the waiting logo; the
sender's log had stopped at about 17:36. The three PASS were annulled.

## What happened

Group 12 asked the operator to open Looking Glass and then asked about the
ring at once. Nothing checked that dev-01's sender was streaming to the
client. With no client on the sender, the window shows dev-01 through the
client's SPICE display, which looks like the stream
([`looking-glass-acceptance-asked-before-the-stream.md`](looking-glass-acceptance-asked-before-the-stream.md),
group 16's form of the same fault).

## Fix

Group 12 waits up to 60 s for the health word `ok`, as group 16 does, and
asks nothing before. If the health is not `ok` it fails, names a missing
client when the health is `idle`, and stops with no question asked.
`health_ok` moved from group 16 to `tools/acceptance/lib.sh` so both groups
use the same check.

## Regression proof

`tests/acceptance_scripts_contract.py` runs group 12 against fake tools:

- healthy: the health PASS comes before the first operator answer. Against
  the previous script: `12 asks about the ring before dev-01's stream is
  healthy`;
- health stays `idle`: FAIL, no operator question, STOPPED, the missing
  client named, 13 health answers over 60 s.

The static check that a health step uses `health_ok`, never the command's
exit code, now covers both groups.
