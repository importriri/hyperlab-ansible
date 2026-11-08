# ADR 0058 - Render product wallpapers with the v3 pool materials

Status: Proposed.

## Context

On 2026-11-03 the operator rejected the installed geometry B product
wallpaper's flat relief at 1920×1080. The v3 HOST pool image was preferable;
the earlier v2 HOST image supplied the desired reference for stone material
and depth, but its words and screen furniture violate the wallpaper rules.
Both pool generations are only 1672×941 and need enlargement on that panel.

ADR 0056 defines the symbol's geometry and its small shell form. Its
wallpaper relief treatment no longer matches this art direction.

## Decision

Proposed: retain geometry B, the product centre at (52%, 48%), the desktop
46% and lock 40% diameters, the eight filenames and four native sizes.
Replace only the wallpaper materials described in ADR 0056: seeded
near-black ground, light stone-grained grey arcs under upper-left light,
a thinner grey ring and a neutral textured sphere. Lock material strength
is 55% of desktop strength, retaining the quiet near-black ground.

Extract the existing v3 Canvas scene and software capture into
`tools/wallpaper/pool_material.py`. Both renderers call that implementation;
there is no second shader and no bitmap scaling in product generation.
The product sphere uses neutral RGB (147, 147, 147), the current v3 HOST
material's luminance, without reading a trust identity or the palette. The
pool still reads its palette and desaturates HOST. It keeps its exact
pixels, manifest policy and hashes.

Omit construction lines as HUD marks. No words, reticles, crosshairs,
badges or other detached marks are permitted, however faint. The reference
images supply visual direction only; no pixels from them enter the renderer.

Retain the pool at 1672×941: `tools/trust_wallpaper_engine.py` requires that
exact geometry mapping. Adding 3840×2160 would change that contract and is
deferred; see [the resolution constraint](../../problems/product-wallpaper-material-and-resolution.md).

## Consequences and verification

The shell glyph and idle desktop are unchanged. Wallpaper remains
presentation with no trust authority, and lock remains a dedicated static
asset. Contained Planes and v2 remain rollback material.

The product geometry contract keeps every shell path, size-boundary and
stroke-scale check. Obsolete relief paint-command assertions are replaced
by executed shader masks at all four sizes, both variants, vertical cuts,
ring/core gaps, neutral materials and actual capture samples. The identity
asset contract pins all eight hashes, regenerates native outputs, compares
every decoded RGB pixel and checks all negative space and fully covered
core pixels. Source restrictions cover both entry points and the shared
helper. The existing pool pixel, palette-refusal and authority checks remain.
This replaces the superseded material checks without loosening geometry or
wallpaper rules.

Software checks cannot establish physical sharpness or visual acceptance.
Nitro inspection at 1920×1080, both compositors and the lock field, and
Predator replay remain open. This record proposes the implementation of
the operator's direction; it does not claim acceptance of the new images.
