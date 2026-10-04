# Looking Glass showed nothing after a night: the guest had locked itself

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the guest presentation contract.
The physical recheck on `dev-01` is pending.

## Symptom

After eight idle hours, `hyperlabctl open looking-glass dev-01` connected,
reported the guest and `Starting session`, then stayed on the Looking Glass
splash screen. The host bar still named the GPU owner `dev-01`.

## Diagnosis

A read-only check inside the guest showed the domain running, the Hyprland
session up, the headless output on (`dpmsStatus: 1`), the Linux sender
process alive since boot, and `hyprlock` running.

## Root cause

`hypridle` locked the guest session after ten idle minutes. Hyprland refuses
screen capture while the session is locked, so the PipeWire capture behind
the sender had no frames to give. The guest was fine; it was simply locked
where no one could see it.

The same configuration also turned the display off with
`hyprctl dispatch dpms off`, the classic syntax that the guest's Lua
configuration no longer accepts, so that listener never worked.

## Fix

A guest with the headless output, the Looking Glass configuration, does not
start `hypridle`: the host owns the lock, as it owns the frame around the
window. A guest with a real display keeps the idle lock. The display power
listener is removed: a virtual display has no panel to save. `ALT+L` still
locks on request.

## Regression proof

`tests/guest_presentation_contract.py` requires `hypridle` to start only
outside the headless policy, exactly once, and no `hyprctl dispatch` in the
idle configuration.
