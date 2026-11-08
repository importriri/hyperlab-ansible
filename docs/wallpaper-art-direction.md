# HyperLab wallpaper — identity and art direction

The shell owns every word on screen. A HyperLab wallpaper is a **ground**,
not a poster: it carries depth and identity without carrying text, badges or
a second logo, and it never establishes trust.

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
geometry with the v3 pool materials: seeded near-black ground, light
stone-grained grey arcs lit from the upper left, a thin grey ring and a
neutral textured sphere. The operator rejected the flat wallpaper relief on
2026-11-03; [ADR 0058](adr/0058-product-wallpaper-pool-materials.md) records
the proposed implementation of that direction. The shell glyph stays as it is.

```sh
python3 tools/wallpaper/render_isolation_ring.py --print-hashes
```

Two variants come from one geometry:

| Variant | Mark diameter | Use |
| --- | --- | --- |
| `isolation-ring` | 46% of the shorter side | the everyday product ground |
| `isolation-ring-lock` | 40%, 55% material strength | the lock surface |

Both are rendered natively at 3840×2160, 1920×1080, 2560×1600 and
3440×1440. No smaller bitmap is scaled into these outputs. The
master is deployed as `/usr/share/backgrounds/hyperlab/product.png` (the
`product` wallpaper mode) and `/usr/share/backgrounds/hyperlab/lock.png`.

Rendering goes through Qt's software rasteriser, so output is byte-stable for
a given Qt release. `tests/host_identity_asset_contract.py` pins every output
by SHA256 and regenerates all eight, comparing every decoded RGB pixel,
negative space and fully covered neutral core pixels. Regenerating the
family is a reviewed change. `tests/product_symbol_geometry_contract.py`
executes shell paths and the shared wallpaper shader to check numerical
constants, vertical cuts, material boundaries, native dimensions and actual
capture samples. Source restrictions cover both entry points and their shared
`tools/wallpaper/pool_material.py`; only native pixel-buffer painting is
allowed. The static product has no trust identity or palette input: its core
uses neutral RGB (147, 147, 147), matching the current v3 HOST material.
Geometry B and these materials are software-verified; physical acceptance
remains open.

"Contained Planes" (`render_contained_planes.py`) stays installed as reviewed
rollback material until the identity family passes physical acceptance on
both compositors.

## Rules any HyperLab wallpaper must keep

- **No typography, no logos, no HUD marks, no reticles.** The rail wordmark
  and the identity treatment are the branding.
- **Dark, low-saturation ground** in the `#07090d`–`#151b23` range, so
  foreground text at `#f0f6fc` and the six provenance colours read at full
  contrast anywhere on it.
- No construction lines, however faint: detached guide lines count as HUD
  marks. Stone grain and sphere texture stay inside the symbol's surfaces.
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

## The trust pool

`trust-pool-v3` is the generated, text-free pool used by Trust Model and the
managed guest profiles. Trust wallpapers are selected by the host's explicit
trust identity through the reviewed manifest. They remain opt-in presentation
that establishes nothing: the shell's host-owned indicators are the only trust
signal. The product and lock backgrounds remain their neutral static family.

```sh
python3 tools/wallpaper/render_trust_pool.py --print-hashes
python3 tests/trust_pool_v3_generated_contract.py
```

The renderer writes twelve 1672×941 PNGs and their SHA-256 manifest. That
size is retained because the trust engine requires the exact geometry mapping;
3840×2160 needs a separate engine-contract change (see the
[resolution constraint](../problems/product-wallpaper-material-and-resolution.md)).
The schema, six identities, two variants each, 30-minute rotation within the current
identity and authority fields are unchanged from v2. Every `trust_color` is
read from `tools/palette/palette.yml` (`domains`), never inferred from artwork.
The palette must be a regular, readable file with unique keys and all six
explicit domain colours; missing or redirected input is refused.

Geometry B stands on a near-black ground with fine, fixed-seed coordinate
grain (amplitude 1.1 per channel). Its filled arcs are light neutral grey with stone grain and upper-left
light; its containment ring is thinner grey. The core is a textured sphere
with a soft identity-coloured rim and dark centre. Colour is clipped to the
sphere, with no bloom or light outside its edge. HOST's sphere is entirely
neutral grey, derived by desaturating its palette colour.

| Variant | Placement | Outer radius | Treatment |
| --- | --- | --- | --- |
| `01` | centre | 33% of image height | visible arc height about 60% |
| `02` | right third (75% of width) | 26% of image height | quieter, at 66% material strength |

There are no words, labels, crosshairs or corner marks. Qt's software Canvas
rasteriser captures the materials, with fixed integer noise seeds and no clock
input. Output is byte-stable for a given Qt release. The generated contract
compares every decoded RGB pixel of all twelve renders, independently checks
committed and temporary PNG hashes against their own manifests, and compares
the parsed manifest policy. Compression and metadata bytes may differ between
Qt releases; image pixels may not. Every pixel outside the symbol or in its
core/ring/arc gaps and vertical cuts must remain within the documented ground
range plus two byte levels for grain and rounding, with a one-pixel margin
around material edges. The contract reads the shared geometry ratios pinned
by the product geometry contract, probes material boundaries, refuses typography and extra drawing
primitives in the helper and both entry points, and checks host and guest
deployment sources. Its source check rejects identity colours
as strings, RGB triples or packed numeric literals in Python and QML, so a
constant matching today's palette cannot silently replace palette input.

`hyperlab-trust-v2` stays unchanged as reviewed rollback material, just as
Contained Planes does for the product family. Its typography predates the
current shell. It is no longer deployed by default. Rolling back means
reviewing the theme/visual asset-set references, guest identity asset source,
host palette copy source and coordinator default together; the planner still
validates v2 under the same authority rules. V2's unresolved asset provenance
is unchanged; see [the licence record](third-party-licences.md).

Software verification does not establish physical acceptance. On Nitro, inspect
one guest per identity at 1920×1080: distinguish the sphere tint, check both
variants for absent text, and confirm only the host shell claims trust. Keep
that hardware gate and Predator replay open.

## Acceptance

- Regenerate, compare hashes, and update
  `tests/host_identity_asset_contract.py` deliberately.
- Check the rail, a workspace window and the lock field over the candidate at
  1920×1080, 2560×1600 and 3440×1440 without the shell adding any scrim.
- Check cropping at 3:2 and portrait before adding a new output size.
