# Nitro Control Panel

Author: [importriri](https://github.com/importriri).

The Nitro page is part of the resident HyperLab Control Center. It is a
normal-user frontend for `/usr/local/bin/hyperlab-nitro-control`; it does not
write sysfs, call `sudo`, or receive a generic privileged command primitive.

## V1 scope

The first hardware-facing surface is deliberately small:

- backend/model status;
- CPU and GPU fan percentages when advertised;
- battery limiter when advertised;
- four static keyboard zones and brightness when advertised.

Each write requires an explicit Apply action. The page rebuilds from broker
readback after a successful request rather than assuming that the requested
value reached hardware.

Controls are capability-driven. A missing capability is not rendered as a
disabled promise.

On the validated AN515-55 this means fan, battery limiter and four-zone RGB are
available. Firmware effects are not exposed, and no backlight-timeout control is
invented for hardware whose active driver has no such ABI.

## Ownership

The GUI changes runtime state only. Ansible continues to own boot defaults and
the persistent `nitro-sense-apply.service` policy.

A future persistent GUI action needs a separate reviewed ownership contract.

## Later dynamic modes

Theme Sync, Trust, Ambient, Temperature/Load and Audio Reactive are intentionally
outside V1. They can be implemented later as normal-user frame providers using
the existing broker rate limit without widening the privileged protocol.

## Control Board V2

The visible `Nitro` rail item opens one integrated Nitro Control Board rather
than a separate hardware utility.

The board includes direct Green, Violet, Blue and Red desktop theme selection
through the existing normal-user `privatestack-theme` transaction. Theme
selection changes presentation only. The semantic clean/dev/services/dirty/lab
trust colors remain fixed across every appearance theme.

Fan, battery limiter and four-zone keyboard RGB retain the existing narrow
Nitro broker boundary. The GUI still receives no sysfs path and no generic
privileged command primitive.

Theme Sync, Trust Sync, ambient color, temperature/load and audio-reactive RGB
remain outside this revision. They require separate runtime-policy and hardware
validation before becoming visible controls.

## Re-entrant theme reload boundary

Theme selection from the Nitro Control Board is synchronous so the UI can
report a real helper failure. The theme helper historically ended every theme
transaction by launching `privatestack-hyperlab-domains --reload-theme`.

That route is correct when the helper is called from Sway, Waybar or a shell.
It is not correct when the caller is already the resident Control Center:
the GTK callback waits for the helper while the helper launches a second
GApplication command that waits for the same callback to return.

Control Center theme calls therefore set a narrow environment marker that
suppresses only the helper's Control Center reload. After the helper transaction
returns, the resident application reloads all cached GTK surfaces itself.
Waybar signalling, wallpaper updates, Sway reload and ordinary external theme
calls keep their existing behavior.

## Visible-surface lifetime during theme selection

A theme button inside the Nitro Control Board must not dismiss the Control
Center. The palette, wallpaper, Waybar and resident GTK provider are updated
while the current surface remains mapped.

Sway itself cannot be reloaded synchronously from that callback. The Sway
configuration deliberately starts the resident Control Center supervisor with
`exec_always`; a reload therefore replaces the resident process and would hide
the surface even though the user never clicked outside it.

Control Center-owned theme transactions consequently defer only the Sway reload.
The window records one pending palette reload, keeps accepting ordinary controls
and further theme choices, then launches the final Sway reload asynchronously
after the surface is intentionally hidden. Repeated theme choices coalesce into
one final reload using the last selected palette.

Theme changes started outside the Control Center retain the normal immediate
Sway reload behavior.

## Nitro runtime validation

The integrated Control Board has been exercised on the Acer Nitro AN515-55
after deployment through `host-desktop-sway.yml`.

Green, Violet, Blue and Red desktop themes can be selected from the board while
the same overlay remains mapped and responsive. Theme writes stay in the
normal-user desktop helper; fan, battery and keyboard RGB remain behind the
Nitro broker.

The board deliberately keeps Sway reload deferred while it is visible. Several
theme selections can therefore occur inside one interaction. The final reload
is released only after intentional dismissal, at which point the warm resident
manager can be replaced without interrupting the active control session.

The runtime campaign also verified that desktop theme changes do not mutate
Nitro hardware state. During the test, fan state remained `100,100`, the
battery limiter remained enabled and RGB readback remained
`ff00ff,00ff00,0000ff,ff00ff,100`.

The second real desktop-role apply after the runtime campaign completed with
`changed=0` and `failed=0`.
