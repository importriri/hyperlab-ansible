# The pinned Looking Glass Linux sender failed under GCC 16

Author: [importriri](https://github.com/importriri).

## Symptom

The pinned Looking Glass Linux `host/` build stopped in the PipeWire/portal code
when compiled with GCC 16. The project keeps warnings as errors, so weakening
compiler flags would have hidden the incompatibility rather than fixing it.

## What was wrong

The pinned upstream source used a GLib auto-pointer pattern that GCC 16 rejected
in this build. The failure was specific to the source/toolchain combination; the
PipeWire design itself was not the problem.

## Fix

Keep the upstream commit pinned and apply one small, hash-verified compatibility
patch only during the build. Preserve the upstream warning policy and revert the
source tree after installation.

## Regression proof

The patched build reached 100 percent with PipeWire enabled and XCB disabled.
The resulting sender later produced real 1920×1080 frames through the portal and
kvmfr path.
