# A second VFIO Machine was refused while the first was shut off

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the guest contract. The physical
creation of `dev-01` on Nitro is pending.

## Symptom

Creating `dev-01`, the first Machine from the `workstation-dev` Template,
stopped before anything was written:

```text
VFIO registry refused: VFIO devices ['0000:01:00.0', '0000:01:00.1'] are
already assigned to libvirt domain arch-dev-vfio
```

`arch-dev-vfio` was shut off.

## Root cause

`tools/vfio_registry.py` treated a PCI function named in any defined domain
as owned, in the define check as well as the start check. That made the GPU
belong to whichever VFIO domain was defined first, for as long as it existed,
and left room for exactly one VFIO workstation on the host.

## Fix

[ADR 0016](../docs/adr/0016-gpu-shared-definition-running-lease.md): naming
the GPU is not owning it.

- A managed VFIO domain may name the same functions as other managed VFIO
  domains. A domain HyperLab does not manage still blocks.
- At start, under the GPU lock, a running domain on the same functions, the
  same Looking Glass device or the fixed SPICE port blocks.

The contamination ladder in the qemu hook is unchanged.

## Regression proof

`tests/guest_contract.py` defines a second managed VFIO domain beside a
current-namespace and a legacy-namespace one, refuses an unmanaged or
standard domain on the same functions, accepts a start while the other is
shut off, and refuses it while the other runs or holds `/dev/kvmfr0`.
