# ADR 0037 - Confining each QEMU process to its own Machine

Status: proposed. The operator chooses; both options change how every
Machine is defined, and the first changes the kernel command line.

## Context

On Nitro libvirt uses only the DAC security model, the kernel runs no MAC
module (AppArmor or SELinux), and every QEMU process runs as
`libvirt-qemu`, the owner of every Machine disk
([`../../problems/qemu-processes-share-one-identity.md`](../../problems/qemu-processes-share-one-identity.md)).
A guest that escapes its QEMU process reaches every other Machine's disk.
Roadmap milestone 10 asks for confinement that is verified, not assumed.

## Options

**A. AppArmor with libvirt's per-domain profiles (recommended first).**
Enable AppArmor in the kernel (`lsm=` on the command line, which
`vfio_boot` already manages), install `apparmor`, and set libvirt's
`security_driver = "apparmor"`. libvirt then generates a profile per domain
(`virt-aa-helper`) that lets each QEMU open only its own disk, NVRAM, TPM
state, sockets and devices. Also confines what QEMU may touch on the host
beyond disks. Needs a reboot and a check that VFIO, Looking Glass's
`/dev/kvmfr0` and the per-domain SPICE socket are in each profile.

**B. One DAC identity per Machine.** Each Machine gets its own system user
and group, set as a static DAC seclabel in its domain definition, and its
disk, NVRAM and TPM state are owned by that user; sealed bases stay
`root`-owned and readable through a shared group. No kernel change, but
user allocation and ownership become part of the Machine lifecycle and must
survive reset, resize and restore.

**C. Both.** MAC for what QEMU may touch, DAC so the boundary holds even
with the MAC module off.

## Recommendation

A first, because it confines more than disks and libvirt maintains the
profiles; then decide on B. Either way, a contract checks the security
driver and the per-domain labels, and Nitro proves it by reading a running
domain's profile or label and failing one cross-Machine open.
