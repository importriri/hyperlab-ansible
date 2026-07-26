# ADR 0001 - Image store layout

## Context

Nothing in the three repositories touches `/var/lib/libvirt`. The VM
factory needs a place to put base images, per-VM disks, NVRAM, TPM state
and cloud-init seeds, and it needs one before any of them exist - a
layout decided after the first image lands is a migration, not a layout.

## Decision

One root, one variable:

```
hyperlab_root: /var/lib/libvirt/images/hyperlab
```

```
{hyperlab_root}/
├── bases/{windows,linux}/   immutable, 0444, never booted directly
├── disposable/<vm>/         overlay qcow2, backing file in bases/
├── permanent/<vm>/          independent clone, no backing file
├── cloud-init/<vm>/         NoCloud seed ISOs
├── nvram/<vm>/              per-VM UEFI variables
├── tpm/<vm>/                per-VM swtpm state
├── snapshots/, exports/, cache/, state/
```

The tree is created by `kvm_host`, not by `guest`. `kvm_host` is the
brick that owns libvirt; the store is part of owning libvirt, and a host
with the store but no VMs is a coherent state. `guest` fills the tree, it
does not invent it.

## Consequences

- Relocating the store is one variable, including onto the encrypted
  second disk `arch-bootstrap` can already create.
- `bases/` at 0444 makes "a VM booted its own base" a permission error
  instead of a silent corruption discovered a week later.
- Per-VM subdirectories under `nvram/` and `tpm/` make the "never clone
  TPM state" rule structural rather than a instruction in a document.
- `state/` is the only writable metadata location, which gives storage
  audit and garbage collection exactly one place to read.
