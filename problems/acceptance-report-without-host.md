# The acceptance report named no host

Seen by the operator on Nitro, 2026-10-06, running
`tools/acceptance/07-network-isolation.sh`:

    tools/acceptance/lib.sh: line 40: hostname: command not found
    group 07-network-isolation on  at 2026-10-06T17:23:48+02:00

## Cause

`acceptance_start` wrote the report header with `$(hostname)`. Arch
installs that command only with `inetutils`, which the Nitro does not have,
so the header said "on  at" and the evidence did not say where it ran. The
checks themselves were not affected.

## Fix

The header reads the kernel's own name from `/proc/sys/kernel/hostname`
with a shell redirection, which needs no package at all.

## Test

`tests/acceptance_scripts_contract.py` now refuses any acceptance script or
`lib.sh` line that runs `hostname`, and its run of `lib.sh` requires the
report to name the host from `/proc/sys/kernel/hostname`. It fails on the
code before the fix.
