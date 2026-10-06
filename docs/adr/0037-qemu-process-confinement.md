# ADR 0037 - Confining each QEMU process to its own Machine

Status: accepted (2026-10-06, option A2, chosen on the operator's
delegation). Part 1, the QEMU profile, is built; part 2, the per-Machine
identities, is next. Neither is proved on hardware yet.

## Context

On Nitro libvirt uses only the DAC security model, the kernel runs no MAC
module (AppArmor or SELinux), and every QEMU process runs as
`libvirt-qemu`, the owner of every Machine disk
([`../../problems/qemu-processes-share-one-identity.md`](../../problems/qemu-processes-share-one-identity.md)).
A guest that escapes its QEMU process reaches every other Machine's disk.
Roadmap milestone 10 asks for confinement that is verified, not assumed.

## Finding: Arch's libvirt has no AppArmor driver

The operator chose AppArmor with libvirt's per-domain profiles
(`virt-aa-helper`) on 2026-10-05. Checked before building it: Arch's
`libvirt` 12.7 is built with `-Dapparmor=disabled`,
`-Dapparmor_profiles=disabled`, `-Dsecdriver_apparmor=disabled` and the
SELinux equivalents off (`PKGBUILD` in Arch's packaging repository); the
installed package ships neither `virt-aa-helper` nor any profile. The
kernel side is ready: `linux-hardened` has `CONFIG_SECURITY_APPARMOR=y`
and only its default LSM list leaves it out, so `lsm=` on the command line
enables it, and `apparmor` 4.1 is in Arch's `extra` repository.

## Options

**A1. A locally built libvirt with the AppArmor driver.** Rebuild Arch's
`libvirt` with the AppArmor options on and install it in place of the
distribution package; libvirt then generates a profile per domain. The
strongest MAC confinement, but HyperLab would own a package of its core
hypervisor: every libvirt update waits for a rebuild, and the build itself
becomes part of the trusted base.

**A2. Per-Machine DAC identities plus one AppArmor profile for QEMU
(recommended now).** Each Machine's QEMU runs as its own system user, set
as a static DAC label in its domain, and owns only its disk, NVRAM and TPM
state; sealed bases stay root-owned and readable through a shared group.
This closes the cross-Machine disk access with packages Arch ships. On top,
one AppArmor profile for `qemu-system-x86_64` confines every QEMU process
from the rest of the host (home directories, keys, `/etc`), though it cannot
tell one Machine from another.

**A3. Per-Machine DAC identities only.** No kernel change; no MAC layer.

## Recommendation

A2: the per-Machine identities give the property that matters most, each
QEMU can open only its own Machine's files, without owning a libvirt build,
and the AppArmor profile adds a host boundary. A1 stays possible later.
The kernel side is the same for A1 and A2 and is prepared now: a fifth
systemd-boot entry, `Arch-Linux-Hardened-Vfio-AppArmor.conf`, identical to
the VFIO entry but for `lsm=landlock,lockdown,yama,integrity,apparmor,bpf`,
not the default until Nitro has proved it (`tests/apparmor_boot_contract.py`).

## Decision

A2. A1 would give per-domain MAC profiles, but HyperLab would own a rebuilt
hypervisor package: every libvirt security fix would wait for that rebuild,
and the build would join the trusted base. A2 uses only what Arch ships, and
splits the two properties between the mechanisms that can each enforce one:
DAC keeps one Machine's QEMU from another Machine's files, AppArmor keeps
every QEMU from the host's own data. If Arch ever builds libvirt with its
AppArmor driver, per-domain profiles can replace the shared one.

## Implementation

**Part 1, the QEMU profile** (`roles/qemu_apparmor`,
`playbooks/qemu-apparmor.yml`, `tests/qemu_apparmor_contract.py`). One
profile, `hyperlab-qemu`, attaches to `/usr/bin/qemu-system-x86_64`. It
grants the Machine store as each part needs it (disks, transient overlays
and NVRAM read and written; seeds and sealed bases read only), libvirt's
runtime files, the devices a Machine can be given (`/dev/kvm`, VFIO groups,
`kvmfr`, tun, vhost), the SPICE socket directory and the lab host's pool. It
gives QEMU no capability, and denies with an audit the homes, `/root`,
shadow, sudoers, SSH, the store's state and TPM directories, writes to
`/boot`, `/etc/libvirt` and the GPU policy. The role validates the profile
with `apparmor_parser` before installing it, installs it always, and loads
it only on a kernel running AppArmor (the AppArmor boot entry), in
`complain` until the lab host and then Nitro have run every Machine kind
under it with no denial, then `enforce`.

**Part 2, per-Machine identities** (next). Each managed Machine gets a
system user and group; its domain carries a static DAC label with that
identity; its disk, seed and NVRAM become `0600` files of that user; sealed
bases are read through a group that grants nothing else; a Looking Glass
Machine gets its own SPICE socket directory, readable by the operator
through an ACL and by no other Machine, and `kvmfr` access through a group
only VFIO Machines join. Existing Machines move when shut off, through the
guest role's reconcile path. It ships behind a switch that stays off until
the lab host has proved it.
