# Control Center theme selection re-entered its own GApplication

Author: [importriri](https://github.com/importriri).

Status: proved on Acer Nitro AN515-55.

## Symptom

Green, Violet, Blue and Red buttons changed the desktop correctly, but the
Control Center became temporarily unresponsive. After eight seconds it reported
that the theme controller had not responded, and the resulting modal error had
to be dismissed before the Control Center could close normally.

The hardware broker remained healthy and keyboard RGB did not change.

## Root cause

The Control Center used a synchronous `privatestack-theme set THEME` call so a
real helper failure could be reported to the user.

The theme helper then called `privatestack-hyperlab-domains --reload-theme` at
the end of the same transaction. With a resident GApplication this created a
re-entrant wait: the GTK callback waited for the helper while the helper waited
for the same application event loop to process the reload request.

The theme files and wallpaper had already landed, which is why the visible
theme changed even though the parent call eventually timed out.

## Fix

Control Center-owned theme transactions mark themselves so the helper skips
only the callback into the Control Center. After the helper exits, the resident
application reloads every cached GTK surface directly.

External theme changes still use the original reload route. The marker does not
change fan, battery or RGB privilege boundaries.

## Regression gate

Closure requires immediate Green/Violet changes with no timeout dialog, normal
Escape/pointer dismissal, correct `privatestack-theme status`, unchanged Nitro
broker/RGB state, and a successful external theme change that still refreshes
the resident UI.

## Runtime validation

The candidate fix was validated on the Acer Nitro AN515-55.

Theme selection from the Nitro Control Board completed without the previous
eight-second timeout or modal error. Green and Violet were selected from the
board and `privatestack-theme status` followed the requested value.

The Nitro broker remained healthy throughout the test. Fan state stayed at
`100,100`, the battery limiter stayed enabled and four-zone RGB readback stayed
`ff00ff,00ff00,0000ff,ff00ff,100`.

This closes the re-entrant GApplication failure. The later surface-lifetime
regression is documented separately because its root cause was the Sway reload,
not the synchronous helper call.
