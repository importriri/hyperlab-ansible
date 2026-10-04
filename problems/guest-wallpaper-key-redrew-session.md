# `ALT+SHIFT+W` took seconds to change a guest's wallpaper

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the Workspace Shell contract.
The physical recheck on `dev-01` is pending.

## Symptom

On `dev-01`, reached through Looking Glass, `ALT+SHIFT+W` changed the
wallpaper only after a visible pause and a slow animation.

## Measurement

Measured on `dev-01` over SSH, without privilege, with every subprocess of
`privatestack-guest-theme wallpaper-next` timed:

| Step | Time |
| --- | --- |
| Python start and wallpaper choice | 0.03 s |
| `hyprctl reload` (returns; `configreloaded` follows in 9 ms) | 0.01 s |
| `pgrep waybar`, `makoctl reload`, `kitty @ set-colors` | 0.05 s |
| `awww query`, `awww img` (returns) | 0.03–0.05 s |
| whole command | 0.09–0.11 s |

The command itself was never slow. What the eye waits for comes after it
returns: the `grow` transition of 1.1 s at awww's default 30 frames per
second, shown through Looking Glass, and a full compositor reload that
replays the configuration for a change that touches no colour.

## Root cause

The wallpaper key used the same refresh as a theme change. A theme change
must reload Hyprland, restart Waybar where it runs, reload mako and recolour
kitty; a new wallpaper needs none of that. It also inherited the theme's long
transition.

## Fix

`apply_theme` renders the palette files a second time with the previous
wallpapers. A file whose text is the same either way carries colours or
style; a file that differs only names the wallpaper. When the key rotates
the wallpaper and no styling file changed, only `awww img` runs, with a
0.4 s fade at 60 frames per second. The lock screen still follows the new
image through `hyprlock-theme.conf`, read when hyprlock starts. A theme
change, or a rotation that also had to rewrite colours, keeps the full
refresh and its transition.

The time from the key press to the first changed frame through Looking
Glass cannot be measured without pressing the key on the console; that is
the physical recheck.

## Regression proof

`tests/guest_workspace_shell_contract.py` drives the real controller with
fake programs: a rotation must change the desktop and lock wallpapers, call
nothing but `awww`, and use the short fade of at most 0.5 s; a theme change
must still reload Hyprland and mako and keep its own transition. The check
fails against the previous controller.
