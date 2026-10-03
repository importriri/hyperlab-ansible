# Desk keys did nothing: `hyprctl dispatch` takes Lua under a Lua configuration

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the guest Desk helper contract
with a real Lua interpreter. The physical recheck on `arch-dev-vfio` is
pending.

## Symptom

First physical run of the Workspace Shell on `arch-dev-vfio`: the shell drew,
but `ALT+1` to `ALT+9` did nothing and the session stayed on workspace 1. The
shell's OSD reported the helper's error:

```text
That did not work
Hyprland refused: error: [string "return hl.dispatch(workspace 11)"]:1:
')' expected near '11'
Note: dispatch in lua is a shorthand for hl.dispatch(...)
```

## Root cause

The guest runs Hyprland 0.56 with a Lua configuration. In that mode
`hyprctl dispatch X` is a shorthand for evaluating `hl.dispatch(X)`, so `X`
must be a Lua dispatcher expression. `hyperlab-desk` sent the classic
dispatcher syntax (`workspace 11`, `movetoworkspace 17`, `exec ...`), which
is not Lua.

The helper contract could not see it: its `hyprctl` stand-in accepted the
classic syntax because the classic syntax is what it was written to expect.
The launcher's "Log out" action (`hyprctl dispatch exit`) had the same fault.

## Fix

`hyperlab-desk` sends Lua dispatcher expressions, the same ones the guest
configuration binds:

```text
hl.dsp.focus({workspace = 11})
hl.dsp.window.move({workspace = 17})
hl.dsp.exec_cmd([[cd -- '/home/sid/src' 2>/dev/null; exec kitty]])
```

Commands are quoted as Lua long strings whose fence grows until the content
cannot close it. Project programs no longer use a `[workspace N]` exec rule:
the helper focuses the project's workspace first, so they open there.

"Log out" asks logind to end the session (`loginctl terminate-session`)
instead of dispatching `exit`.

## Regression proof

- `tests/fixtures/fake_hyprctl_lua.py` evaluates every dispatch with a real Lua
  interpreter against a recording `hl.dsp` table, so the classic syntax fails
  in the contract exactly as it fails in Hyprland.
- `tests/guest_desk_helper_contract.py` covers Desk and slot moves, window
  moves, project launches and a command containing `]]` and `]=]`.
- `tests/guest_workspace_shell_contract.py` refuses classic `hyprctl dispatch`
  syntax in the shell and requires the Lua dispatchers in the helper.

## Still open

`hypridle.conf` turns the display off and on with `hyprctl dispatch dpms`, the
same classic syntax. On a headless guest it has no visible effect; it is
listed in the roadmap until the Lua form of the DPMS dispatcher is reviewed.
