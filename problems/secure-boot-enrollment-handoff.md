# Secure Boot preparation stopped before the firmware acceptance gate

## Symptom

The Nitro host had `sbctl` key material and a signed systemd-boot/kernel path,
but runtime inspection still reported:

- Setup Mode disabled;
- Secure Boot disabled;
- the Acer Platform Key active in firmware.

A historical document described the bootstrap result too strongly as a Secure
Boot host.

## Root cause

Signing the boot artifacts and preparing custom keys are only the software side
of the transition. This Acer still requires an explicit firmware key-management
handoff before the HyperLab hierarchy becomes active and Secure Boot can be
proved at runtime.

The boot chain also contains an Option ROM, so vendor trust cannot be discarded
without an explicit compatibility decision.

## Fix

The acceptance contract now separates PREPARED, ENROLLED, ENABLED,
MODULE TRUST REVIEWED and HARDWARE PROVEN states.

For the first Nitro enrollment, the reviewed preview uses HyperLab PK/KEK/db
plus Microsoft and firmware-builtin Acer `db,KEK`. It does not preserve the
previous Acer PK as the active Platform Key.

A root-only recovery set is required before firmware modification.

## Proof

The final non-writing preview produced the same HyperLab PK list while adding
the firmware-builtin material to KEK and db. `sbctl status` remained unchanged
after the preview.

## Status

OPEN until real firmware enrollment, Secure Boot enablement, two successful
boots and the VFIO/Nitro/Looking Glass hardware gates are proved.
