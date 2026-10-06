# The problem index missed notes and listed one twice

Found on 2026-10-06 while indexing a new note.

## What was wrong

`problems/README.md` is how a note is found from its symptom, but nothing
checked it. Five notes had never been listed
(`guests-reached-host-services.md`,
`guest-capture-device-reaches-host-microphone.md`,
`operation-relay-observer-race.md`, `qemu-processes-share-one-identity.md`,
`emergency-stop-blocked-by-its-record.md`), and
`acceptance-report-without-host.md` was listed twice: an index edit ran
twice, once in a command the operator had rejected after it had already
started, and once again in the commit that followed.

## Fix

The five notes are listed and the duplicate is gone.

## Test

`tests/docs_contract.py` requires every note in `problems/` to appear in
the index exactly once. It fails on the previous index with
"problems/README.md lists acceptance-report-without-host.md 2 times, not
once".
