# The acceptance report named a commit while the checkout differed from it

Seen on 2026-10-06 in group 7 (`07-network-isolation-172348`): the report
said `repository 223473b` (the commit published as `02ff09e`), while
the operator's prompt showed `main [+⇡]`, staged changes in the checkout
the run came from. The exact tree that ran is not known; that run's
evidence is the loaded ruleset and the kernel's counters.

## Cause

The header printed `git rev-parse --short HEAD` and nothing else, so a
changed checkout looked like the commit.

## Fix

The header marks the commit `+dirty` when tracked files differ from it,
staged or not, and keeps the redacted `git diff --stat HEAD` in the
evidence. Untracked files do not make a run dirty but are counted and
listed in the evidence.

## Test

`tests/acceptance_scripts_contract.py` runs the report header in a
temporary repository: clean, with a modified file (holding a password that
must not reach the evidence), with the change only staged, and with an
untracked file. It fails on the code before the fix with "a modified
tracked file is not +dirty".
