# Guest Waybar visible over a fullscreen-looking benchmark

Author: [importriri](https://github.com/importriri).

Status: corrected, software-verified, deployed to the Nitro guest, and physically accepted. Guest ALT+F enters compositor true fullscreen, covers Waybar, and returns with Waybar restored.

## Physical symptom and reproduction

On Nitro, `arch-dev-vfio` viewed through Looking Glass shows guest Waybar above
Unigine Valley/Heaven when the benchmark appears fullscreen. The user reports
this after the rebuilt Linux sender restored correct SDR colours, and remembers
a previous solution. The exact fullscreen entry route was not captured with the
report. Reproduce separately with the application's own fullscreen setting and
with guest `ALT+F`; looking fullscreen is not proof of compositor fullscreen.

Affected path: guest Hyprland on `HEADLESS-0` -> PipeWire -> Linux Looking Glass
sender -> kvmfr -> host client. Guest Waybar is launched by the guest Hyprland
startup callback and restarted by the guest theme controller. Host Quickshell is
a different surface and is not changed here.

## Historical reconstruction

- `21f47aa` introduced guest Waybar on `layer: top`, and the guest `main_mod+F`
  binding executed `hyprctl dispatch fullscreen 1`. That dispatcher argument
  selects maximization, retaining the work area and bar. It was not a true
  fullscreen fix.
- `a822713` moved the guest Lua file into a Jinja template for the managed
  headless output without changing that fullscreen action or tearing policy.
- `ba8da59` adjusted appearance/login, preserving the action.
- `0a39da5` introduced the **host** native
  `hl.dsp.window.fullscreen({action="toggle", mode="fullscreen"})` action.
  That provides the reviewed true-fullscreen mechanism reused by this correction;
  it does not prove a prior guest repair.
- `24e2b43` changed guest SUPER to ALT, preserving `fullscreen 1`.
- Despite its title, `28c8688` did not change the guest fullscreen action.
  Host shell changes in `a056b6b`/`53489ee` do not rewrite guest Waybar policy.

`git log --all -S/-G` and blame found no committed guest top-to-overlay drift or
later removal of a true-fullscreen shortcut. The remembered physical repair
may have been local; it is not reconstructed as an invented commit here.

## Proven defect and boundary

The managed guest shortcut requests maximization, not full display coverage.
Hyprland distinguishes these modes in its [dispatcher contract](https://wiki.hypr.land/Configuring/Basics/Dispatchers/);
the [legacy dispatcher documentation](https://wiki.hypr.land/0.54.0/Configuring/Dispatchers/)
also distinguishes `fullscreen 1` from true fullscreen. This explains a retained
bar when that shortcut is used. It does **not** establish why a benchmark that
already has genuine internal fullscreen would show a bar: that case still needs
runtime state, layer ownership, and a physical replay.

## Implemented correction and rejected alternatives

Use the existing native Lua fullscreen action for guest `ALT+F`, with explicit
`mode="fullscreen"` and `action="toggle"`. Keep the normal guest top-layer bar,
startup, theme restart, and exclusive work area unchanged. Tiled and maximized
windows must retain the bar; true fullscreen must cover it.

Do not kill Waybar, globally hide it, move it to overlay, change host Quickshell,
or add F11/Ctrl+F/Ctrl+Alt+F11 routes. Host SUPER and Looking Glass RIGHTCTRL stay
in their own namespaces. The current sender SDR/HDR patch is untouched.

## Deterministic regression coverage

`python tests/guest_presentation_contract.py` renders ordinary and headless
configurations and executes them with Lua, recording API calls without invoking
a compositor. It failed against the old exec binding and passes with native
fullscreen. Mutation cases reject the old action, maximization, overlay/nonexclusive
Waybar, removal of Waybar startup, and enabled or omitted tearing policy.
The separate namespace and Looking Glass contracts protect adjacent boundaries.
These tests prove emitted configuration, not actual layer rendering.

## Physical acceptance — PASS

The corrected guest configuration was rendered from the current source and
deployed narrowly to `arch-dev-vfio`. Runtime evidence showed the managed guest
on `HEADLESS-0` at 1920x1080@144, `general.allow_tearing=false`, no Hyprland
configuration errors, and the ALT binding emitted by the reviewed native Lua
fullscreen action.

Physical acceptance on Nitro proved both directions of the transition:

1. `ALT+F` enters true compositor fullscreen and the guest Waybar is no longer
   visible over the application.
2. `ALT+F` returns from fullscreen and the guest Waybar returns normally.
3. The rejected F11, Ctrl+F and Ctrl+Alt+F11 guest routes are not required.
4. Host SUPER and Looking Glass RIGHTCTRL retain their separate namespaces.

This closes the reported Waybar/fullscreen defect. The correction changes the
guest fullscreen action only; it does not hide or kill Waybar globally and
does not alter the Looking Glass sender, colour path, tearing policy, host
Quickshell, or trust/provenance authority.

Classification:

`C9_A_WAYBAR_FULLSCREEN=PHYSICAL_PASS`
