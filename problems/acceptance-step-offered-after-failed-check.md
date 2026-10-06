# A destructive step was offered after its check mode failed

Seen by the operator on Nitro, 2026-10-06, in group 11
(`11-usbguard-215301`): "usbguard check mode" failed, and the script still
stopped at "turn on USBGuard: every USB device not attached now stays
blocked". The operator confirmed it; the block was turned on.

## Cause

`check` recorded a FAIL and returned success either way, and the step that
the check mode previews did not look at its result. Group 7 had the same
shape: "foundation check mode", then "apply playbooks/foundation.yml".

## Fix

`check` returns 1 when it records a FAIL. In groups 7 and 11 the
destructive step sits inside `if check … --check`, and the else reports
"BLOCK NOT OFFERED" or "APPLY NOT OFFERED": nothing is changed after a
failed dry run.

## Test

`tests/acceptance_scripts_contract.py` requires every check mode in every
acceptance script to guard the confirmations after it, with an else that
says the step was not offered. It also runs group 11 against a fake
playbook: a failed check mode must report "BLOCK NOT OFFERED" and stop at
no confirmation, a clean one must stop at the block. Both fail on the code
before the fix.
