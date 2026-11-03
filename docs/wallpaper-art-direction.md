# HyperLab wallpaper — identity and art direction

The shell owns every word on screen. A HyperLab wallpaper is a **ground**,
not a poster: it carries depth and identity without carrying text, badges or
a second logo, and it never encodes trust.

## The product identity: "Isolation Ring"

The default product wallpaper is generated, not sourced. One geometry family
carries the product from the rail to the lock screen:

- two **filled left and right arcs**, the annulus from 0.685 R to R with the
  vertical band |x| < 0.41 R removed; their straight vertical ends leave gaps
  at 12 and 6 o'clock, with no round caps or radial cuts;
- a **containment ring** at radius 0.555 R, stroke 0.057 R (at least 1 px);
- a **contained core**, a filled disc of radius 0.413 R.

This is geometry B, chosen by the operator on 2026-11-01
([ADR 0056](adr/0056-product-symbol-geometry-b.md)), replacing the rounded
stroked boundary split at both sides and its small central dot. R is the
outer radius: 0.46 times the glyph size, or the wallpaper renderer's existing
radius. Below 33 units the glyph omits the ring and uses a 0.435 R core.

`IsolationGlyph.qml` draws that geometry at 18 units in the rail and 24 on
the idle desktop. `tools/wallpaper/render_isolation_ring.py` renders the same
geometry as architectural relief cut into a graphite ground, under a broad
upper-left light.

```sh
python3 tools/wallpaper/render_isolation_ring.py --print-hashes
```

Two variants come from one geometry:

| Variant | Mark diameter | Use |
| --- | --- | --- |
| `isolation-ring` | 46% of the shorter side | the everyday product ground |
| `isolation-ring-lock` | 40%, darker, quieter | the lock surface |

Both are rendered at 3840×2160, 1920×1080, 2560×1600 and 3440×1440. The
master is deployed as `/usr/share/backgrounds/hyperlab/product.png` (the
`product` wallpaper mode) and `/usr/share/backgrounds/hyperlab/lock.png`.

Rendering goes through Qt's software rasteriser, so output is byte-stable for
a given Qt release. `tests/host_identity_asset_contract.py` pins every output
by SHA256: regenerating the family is a reviewed change, never a silent one.
`tests/product_symbol_geometry_contract.py` executes both implementations to
check their numerical constants, vertical cuts and actual drawing paths.
Geometry B is software-verified; its physical acceptance remains open.

"Contained Planes" (`render_contained_planes.py`) stays installed as reviewed
rollback material until the identity family passes physical acceptance on
both compositors.

## Rules any HyperLab wallpaper must keep

- **No typography, no logos, no HUD marks, no reticles.** The rail wordmark
  and the identity treatment are the branding.
- **Dark, low-saturation ground** in the `#07090d`–`#151b23` range, so
  foreground text at `#f0f6fc` and the six provenance colours read at full
  contrast anywhere on it.
- **Depth, not glow.** Soft directional light; no neon, no glowing lines, no
  lens flares, no RGB gaming look.
- **Quiet where the product sits.** The top 37 units belong to the rail, and
  a workspace window can land anywhere.
- **No trust authority.** Colour, filename and appearance are never trust
  authority, in any pool.

## The lock surface

The lock background is a **dedicated static asset**. It is never a blurred
screenshot of the desktop and never a rotated theme wallpaper, because a
locked screen must reveal nothing about the session behind it — no machine
name, no guest content, no provenance.

`privatestack-theme lock-image` returns the product lock asset when it is
installed and keeps the historical rotation offset only as a fallback for an
installation that does not have it.

## The trust pool (unchanged, opt-in)

Trust wallpapers are selected by the host's explicit trust identity through
the reviewed manifest, and remain an opt-in presentation policy that
establishes nothing. The `hyperlab-trust-v2` pool predates this shell and
prints "HYPERLAB", "HOST" and "TRUST" typography into regions the product now
occupies; it stays reviewed material, but it is not the platform identity and
it is not used on the lock surface.

A trust variant may carry **one** quiet tint of its identity in the light —
never a colour field, never a badge.

## Acceptance

- Regenerate, compare hashes, and update
  `tests/host_identity_asset_contract.py` deliberately.
- Check the rail, a workspace window and the lock field over the candidate at
  1920×1080, 2560×1600 and 3440×1440 without the shell adding any scrim.
- Check cropping at 3:2 and portrait before adding a new output size.
