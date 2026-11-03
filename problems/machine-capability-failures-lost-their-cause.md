# Machine capability failures lost their cause

## Observation

During the read-only Nitro capture session on 2026-11-02, in Hyprland with
`qs -c hyperlab`, every action on the selected Machine card showed
"The machine bridge did not answer". No Machine was started or changed.
The installed executable, permissions and timing were not inspected here;
the original installed failure remains an operator gate.

## Software findings and fix

A real isolated Quickshell process reproduces two defects. A bridge refusal
on stdout with no stderr loses its known reason in `ShellState`. An absent
or non-executable bridge never emits `exited`, leaving capabilities loading
indefinitely. A successful inert bridge returns its JSON normally: there is
no evidence here of a general stdout ordering failure.

The shipped bridge writes refusals to stderr as well as stdout. On the
Nitro, the old generic sentence therefore points to empty stderr (for
example an interrupted process, or invalid output with exit 0) or the
Connect header's literal; the stdout-only fixture does not identify that
installed cause.

The observed sentence came from two places. `ShellState` used it as the
fallback detail when the answer was invalid and stderr was empty, and
`MachineContextPane.qml` printed it as the Connect header whenever the
capabilities were unavailable, even when `ShellState` held a known cause.
The header now shows the recorded cause, as the disabled action rows do.

The shell now preserves a structured refusal and distinguishes empty data,
invalid data, nonzero exit and interruption. A failed start is reported after
5 seconds, followed by bounded `/usr/bin/test -e` and `-x` probes of the
executable path. The result names an absent/unreadable path, a file without
execute permission, or a failure despite an executable path. An unavailable
or stalled inspection reports its own failure; it never enables an action.
A running capability read
has a 180-second total budget for the sequence of bounded backend reads.
A newer selection cancels its previous bridge process, and a spent request
cannot be overwritten by a duplicate or late callback. Cancellation signals
the bridge only; it does not promise cleanup of CLI descendants.

## Regression proof and remaining gate

`tests/machine_capability_transport_contract.py` runs production
`MachineActions.qml` with real Quickshell processes and inert executables,
and the real `ShellState` validation with its unrelated inputs removed.
It covers success, structured refusal, empty and malformed output, exit,
interruption, timeout, missing/non-executable bridge, replacement and clear.
It shortens the timers in the disposable copy; it does not measure Nitro
latency. Removing either deadline or the refusal reason makes it fail.
Collapsing absent and non-executable paths into one sentence also fails.
The `capabilities-unavailable` scenario of
`tests/host_quickshell_runtime_contract.py` renders the pane and fails if its
Connect header hides a stderr cause or a stdout-only refusal.

On Nitro, select a Machine and use an already available action. It must
answer or give its actual known cause. If the start check fails, inspect
`/usr/local/bin/privatestack-machine-actions` and its execute permissions;
if the bridge starts, retain its read-only `capabilities NAME` response and
stderr. This software result does not establish why the installed session
failed or accept a real lifecycle operation.
