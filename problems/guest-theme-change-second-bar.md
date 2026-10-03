# A theme change would have started Waybar beside the Workspace Shell

Author: [importriri](https://github.com/importriri).

Status: corrected before the Workspace Shell shipped; pinned by the guest
workspace shell contract.

## Symptom

Found while wiring the Workspace Shell, before any guest ran it. With the
shell as the session bar, `ALT+SHIFT+T` (next guest theme) would have killed
nothing and then started a fresh Waybar, leaving two bars on screen: the
Waybar strip over the shell's islands and a second reserved work area.

## Root cause

`privatestack-guest-theme` refreshed the running desktop by always running
`pkill -x waybar` followed by `waybar`. That was right while Waybar was the
only bar. It assumed the bar it restarts is the bar the session runs.

## Fix

The controller restarts Waybar only when `pgrep -x waybar` finds one running,
which is the plain-bar session or the shell's own Waybar fallback. The
Workspace Shell does not need a restart: the controller now also writes
`~/.config/privatestack-guest/palette.json`, and the shell watches that file
and recolours itself.

## Regression proof

- `tests/guest_workspace_shell_contract.py` requires the `pgrep` guard and the
  palette file in the controller.
- `tests/guest_presentation_contract.py` requires exactly one bar at session
  start, for both `guest_desktop_hyprland_shell` values, and rejects a
  template that starts both.
