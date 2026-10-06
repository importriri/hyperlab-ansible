# A failed check mode left only the recap where the report pointed

Seen by the operator on Nitro, 2026-10-06, in group 11
(`11-usbguard-215301`): the report said

    FAIL  usbguard check mode  (evidence: …/usbguard-check-mode.log)

and that log held only the play recap, `ok=8 changed=1 failed=1
skipped=1`.

## Cause

`check NAME playbook WHY …` keeps two logs. `playbook` writes the whole
redacted run to `<why>.log` (`usbguard-check.log`) and prints only its last
three lines; `check` saves what it sees to `<name>.log`
(`usbguard-check-mode.log`) and names that one in the FAIL line. The full
log existed, under another name nobody was pointed to, and the report never
said which task failed or why. Read later, the full log showed:

    TASK [host_usbguard : Refuse a generated policy that would block an attached device]
    "msg": "usbguard generate-policy allowed 0 devices but the kernel reports 4; …"

## Fix

`playbook` names its full log in the report, and after a failed run it
writes each failed task's name and message, from the already redacted log,
into the report and into the check's own log.

## Test

`tests/acceptance_scripts_contract.py` runs a check of a fake
`ansible-playbook` that fails like the first group 11 run and requires the
task name, its message (with a token redacted) and the full log's path in
the report. It fails on the code before the fix with "the report does not
name the failed task".
