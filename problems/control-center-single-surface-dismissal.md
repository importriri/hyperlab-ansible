# Control Center outside-click dismissal needed one Layer Shell surface

Author: [importriri](https://github.com/importriri).

Status: software-verified; final Nitro runtime acceptance pending.

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

The 2026-09-01 Nitro visual recheck exposed one remaining runtime gap. Pointer
dismissal was correct, but a drawer opened from another application still used
`ON_DEMAND` keyboard interactivity. The window already had a capture-phase
`Escape` handler, but Sway kept keyboard focus on the previous application until
the drawer was clicked, so the handler never received the first key press.

The first repair switched visible surfaces to `EXCLUSIVE` just before mapping
and returned them to `ON_DEMAND` before hiding. That fixed the first open after
the resident process started, but a second open exposed a protocol lifecycle
detail: wlr-layer-shell resets layer-surface state when the surface is unmapped.
An interactivity request made while the cached window was still hidden could
therefore be lost by the following remap.

The resident window now reasserts `EXCLUSIVE` from GTK's `map` signal on every
show. `close_surface()` still returns the surface to `ON_DEMAND` before hiding
it. The transparent catcher remains the pointer dismissal owner, so
click-outside behavior stays independent from keyboard focus and a hidden warm
surface never keeps exclusive keyboard ownership.

A repeated Nitro sequence then isolated a second path-dependent failure:
`Escape -> reopen -> Escape -> reopen -> outside click` all passed, but the next
`reopen -> Escape` failed. The difference was that pointer dismissal unmapped
the layer surface synchronously from the catcher's `clicked` callback.

Pointer dismissal is therefore deferred with `GLib.idle_add()`. The click
dispatch and compositor pointer grab unwind first; the deferred callback then
uses the exact same `close_surface()` path as Escape. This keeps the following
remap and keyboard-focus acquisition independent from the previous pointer
sequence.

The next Nitro run showed the complementary failure: Escape could work for
several cycles but fail once keyboard focus was actually owned by the drawer.
That leaves one common lifecycle rule: a focused layer surface must not unmap
synchronously from either input callback. Escape now schedules the same idle
dismissal callback as the outside-click catcher, so both keyboard and pointer
dispatch fully unwind before `close_surface()` changes layer-shell visibility
and keyboard interactivity.

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
was a runtime ownership problem. Contracts therefore pin the visible
mapped `EXCLUSIVE` / hidden `ON_DEMAND` transition as well as the
capture-phase `Escape` handler; the Nitro display must prove repeated
open → `Escape` → reopen cycles plus outside-click dismissal.

The final focus-specific failure showed that `Gtk.EventControllerKey` was the
wrong ownership boundary: Escape could be lost once a descendant widget owned
keyboard focus. Dismissal is now a `GtkShortcutController` accelerator in
`GLOBAL` scope on the cockpit root. GTK resolves the Escape accelerator across
the window regardless of the focused child, then defers the existing common
input-dismissal callback so Layer Shell visibility changes only after the key
dispatch unwinds.

The instrumented Nitro replay isolated the remaining intermittent failure below
GTK focus handling. Successful Escape cycles logged both the key event and the
global shortcut. On the failing cycle, no Escape key event reached GTK at all,
even though the most recent map transition locally reported Layer Shell
`EXCLUSIVE`; click-outside still reached the common deferred dismissal path.

The drawer therefore no longer reuses one hidden/remapped layer surface.
Dismissal hides and destroys only the compact drawer window, and the resident
`Gtk.Application` creates a fresh drawer/layer-surface on the next route.
Overlay/Control Center windows may remain cached. Window-map iterations use
snapshots because drawer destruction removes the object from the application
cache through the existing `destroy` signal.

The v6.1 Nitro replay proved that a fresh drawer object alone was insufficient.
Deployment and idempotence passed, but after Firefox/ChatGPT owned input focus
during a GitHub-selector interaction, the visible drawer again received no
Escape dismissal. The fresh surface was still created as `ON_DEMAND` and only
promoted to `EXCLUSIVE` from its GTK `map` callback. That first mapped commit
could therefore preserve the browser's keyboard ownership.

Routing now requests `EXCLUSIVE` immediately before `set_visible(True)` and
`present()`, so the first mapped layer-surface commit already carries the
keyboard-ownership request. The map callback remains as a defensive
reassertion, while close still releases capture before hiding and destroying
the drawer.


## 2026-09-10 convergence hardening

The final pre-map repair was mechanically green, but exact-byte adversarial
review found that an idle dismissal could outlive the presentation that queued
it. A close/reopen race could therefore let a stale callback dismiss the new
drawer, and duplicate input callbacks were not coalesced.

Deferred dismissal is now bound to a monotonically increasing visibility
generation. Escape and outside-click share one pending idle source; close,
reopen and destroy invalidate that source, and stale/hidden/destroyed callbacks
are no-ops. An executable headless behavioral contract exercises duplicate
input, close/reopen invalidation and destroyed-callback cases instead of relying
only on source-presence assertions.

This remains **software-verified, runtime-pending** until a fresh Nitro replay
proves repeated browser-focused open → Escape → reopen cycles, outside-click →
reopen → Escape, and no stale callback closing a newly presented drawer.
