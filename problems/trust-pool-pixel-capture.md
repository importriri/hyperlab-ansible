# A trust pool pixel buffer captured as an empty image

Author: [importriri](https://github.com/importriri).

Status: corrected in source; software verification covers capture pixels.
Physical trust-pool acceptance is pending.

## Symptom

During development of the generated trust pool, the Qt Canvas material
function returned the expected grey arcs and coloured core, but its PNG
capture was empty. A successful save and a reproducible hash alone did not
prove that the material reached the image.

## Root cause

With Qt 6.11.2's software Canvas, the three-argument
`putImageData(pixels, 0, 0)` call in this scene did not capture the expected
pixel rectangle. Supplying the explicit dirty rectangle reproduced the
material correctly. No claim is made about other Qt releases or backends.

## Fix

The renderer supplies all seven arguments, including the full canvas width
and height. The scene captures once after drawing. Its pixel loop uses a
local JavaScript material closure so that repeated QML property lookups do
not dominate generation time.

## Regression proof

`tests/trust_pool_v3_generated_contract.py` reads actual PNG pixels and
compares them against the material sampled at those pixel centres, for HOST
and DEV in both variants. It also regenerates all twelve files and compares
them byte-for-byte. Removing the explicit dirty rectangle fails the capture
check after regeneration; a blank image cannot pass merely because the
underlying material function is correct.
