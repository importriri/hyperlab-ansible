# rofi opened on a guest whose Workspace Shell was running

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the guest workspace shell
contract. The physical recheck on `dev-01` is pending.

## Symptom

On `dev-01`, with the Workspace Shell up and its key sheet open, the plain
rofi application list appeared instead of the shell's launcher.

## Root cause

Two paths reached rofi while the shell was running:

- `ALT+R` was bound straight to `rofi -show drun` and listed on the key
  sheet as the plain app menu;
- the key helper fell back to rofi on any failed IPC call, so a shell that
  was up but slow to answer was replaced by rofi.

## Fix

`ALT+R` and its key sheet entry are gone. The helper asks a running shell up
to three times and logs a shell that never answers; rofi stands in only when
no shell process of this user is running.

## Regression proof

`tests/guest_workspace_shell_contract.py` runs the helper with fake `qs`,
`pgrep` and `rofi`: a reachable shell is used once, a slow running shell is
asked again, a running shell that never answers is logged and not replaced,
and only a session without its shell gets rofi. No key binding may run rofi
directly.
