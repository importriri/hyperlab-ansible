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
