# ADR 0056 - Draw the product symbol with geometry B

Status: Accepted (operator decision, 2026-11-01).

## Context

The operator chose geometry B on 2026-11-01. The existing product symbol
used two stroked outer arcs with rounded ends and openings at 3 and 9
o'clock, a thin containment ring and a small central dot. The operator's
visual pack already uses filled left and right arcs with vertical cuts and
openings at 12 and 6 o'clock. The rail and identity wallpaper must share
that symbol, including its legible 16-pixel form.

## Decision

Use geometry B everywhere the product draws its symbol. With outer radius
R, the filled outer boundary is the annulus from 0.685 R to R after removing
the vertical band |x| < 0.41 R. The remaining left and right shapes have
straight vertical ends, with neither round caps nor radial cuts. The closed
containment ring has radius 0.555 R and stroke 0.057 R, at least one pixel.
The central disc has radius 0.413 R.

In `IsolationGlyph.qml`, R = 0.46 times `size`. Below 33 units, omit the ring
and enlarge the core to 0.435 R. Keep `size`, `stroke`, `core` and
`strokeScale`: arcs and ring use `stroke`, the disc uses `core` (which
continues to follow `stroke` by default). At the default scale these are
the exact proportions. `strokeScale` scales the filled boundary thickness
inward and the ring stroke, retaining the ring's one-pixel minimum; the
outer radius and vertical cut positions stay fixed. Clamp the inner radius
at the cut for extreme thicknesses so the coordinates remain finite.

The wallpaper retains its current radius, placement, light, graphite ground,
variants and four output sizes. Apply the engraved recess and offset lit lip
to filled arc paths, and retain the existing ring and core relief treatment
with their new proportions. Wallpaper-sized marks always use the full form.
The same named numerical constants live in both drawing implementations;
an executable contract checks each against this table and inspects the
actual paths and paint calls, preventing independent drift.

## Consequences

The three shell call sites keep their existing interface. All eight
wallpaper outputs are regenerated and their SHA-256 digests updated together.
`tests/product_symbol_geometry_contract.py` checks the QtQuick Shapes paths,
colours, width scaling, small-form boundary and renderer commands;
`tests/host_identity_asset_contract.py` retains the asset and ownership checks.

The mark remains monochrome and has no state, provenance or trust authority.
The wallpaper rules, lock privacy and Contained Planes rollback remain in
force. Acceptance of this geometry is the operator's design decision;
software checks do not establish physical legibility, clipping or compositor
behaviour. Nitro acceptance under both compositors and Predator replay remain
separate hardware gates.
