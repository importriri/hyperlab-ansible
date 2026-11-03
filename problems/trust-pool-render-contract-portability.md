# The trust pool contract checked encoding and undersampled the artwork

Author: [importriri](https://github.com/importriri).

Status: corrected in the generated contract; software verification only.

## Symptoms

Recompressing a PNG without changing a pixel, and updating its manifest hash,
failed with `generated output drift`. A new Qt or PNG compression library
could therefore reject unchanged artwork on CI. The committed pool's byte
reference is Arch's Qt 6.11.2; the workflow uses Ubuntu 26.04 packages.

Conversely, a bright corner mark implemented entirely with arithmetic passed
the complete contract after regeneration. Its pixels lay outside the handful
of material samples and its source used no forbidden drawing primitive.
Changing only the product renderer's geometry B cut ratio also passed the
trust pool contract: the pool and its test duplicated the same constants.

## Causes and correction

PNG compression and metadata bytes are not image pixels. Decode every
scanline with its PNG filter, normalize opaque RGB/RGBA captures to RGB, and
compare every pixel exactly. Retain SHA-256 checks on each committed PNG and
its manifest, and separately on each temporary output and its manifest.
Compare parsed manifest policy independently of those encoding-specific
hashes. The generator's `--print-hashes` must still match its actual files.
A changed pixel has no tolerance; transparent captures are refused.

Check every pixel outside geometry B's surfaces, including the sphere/ring
and ring/arc gaps and the vertical cuts, against the documented ground range
plus grain and rounding. Leave one pixel around each material edge for
antialiasing. A regenerated mark must fail even if renderer and committed
images now agree. Material probes and source restrictions remain in force.

Read the product renderer's numerical QML geometry properties and require
the pool's properties and executed material values to agree. The existing
product geometry contract continues to pin that source to ADR 0056. There is
no third table of geometry values in the pool contract.

## Regression proof

The original full contract rejected compression-only drift, but accepted both
the regenerated corner mark and the product-only cut-ratio change. The
mutations and restored checks are catalogued in `tests/MUTATIONS.md`.
The corrected contract accepts a differently compressed opaque RGB encoding,
rejects a one-pixel difference even with an updated SHA-256, rejects a mark
after regeneration, and rejects product-only geometry drift. Additional
negative cases cover both circular gaps, a vertical cut, transparency and a
PNG whose manifest hash was not updated. Malformed PNG chunks and a
rotation-only manifest change also fail; their restored checks pass.
[ADR 0057](../docs/adr/0057-trust-pool-pixel-verification.md) records the
proposed correction of the cross-runtime byte assertion.
