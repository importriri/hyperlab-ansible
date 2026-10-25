# The showcase script showed host values on camera

## Failure

Right before the first shot, `tools/showcase/demo.sh` printed the host
name, the user name, the home path and every global address, as the list
of what the published film must not show. Its terminal is the one the
operator watches during the take, so the list itself could be recorded.
The same script let Quickshell's error output through to that terminal on a
failed IPC call, and read an unreadable Machine inventory as "the Machine
does not exist yet", so a broken inventory started the take.

## Cause and fix

The script collected real values to make a checklist that only needs
categories. It now prints a fixed, generic checklist and never asks for the
host name, the user name, the home path or an address. Every tool it calls
has both output streams discarded; a failure prints one fixed `demo:` line
on standard error and exits with status 1. The inventory must be readable
JSON that names the Machine at most once, otherwise the take stops before
the first shot.

## Regression proof

`tests/showcase_contract.py` runs the real script in a temporary
directory. Stubs for `hyperlabctl`, `qs`, `sleep`, the identity commands
(`hostname`, `id`, `ip`, `cat` and others) and the privileged ones answer
with sentinel host, user, home and address values on both streams, and the
environment carries the same sentinels. The complete walkthrough must show
the six shots in order with only the reviewed IPC calls and `hyperlabctl`
arguments; each failure (missing tool, shell not answering, existing
Machine, unreadable inventory, inventory failing during the wait, a Machine
that never runs, no acknowledgement) must exit with 1 and print only its
reason. No sentinel may reach either stream and no identity command may
run. The old printing block fails it with `walkthrough: a private sentinel
(zq7x) reached stdout`; the other breaks are in `tests/MUTATIONS.md`.

The contract proves only the script's own output. Other windows,
notifications and the recorded frames still need the review in
`docs/showcase.md`.
