# A failed patch reconstruction truncated the reviewed overlay

Author: [importriri](https://github.com/importriri).

## Symptom

During reconstruction of the AN515-55 source overlay, the repository patch file
became zero bytes even though the preceding transformation had failed.

The running module and pinned source checkout were unaffected, but the candidate
repository had lost the local overlay contents.

## What was wrong

Shell redirection opens the destination before the command on its left has
proved that useful output can be produced.

A command shaped like:

```text
diff ... > roles/nitro_sense/files/an515-55-four-zone.patch
```

therefore made the managed patch itself the transaction target. When the
temporary input preparation failed, the destination had already been
truncated.

## Fix

Never generate a reviewed source overlay directly into its repository path.

Build the candidate patch under `/tmp`, verify that it is non-empty, dry-run it
against a pristine copy of the exact pinned source, compile that patched copy
through the role build recipe and calculate the final SHA-256. Only then replace
the repository patch.

The pinned source checkout remains pristine throughout. It is evidence of the
requested upstream identity, not a scratch worktree.

## Regression proof

The replacement AN515-55 overlay was generated from the pristine pinned commit,
dry-run successfully, compiled with the role-style hardened-kernel build and
then installed as the repository patch.

Its final SHA-256 is
`1a53b4709330ae86dcae16f2efd55ce9468e2cd2d850b48d0f6902641457a778`.
The same hash is recorded by role defaults and the installed build stamp.
