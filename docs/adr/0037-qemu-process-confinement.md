# ADR 0037 - Confining each QEMU process to its own Machine

Status: proposed. AppArmor was chosen on 2026-10-05; the libvirt driver it
assumed is not in Arch's package, so the way to it is open again below.

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
