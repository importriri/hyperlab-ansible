# The USBGuard check mode failed on a host that never had USBGuard

Seen by the operator on Nitro, 2026-10-06, in group 11's first run
(`11-usbguard-215301`, before USBGuard was installed). The full log:

    TASK [host_usbguard : Install USBGuard]                     changed
    TASK [host_usbguard : Ask USBGuard for a policy that allows every attached device]   skipping
    TASK [host_usbguard : Refuse a generated policy that would block an attached device]
    fatal: … "usbguard generate-policy allowed 0 devices but the kernel reports 4; …"

The second run, with USBGuard installed and its policy in place, passed.

## Cause

Ansible skips a `command` task in check mode. `usbguard generate-policy`
was skipped, its output was empty, and the safeguard that refuses a policy
missing a device refused the empty one. Behind it, the daemon setting and
the service start would have failed too in check mode on that host: the
configuration file and the unit come with the package.

## Fix

`generate-policy` only prints a policy, so it runs in check mode too
(`check_mode: false`) and the safeguard sees the policy the run would
install. When the `usbguard` command is absent in check mode, the run says
that it cannot preview the policy and what the apply will do, and skips
only the generation, the daemon setting and the service start. A run that
changes the host always has the package by then, so nothing is skipped
there.

## Test

`tests/host_usbguard_contract.py` requires `generate-policy` to run in
check mode, the describe-only state to hold only in check mode without the
command, and the three steps that need the package to skip only then. It
fails on the previous role with "check mode skips generate-policy". The run
itself is to be seen in the lab host, a host that never had USBGuard.
