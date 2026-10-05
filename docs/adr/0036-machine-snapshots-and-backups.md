# ADR 0036 - Snapshots and encrypted backups of Machines

Status: proposed. The operator chooses before any of it is built; today only
registered services have backups, offline, local and unencrypted
(`docs/service-vm-contract.md`).

## Context

Roadmap milestone 7 asks for snapshots of permanent Machines from the shell
with retention, encrypted backups of Machines, the Machine registry and the
host configuration to a target the guests cannot reach, a restore drill on a
clean host, and the Golden Image and Template catalogue backed up with
their digests. Three facts constrain it:

- a permanent Machine's disk must stay an independent qcow2 with no backing
  file: validation refuses anything else (`tests/sealed_base_use_contract.py`);
- a VFIO Machine cannot be snapshotted live with its device state;
- the service backups already prove one pattern: an offline, independent
  qcow2 copy, checked, then committed atomically under a lock.

## Options for snapshots

**A. Offline independent copies (recommended).** A snapshot is the service
backup pattern applied to a Machine: shut off, `qemu-img convert` of the
disk and a copy of its NVRAM and state receipt into
`snapshots/machines/<name>/<UTC id>/`, checked and committed atomically; a
retention count per Machine prunes the oldest. Restoring keeps the current
disk as a rollback until the restored one is checked. The shell offers
Snapshot and Restore on a shut-off permanent Machine through the operation
runner.

**B. libvirt external snapshots.** Fast, but each one adds a backing chain
under the Machine's disk, which the permanent-disk invariant forbids.

**C. qcow2 internal snapshots.** No new files, but they live inside the disk
they protect and cannot cover the NVRAM.

## Options for encrypted backups

**A. restic to a host-only target (recommended).** A root-owned restic
repository on an external disk, or on a remote reached only from the host's
own namespace, never from a guest network. It holds snapshots of Machines,
the Machine registry, `/etc` pieces HyperLab owns, the image store's sealed
images with their receipts, and the repository checkout. The repository key
lives in a root-only file, and a printed recovery copy is the operator's.
**B. borg**, same shape, different tool. **C. age-encrypted tarballs**, no
deduplication, simple to audit.

## Recommendation

Snapshots A; backups A, because restic verifies its repository
(`restic check --read-data`) and the drill restores onto a clean host from
the repository and the recovery key alone. The catalogue needs no new
format: its manifests and Templates are in the backed-up checkout, and each
sealed image travels with its receipt, so a restore verifies every digest
before anything uses it.
