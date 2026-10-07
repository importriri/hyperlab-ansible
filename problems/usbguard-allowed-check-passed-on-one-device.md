# Group 11's "attached devices allowed" passed on one allowed device

Found in the review of the acceptance scripts on 2026-10-06. Group 11 stays
verified on Nitro (`11-usbguard-215605`): `usbguard list-devices --blocked`
then showed only the new stick blocked. The check itself was weak.

## What was wrong

`expect "attached devices allowed" '^[0-9]+: allow' … usbguard
list-devices` passed when any one line was an allow: a policy that allowed
one device and blocked the keyboard would have passed.

## Fix

The check counts the allow rows of `usbguard list-devices` and the USB
devices the kernel reports in `/sys/bus/usb/devices` (the same basis the
role uses before installing a policy), and passes only when they are equal
and no row is a block or a reject.

## Test

`tests/acceptance_scripts_contract.py` runs group 11 in a pseudo-terminal
with three fake USB devices: three allowed passes, one allowed fails, and
three allowed with a blocked one fails. It fails on the previous script.
