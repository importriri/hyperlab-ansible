# Product relief did not match the requested wallpaper material

Author: [importriri](https://github.com/importriri).

Status: product materials corrected in source; pool resolution deferred.
Software verification only; physical acceptance remains open.

## Symptom and cause

The operator rejected the installed product wallpaper at 1920×1080 on
2026-11-03. Geometry B alone did not carry the material of the preferred
HOST images: its renderer painted dark relief outlines and a flat pale
disc, while v3 already rendered stone-grained arcs and a textured sphere.

The pool images are 1672×941, so copying or enlarging them into the product
family would retain the softness the operator wanted removed. Native
product dimensions alone do not prove that the detail was rendered there.

## Correction

Both wallpaper entry points use the v3 shader and capture from
`tools/wallpaper/pool_material.py`. Product and quieter lock render every
pixel directly at 3840×2160, 1920×1080, 2560×1600 and 3440×1440. The sphere
is neutral without a trust or palette input. The old reference's typography,
reticles and construction lines are omitted under the art-direction rules.
[ADR 0058](../docs/adr/0058-product-wallpaper-pool-materials.md) records the
proposed material change.

## Why the pool stays at 1672×941

`load_pool` in `tools/trust_wallpaper_engine.py` requires the complete
geometry mapping to equal width 1672, height 941 and aspect ratio
`1672:941`. A 3840×2160 manifest is refused with
`wallpaper geometry contract changed`; changing only the PNGs is refused
by the per-image dimensions and hashes. The pool cannot accept a second
size under that contract. Its renderer, images and manifest therefore
retain the original dimensions and pixels. Supporting another size needs
a separate reviewed engine change with equivalent manifest/image checks;
this change does not broaden the accepted geometry.

## Regression proof

The shared-material contract failed before extraction. Contracts now
execute native scene dimensions, material masks and capture samples,
regenerate all eight product outputs and compare every decoded RGB pixel.
Hashes, every negative-space pixel, fully covered neutral core pixels and
quieter lock parameters are checked. The existing generated pool contract
still compares all twelve images exactly. Source, tint, geometry, native
size and lock mutations are catalogued in `tests/MUTATIONS.md`.

## Native PNGs exceeded the file budget

The first native material regeneration produced 4K product and lock files
of 6,930,410 and 6,929,379 bytes, exceeding the 5 MiB repository asset limit.
Qt saved opaque RGBA with adaptive scanline filters; that encoding compressed
this fine grain poorly. Raising the compression level alone still exceeded
the limit. Reducing the grain or output dimensions would change the artwork.

The product entry point now captures the shared Qt scene into a temporary
eight-bit RGB PPM, refuses an unexpected header or payload length, and writes
an RGB PNG with unfiltered scanlines and zlib level 9. This requires only the
existing Qt renderer and Python standard library. There is no quantisation
or resampling. The pool keeps its existing PNG capture and unchanged bytes.

The identity contract checks the 5 MiB ceiling for both committed files and
every fresh native render. Exact decoded-pixel comparison remains mandatory,
independent of the new file hashes. The old 4K files fail the new size stage;
a valid oversized PNG mutation is rejected even with its pixels unchanged.
