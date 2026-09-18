# Host Hyprland first physical launch acceptance — 2026-09-18

## Status

**PASS — first physical-host Hyprland launch completed with the Sway recovery
session preserved.**

This acceptance covers the first controlled physical launch on the Nitro
validation host. It does not activate Hyprland in Ly and does not remove Sway as
the recovery desktop.

## Pre-launch boundary

Before the first launch:

- the active recovery session was Sway on `tty2`, `seat0`;
- the internal panel was `eDP-1`;
- `eDP-1` was owned by the Intel host GPU through `i915`;
- the NVIDIA GA106M / RTX 3060 display function remained bound to `vfio-pci`;
- the installed Hyprland Lua configuration passed syntax validation;
- Hyprland, hypridle, hyprpaper and hyprpolkitagent were not already running;
- the shared compositor adapter exposed the reviewed `session-exit` primitive,
  implemented for Hyprland through `hyprshutdown`;
- Ly was not modified.

The pre-launch presence of `xdg-desktop-portal-hyprland` was treated as
non-blocking because compositor absence was independently proven: there was no
Hyprland process and no Hyprland instance signature.

## Controlled launch

The first session was started from a separate login session on `tty3` using the
distribution-provided `/usr/bin/start-hyprland`.

The launch environment was deliberately non-nested:

- `XDG_SESSION_TYPE=tty`;
- no inherited `WAYLAND_DISPLAY`;
- no inherited `SWAYSOCK`;
- no inherited `HYPRLAND_INSTANCE_SIGNATURE`;
- no pre-existing Hyprland process.

The existing Sway recovery session remained on `tty2`.

## Runtime evidence

The controlled launch produced:

- Hyprland process successfully observed;
- one resolvable Hyprland instance;
- Hyprland `0.56.2`;
- Wayland socket `wayland-2`;
- physical output `eDP-1`;
- mode `1920x1080`;
- refresh rate approximately `144.003 Hz`;
- scale `1.5`;
- DPMS enabled;
- hardware cursors active.

The compositor used the installed
`~/.config/hypr/hyprland.lua` configuration.

## Exit and recovery

`start-hyprland` returned `0` and reported that Hyprland exited cleanly.

After the controlled session:

- the launch returned to `tty3`;
- the preserved Sway session on `tty2` remained available;
- the shared compositor adapter resolved the active backend as Sway;
- Sway IPC remained functional;
- Ly configuration was not changed.

## Non-blocking observations

The first launch emitted several observations which did not prevent compositor
startup, physical output acquisition, IPC operation or clean shutdown:

- the realtime/process scheduling strategy could not be changed;
- XKB emitted duplicate or unsupported-symbol warnings;
- `wayland-1` was already locked by the preserved Sway session, so the
  controlled Hyprland session used `wayland-2`;
- a Wayland connection error was emitted during teardown after Hyprland had
  already reported a clean exit.

After recovery, the automation bridge reported `WAYLAND_DISPLAY=wayland-2`
while `SWAYSOCK` remained valid, no Hyprland instance signature was present and
the compositor adapter correctly resolved Sway. This does not invalidate the
first physical launch, but it is explicit evidence that shared user-session
environment restoration must be solved before permanent Hyprland activation.

## Verification

Before publication:

- focused Host Hyprland parity, compositor adapter and desktop control contracts
  passed;
- the privileged render suite passed;
- `./verify.sh` completed **ALL GREEN** under a transient user unit with
  `NoNewPrivileges=0`;
- the repository remained clean before this documentation-only publication.

## Acceptance boundary

This milestone proves that the physical host can launch the reviewed Hyprland
configuration on the internal Intel-driven panel and recover to the existing
Sway session without changing Ly or the VFIO ownership boundary.

It does **not** make Hyprland the default login session.

The next milestone is `HOST_HYPRLAND_SESSION_LIFECYCLE`, which must resolve
session-environment ownership/restoration, portal and helper lifecycle,
activation ordering, failure rollback and login-manager integration before any
permanent session switch.
