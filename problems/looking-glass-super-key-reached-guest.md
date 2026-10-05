# A host shortcut reached a guest terminal as "8;10u"

Author: [importriri](https://github.com/importriri).

Status: corrected in the opener for Linux guests; covered by
`tests/looking_glass_host_modifier_contract.py`; not yet proven on Nitro.

## Symptom

Text such as `8;10u` appeared at the prompt of a terminal in `dev-01`, seen
through Looking Glass.

## Cause

`8;10u` is the tail of a kitty keyboard report, `ESC [ <key> ; <modifiers> u`.
The guest terminal is kitty and the shell is Bash. Given such a report, Bash's
readline matches the start of it against its own escape bindings, beeps, and
inserts the rest. With modifiers `10` (shift and super), only three keys leave
exactly `8;10u`: `b` (98), `l` (108) and `v` (118), that is SUPER+SHIFT+B, L
or V. On the host SUPER+SHIFT+L moves a window right.

The guest binds nothing to SUPER: its compositor uses ALT
(`roles/guest_desktop_hyprland/templates/hyprland.lua.j2`, "Host = SUPER;
guest = ALT"). The Looking Glass client, though, passed the SUPER key to the
guest (`input:ignoreWindowsKeys` defaults to no). While the client holds the
keyboard the host compositor's shortcuts do not fire, so a host shortcut
went to whatever guest application had focus, and the terminal received a key
it has no meaning for.

Not seen: which of the three keys was pressed, and kitty producing the
report. The contract reproduces the second half: Bash given SUPER+SHIFT+L's
report shows `8;10u`.

## Fix

`hyperlabctl open looking-glass` starts the client with
`input:ignoreWindowsKeys=yes` for a Linux guest, so SUPER is never a guest
key. A Windows guest keeps its Windows key, which it uses. A host shortcut
pressed while the client holds the keyboard now reaches the guest without
SUPER (SUPER+SHIFT+L types `L`): host shortcuts during capture remain the open
gate of [`looking-glass-input-isolation.md`](looking-glass-input-isolation.md).

## Regression proof

`tests/looking_glass_host_modifier_contract.py` shows the symptom with an
interactive Bash, checks that the opener withholds SUPER from Linux guests
only, and checks that the guest compositor binds nothing to SUPER. It fails
against the previous opener.
