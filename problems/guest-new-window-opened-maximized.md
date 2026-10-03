# A second terminal hid the first: it opened maximized

Author: [importriri](https://github.com/importriri).

Status: corrected in source and pinned by the guest presentation contract.
The physical recheck on `arch-dev-vfio` is pending.

## Symptom

With one kitty open, `ALT+Return` seemed to do nothing: the screen still showed
a single terminal across the whole work area. Opening a third terminal and
closing it again left two terminals side by side.

## Evidence

`hyprctl clients` on the guest, taken in that state:

```text
Window 55ddbb5235f0  at: 18,78  size: 932,908   fullscreen: 0  visible: 0
Window 55ddbb600300  at: 18,78  size: 1884,908  fullscreen: 1  fullscreenClient: 1
workspace 11: windows: 2, hasfullscreen: 1
```

Both windows existed and were tiled; the new one was maximized (fullscreen
mode 1) at the client's own request and covered the first.

## Root cause

Applications may ask the compositor to open maximized, and kitty does on this
guest. Hyprland's own default configuration ignores those requests with a
window rule; the guest's managed Lua configuration replaced the default and
did not carry that rule, so the request was honoured.

## Fix

A window rule for every class suppresses `maximize` events. Tiling decides
window sizes; `ALT+F` still makes a window fullscreen on purpose.

## Regression proof

`tests/guest_presentation_contract.py` executes the rendered configuration and
requires the rule; removing it is a rejected regression.
