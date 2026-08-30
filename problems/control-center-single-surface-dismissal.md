# Control Center outside-click dismissal needed one Layer Shell surface

Author: [importriri](https://github.com/importriri).

Status: resolved by targeted runtime contracts.

## Symptom

The desktop cockpit needed click-outside dismissal without becoming a normal
Sway window. Earlier implementations split the visible panel and its dismissal
backdrop across separate Layer Shell windows or tried to infer dismissal from
focus changes.

Those approaches made pointer dismissal and keyboard focus depend on compositor
activation behavior rather than on one owned surface.

## What changed

The cockpit now owns one Layer Shell surface covering the usable output. A
`Gtk.Overlay` puts a transparent full-surface button below the real panel:

```text
Layer Shell surface
  Gtk.Overlay
    transparent catcher
    drawer or Control Center panel
```

The catcher closes the active cockpit only when the pointer lands outside the
panel. The real panel is above it, so ordinary interaction never falls through
to the dismissal target.

The separate backdrop window, pointer-only keyboard mode and focus-loss watcher
are retired implementation paths.

## Geometry contract

The single-surface change must not move the visible cockpit.

The compact drawer remains `500x560`, flush left below Waybar. The full Control
Center remains `1180x760`, centered, with its existing top content margin.

The targeted surface, runtime-action, M10, M11, mockup and shell contracts were
used to pin those visible dimensions while removing the second surface.

## Regression rule

A future dismissal change must prove both behaviors at once:

- outside click and one `Escape` close the active cockpit;
- clicking inside the drawer or Control Center never dismisses it accidentally.

Static geometry checks alone are not sufficient because the original failure
was a runtime ownership problem.
