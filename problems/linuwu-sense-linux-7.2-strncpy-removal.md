# Linuwu-Sense build failure on Linux 7.2

## Symptom

After upgrading the Arch host to Linux hardened 7.2, DKMS stopped compiling
the pinned Linuwu-Sense driver. Compilation failed at the three remaining
`strncpy()` calls in `src/linuwu_sense.c`.

The previous kernel remained operational because its Linuwu-Sense module was
already loaded. HyperLab blocked reboot until a module for the new kernel
could be built and verified.

## Failure boundary

This is a Linux kernel API compatibility issue in the pinned out-of-tree
driver. It is not a Nitro firmware, Acer WMI, VFIO, or HyperLab control
failure.

## Repair

HyperLab retains the reviewed upstream source commit. The role-owned source
overlay additionally replaces exactly the three affected bounded copies with
`memcpy()`.

Those paths explicitly terminate their destination buffers after the copy.
The change follows the focused upstream Linux 7.2 compatibility repair
without moving HyperLab to an unreviewed upstream revision.

The source-overlay SHA-256 and deterministic DKMS version are regenerated
together.

## Validation

Acceptance requires:

- exact upstream pin identity;
- clean application of the reviewed combined overlay;
- exact semantic proof of all three replacements;
- isolated compilation against the target hardened kernel;
- successful DKMS installation for the target kernel;
- successful `modinfo` resolution;
- preservation of the currently loaded pre-upgrade module.

The source patch payload is validated semantically and by compilation rather
than being rewritten to satisfy generic patch-file whitespace diagnostics.

## Upstream references

- https://github.com/0x7375646F/Linuwu-Sense/issues/129
- https://github.com/0x7375646F/Linuwu-Sense/pull/130
