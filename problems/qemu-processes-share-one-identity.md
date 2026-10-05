# Every QEMU process can open every Machine's disk

Author: [importriri](https://github.com/importriri).

Status: open; the decision is ADR 0037, proposed. Found by review on
2026-10-05 from read-only observations on Nitro; nothing was exploited.

## Symptom

None observed. Roadmap milestone 10 asks for "sVirt/AppArmor confinement of
every QEMU process verified, not assumed". Verifying it showed there is
none.

## Diagnosis

Read on Nitro without privilege:

- `virsh capabilities` lists the security models `none` and `dac` only: no
  sVirt driver (AppArmor or SELinux) is in use.
- `/sys/kernel/security/lsm` is `capability,landlock,lockdown,yama,bpf`:
  neither AppArmor nor SELinux is active in the kernel.
- every running `qemu-system-x86` process runs as `libvirt-qemu`
  (uid 963), the same user for every Machine.

From the repository: `roles/guest/tasks/create.yml` commits every Machine
disk as `libvirt-qemu:libvirt-qemu 0640`, and the managed domain pins
`relabel="no"` for DAC on the disk.

So the host is protected from a guest by DAC (QEMU is not root), but the
Machines are not protected from each other: code that escaped one QEMU
process, say of a `dirty` or `lab` Machine, could read and write the disk of
every other Machine, `dev-01` included.

## Cause

The guest lifecycle relies on libvirt's DAC model with one QEMU user, as
Arch configures it; no MAC driver was ever enabled, and the roadmap item
was written as a check of something assumed present.

## Fix

Pending ADR 0037. The chosen route, AppArmor with libvirt's per-domain
profiles, is not available with Arch's libvirt, which is built without its
AppArmor and SELinux drivers; the ADR now weighs a local libvirt build
against per-Machine DAC identities with one AppArmor profile for QEMU. The
kernel side is prepared: an AppArmor boot entry that is not the default.

## Regression proof

`tests/qemu_confinement_contract.py` records today's state as an explicit,
reviewed gap: it fails if the guest role starts claiming confinement
without a security driver, and it is where the chosen fix's checks go.
