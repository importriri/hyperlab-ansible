# Theme variants changed the meaning of trust-domain colors

Author: [importriri](https://github.com/importriri).

## Symptom

Switching the desktop palette changed some `clean`, `dev`, `services`, `dirty`
or `lab` colors even though the Control Center and domain icons treated those
colors as stable security semantics.

The same workload could therefore acquire a different trust color when only the
visual theme changed.

## What was wrong

`tools/palette/palette.yml` stored domain tokens inside every theme variant.
That made security identity look like an ordinary accent choice.

The Control Center had already drifted in the other direction and carried
literal domain colors in its CSS. Neither side was an authoritative semantic
source.

## Fix

Move the five domain tokens to one top-level semantic palette. Theme variants
contain appearance tokens only.

The renderer merges the immutable domain palette into every generated fragment,
and its audit refuses any variant that tries to override those domain names.

The Control Center consumes `@hl_dom_*` tokens instead of repeating hexadecimal
domain colors in domain-specific selectors.

Focused Sway borders remain theme-accented. This change stabilizes trust
identity; it does not turn Sway's global unfocused color class into a per-window
trust decoration.

## Regression proof

Palette audit checks one canonical five-domain set and verifies its separation
independently from theme variants. Every generated Sway fragment receives the
same five semantic values.

The Control Center domain-specific CSS no longer owns a second hexadecimal
mapping. Theme changes can alter accents and surfaces without changing the
meaning of `clean`, `dev`, `services`, `dirty` or `lab`.
