# ADR 0008 - Standard guest provisioning is a transaction

## Context

M2 creates a verified store, but a VM spans several independently dangerous
objects: a disk, optional NoCloud seed, UEFI NVRAM, optional TPM state, a
libvirt definition and a state record. Treating those as unrelated tasks makes
a failed first run indistinguishable from an operator-owned partial VM.

VFIO has additional ownership and topology requirements and is intentionally
outside this decision.

## Decision

M3 provisions only `device_profile: standard` and refuses VFIO until M4.
Looking Glass, shared folders, USB passthrough and static IP assignment are also
refused rather than silently omitted.

A selected checked-in VM spec is converted into a deterministic plan before any
write. The plan fixes the UUID, locally administered MAC, store paths,
lifecycle and exact deletion set. Before inspecting, writing or deleting those
paths, M3 revalidates the M2 layout manifest plus every store directory it
depends on: each must still be a real canonical directory on the store device.
Creation then holds a per-VM lock and commits one transaction:

1. verify the sealed base's canonical path, immutable permissions, SHA-256,
   qcow2 format, independence and virtual size;
2. reject singleton, UUID and MAC collisions in committed VM state and in both
   live and next-boot libvirt interface configurations;
3. resolve memory against live libvirt commitments;
4. create a qcow2 overlay with an explicit backing format for `disposable`, or
   an independent atomic `qemu-img convert` clone for `permanent`;
5. create a secret-free NoCloud seed only for capable Linux images;
6. render and schema-validate domain XML;
7. define the domain and reconcile autostart;
8. write the state record, re-read every artifact and validate the complete
   transaction before returning success.

If first creation fails, only artifacts owned by that new transaction are
removed. The sealed base is never in a deletion set. A later run accepts either
zero managed artifacts or the complete lifecycle-specific set; partial sets,
stranded staging files and orphan identity state fail closed.

The domain uses firmware auto-selection, a VM-specific NVRAM path and, when
required, a VM-specific swtpm directory. Libvirt may add device addresses, so
idempotence compares the fields owned by this brick rather than byte-comparing
normalized XML. Offline `qemu-img` chain inspection runs only while the domain
is shut off.

The primary disk source disables only libvirt's per-image DAC relabel. The
guest transaction already grants the reviewed QEMU identity exactly the access
it needs: the writable top disk is QEMU-owned, while a disposable backing base
is `root:<qemu-group>` and read-only. Allowing dynamic DAC relabel would change
that sealed base to the QEMU user on first start; libvirt deliberately does not
restore ownership of read-only backing images because they may be shared. The
per-source `model=dac, relabel=no` label is inherited by the backing chain and
preserves the stronger root-owned base contract without disabling other
security drivers or changing the host-wide `qemu.conf` policy.

An otherwise exact domain created before this pin may be migrated only through
`vm-create`, only while shut off. Check mode predicts the redefinition; the
real pass replaces the managed XML and redefines the same UUID, disk, NVRAM and
policy before strict comparison. Any additional XML difference still fails
closed.

Every modifying operation holds the per-VM lock. Start additionally holds a
global capacity lock from the live memory calculation through `virsh start`, so
two concurrent starts cannot both consume the same remaining budget. A
disposable start and explicit validation re-hash the sealed backing image; safe
shutdown and deletion remain available without adding that unrelated gate.

Lifecycle operations are separate playbooks. `reset` is legal only for a
shut-off disposable VM and keeps one lock across undefine, deletion and
recreation. It preserves the committed memory allocation while replacing disk,
NVRAM and TPM identity. `destroy` and forced `stop` require the exact VM name as
confirmation. Permanent reset is an error.

## Consequences

- A standard VM can be created, validated, started, gracefully shut down,
  force-stopped, reset when disposable, or destroyed without interpreting
  ad-hoc paths.
- `memory_mb: auto` is resolved at create time and recorded; a shut-off start
  rechecks that recorded allocation against the current live budget.
- Linux access requires one or more host-local public SSH keys. Passwords and
  private keys are not accepted by the role. The NoCloud seed creates only the
  declared locked-password account.
- A symlinked, relocated or cross-filesystem store path is a hard refusal before
  guest-owned paths are inspected, created or deleted.
- A managed domain cannot make its sealed backing base QEMU-owned merely by
  starting; the per-disk DAC exception is part of the compared XML contract.
- Current public manifests remain `not-built`, so production create correctly
  refuses until a base is sealed and imported. Tests use synthetic sealed
  fixtures; the image-build stage supplies the real image procedures.
- VFIO, Looking Glass, CPU pinning and GPU exclusivity remain M4 work and cannot
  accidentally appear in an M3 domain.
