# SUPER and the arrow keys did nothing on the host

Reported by the operator on 2026-10-13, seen since the host first ran
Hyprland: SUPER with an arrow key never moved the focus, even with a host
window focused (a terminal, Firefox).

## What happened

- The host configuration bound focus and window moves to H J K L only:
  `roles/host_desktop_hyprland/templates/hyprland.lua.j2`, "Focus parity"
  and "Move parity" (SUPER+H J K L and SUPER+SHIFT+H J K L), since the
  first Lua configuration (0a39da5). No binding used an arrow key.
- The loaded configuration agreed: on Nitro, `hyprctl binds` (Hyprland
  0.56.2) listed 62 bindings, and none on Left, Right, Up or Down. Nothing
  else took the keys first: the host shell registers no global shortcut,
  and the main modifier is SUPER.
- The key sheet (SUPER+F1) listed only H J K L, so it promised nothing
  more; the guest configuration binds its own modifier, ALT, with the
  arrows.

## Fix

SUPER with an arrow focuses in that direction and SUPER+SHIFT with an
arrow moves the window, as H J K L do. The key sheet rows read "H J K L or
arrows".

## Regression proof

`tests/host_key_sheet_contract.py` requires each of H J K L and the four
arrows to be bound to focus in its own direction with SUPER, and to move
with SUPER+SHIFT. Against the previous configuration: `SUPER+left is not
bound to focus left`. With SUPER+right bound to focus left: `SUPER+right is
not bound to focus right`. The sheet-to-bindings parity check covers the
renamed rows in both directions.

## Applying it

The host Hyprland playbook renders the new configuration; Hyprland reloads
it by itself when the file changes.
