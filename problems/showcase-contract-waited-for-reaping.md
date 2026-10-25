# The showcase contract waited for the shell to reap a finished client

Seen in CI on `main` at f745103, 2026-10-25: `tests/showcase_contract.py`
failed with "Looking Glass failing during shot 5: the Looking Glass stub
did not end". The same contract passed on the operator's machine.

## What was wrong

The contract runs `tools/showcase/demo.sh` with whatever `sh` is first in
`PATH`: Bash on Arch, dash on the Ubuntu runner. In the two Looking Glass
failure cases the `hyperlabctl open looking-glass` stub writes its PID and
exits with an error. Before answering shot 5's (or shot 6's) prompt the
fixture waited for that stub to end, and took "ended" to mean that
`/proc/PID` was gone.

`/proc/PID` stays until the parent reaps the child. An exited child stays
in the process table, in state `Z`, until then. Bash reaps a background
job as soon as it ends. dash and BusyBox `sh` leave the zombie there while
`read` waits for the operator's Enter. The fixture would not press Enter
before the zombie was gone, and the zombie would not go before Enter was
pressed. After ten seconds the fixture gave up.

The script was right. Under dash 0.5.12-12ubuntu3 (the runner's) and
BusyBox 1.36.1, once the prompt is answered the take stops at shot 5 with
`demo: Looking Glass failed for demo-01; stop the take` and status 1, as
it does under Bash.

## Fix

The fixture's `exited()` reads `/proc/PID/stat`. A missing entry or state
`Z` counts as exited, any other state as running. The line must have the
whole layout Linux 3.5 and later print: the PID, the command in
parentheses, a one-letter state and 49 numbers. A line it cannot read or
that lacks any of these, or a missing proc filesystem, is an error, never
an exit. The PID file is read once per attempt; a missing, empty or
unfinished file (no newline yet) means the stub has not written its PID
yet, and anything else that is not a PID is an error. The script was not
changed.

## Test

`check_exit_predicate()` runs before the take. It starts a real child and
waits for it with `os.waitid(..., WEXITED | WNOWAIT)`, which returns once
the child has exited and leaves it unreaped, and requires `exited()` to
call it finished. It requires a child blocked on its open standard input
not to be. Neither depends on timing. A made-up proc tree covers `S` and
`Z`, a command name holding `) ` or a newline, a missing PID, a missing
proc filesystem, lines without the opening parenthesis, the closing one or
the trailing fields, and an unreadable one. The PID file reader has its own
cases, and a counting path requires it to read the file once. With the
previous existence check the contract fails on any shell: "exit
predicate: an exited, unreaped child counts as running".

With `sh` resolved to the runner's dash the unchanged contract reproduced
the CI failure and the corrected one passes. BusyBox runs its builtin
`sleep` instead of the fixture's stub, so under BusyBox the walkthrough
stops earlier, at its `sleep` check; the Looking Glass cases alone pass.
