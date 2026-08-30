# Sway reload dismissed the Control Center during theme selection

Author: [importriri](https://github.com/importriri).

Status: proved on Acer Nitro AN515-55.

## Symptom

Green, Violet, Blue and Red changed the desktop correctly and no longer timed
out, but the visible Nitro Control Board disappeared immediately after a theme
selection.

The backdrop had not been clicked and the Nitro hardware backend remained
healthy.

## Root cause

The re-entrant GApplication callback had already been removed, but `set_theme`
still ended with `swaymsg reload`.

The managed Sway configuration starts the resident Control Center supervisor
through `exec_always`. Reloading Sway therefore runs that supervisor again. Its
replacement contract intentionally retires the previous resident process before
starting a warm replacement, so the currently visible Layer Shell surface is
lost as a side effect of an appearance change.

This was independent from the single-surface backdrop. The backdrop catcher
already dismisses only when the pointer lands outside the real panel.

## Fix

A Control Center-owned theme call now marks the Sway reload as deferred.
Wallpaper, generated palette files, Waybar signalling and the resident GTK
provider still update immediately.

The visible window records one pending Sway palette reload. `close_surface`
first hides the surface, then launches `swaymsg -q reload` asynchronously. This
avoids re-entering the GTK callback while still allowing the resident session
supervisor to replace the manager after dismissal.

Several theme changes while the board is open coalesce into one reload. External
theme commands keep their immediate Sway reload behavior.

## Regression gate

On the Nitro host, open the Nitro Control Board and select at least three
different themes without leaving the panel. The same surface must remain
visible and usable after every selection.

Then dismiss it through the backdrop. The final Sway palette must remain active
and the warm resident manager must still reopen normally. Escape and the
explicit close control retain their existing dismissal behavior.

The test also requires a second real desktop-role apply with `changed=0`.

## Runtime validation

The lifetime fix was validated on the Acer Nitro AN515-55.

The Control Board stayed mapped and usable while several desktop themes were
selected from inside the same surface. It no longer disappeared as a side
effect of an internal theme change.

After an intentional backdrop dismissal, the deferred Sway reload ran and the
warm resident Control Center was replaced successfully. The final desktop theme
remained `violet`, and reopening the Nitro section succeeded normally.

Nitro hardware state was unchanged by the theme sequence: fan state remained
`100,100`, the battery limiter remained enabled and four-zone RGB readback
remained `ff00ff,00ff00,0000ff,ff00ff,100`.

A second real `host-desktop-sway.yml` apply completed with `changed=0` and
`failed=0`, proving role idempotence after the runtime fix.
