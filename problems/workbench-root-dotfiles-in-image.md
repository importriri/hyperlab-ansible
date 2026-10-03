# The first captured image kept root's configuration and caches

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the Workbench contract. The
image already imported was discarded before it was sealed and is captured
again with the fix.

## Symptom

The first successful seal of `arch-dev-vfio` passed the leftover scan. An
independent read-only check of the staged disk found `/root/.cache`,
`/root/.config` and `/root/.npm` still in the image.

## Root cause

Provisioning runs as root, and tools such as npm leave a cache and a
configuration directory in root's home. The seal deleted only root's SSH,
GnuPG and keyring directories, and the scan refused only those and the
shell histories. A configuration directory can hold tokens (`gh`, cloud
CLIs, registries), so it must not travel into every Machine.

## Fix

The seal deletes `/root/.config`, `/root/.cache` and `/root/.npm`, and the
scan refuses an image that still holds any of them.

## Regression proof

`tests/workbench_contract.py` requires the three deletes and refuses a scan
that lists `.config` or `.npm` under `/root`.
