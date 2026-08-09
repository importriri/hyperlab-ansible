# The HyperLab drawer looked detached from Waybar

Author: [importriri](https://github.com/importriri).

## Symptom

The compact drawer opened in the correct corner but looked like a floating
window. There was visible space above it and along the left edge instead of one
continuous surface with Waybar.

## What was wrong

The Layer Shell anchors were already correct: top and left were both enabled.
The gap came from explicit margins. The drawer used 48 pixels from the top and
14 pixels from the left while the managed Waybar height is 37 pixels. Changing
the top margin to 37 still left a 37-pixel gap: with an exclusive zone of zero,
the Layer Shell protocol already moves the drawer below Waybar's positive
exclusive zone before applying the drawer margin.

This was a geometry mismatch, not a Sway placement problem.

The same hardware gate exposed a separate input symptom: after opening the
drawer from a browser, `Escape` still reached the browser until the drawer was
clicked. The drawer requested `ON_DEMAND` keyboard interactivity, for which
Sway uses regular click-to-focus semantics. Mapping the warmed surface therefore
did not transfer keyboard focus.

## Fix

Keep the Layer Shell anchors and set both drawer margins to zero. Keep the
drawer's exclusive zone at zero so Waybar moves it below the reserved bar area
without making the drawer reserve a second work area.

The manager is a resident single-instance GTK application. Sway starts it
through `privatestack-hyperlab-session`, which replaces the resident process on
reload before warming the new one. This prevents a deployed manager update from
continuing to execute the old Python code already loaded in memory.

The middle mouse route is kept separate from this compact surface and opens the
full Control Center explicitly.

Both the compact drawer and full overlay request exclusive keyboard focus while
visible. This makes `Escape` and the drawer keyboard controls work immediately;
hiding either surface releases the request and returns input to the previous
application.

## Regression proof

The desktop structural contract requires the top-left anchors, zero margins,
exclusive focus while visible, the reload-safe warm helper and both compact and
full-manager Waybar routes. A separate Bats lifecycle test replaces an old
resident manager and races four reload helpers to prove that only one warmed
replacement survives. The remaining Nitro gate is a visual check on the real
display after the role converges twice.
