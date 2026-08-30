# VFIO guest reboot can require a full QEMU power cycle

## Symptom

On the Nitro AN515-55 validation host, `arch-dev-vfio` was healthy before a
managed QEMU Guest Agent reboot. The reboot request was accepted while the QEMU
process remained alive, as designed.

The guest did not return to an operational state. Libvirt continued to report
the domain as running, but the QEMU Guest Agent channel stayed disconnected,
the guest no longer had a reported address or DHCP lease, the previous address
stopped responding, and the graphical console showed repeated NVIDIA modeset
progress errors.

This is not evidence that every VFIO guest reboot fails. It is one reproduced
hardware failure mode on the reviewed Nitro + RTX 3060 path.

## Root cause boundary

The original lifecycle proof treated `domstate=running` as evidence that the
reboot was progressing. That observation is insufficient for a guest reboot
because QEMU is intentionally kept alive throughout the operation.

The failure also proved that a running QEMU process does not imply a healthy
VFIO guest. The exact GPU/driver mechanism behind the failed guest-only reboot
is not claimed here; the acceptance contract is based on the observable
disconnect/recovery boundary instead.

## Fix

Managed reboot now keeps its narrow meaning: reboot the guest operating system
without replacing QEMU. For QGA-backed guests it must observe the guest agent
disconnect and reconnect before the operation is accepted as recovered. Failure
to reconnect remains a visible lifecycle error.

The Control Center also distinguishes the two operations explicitly:

- **Reboot** — guest OS reboot; QEMU stays running.
- **Power cycle** — force-stop QEMU, wait for `shut off`, then start a new QEMU
  process through the normal VFIO, capacity and QGA readiness gates.

There is no silent fallback from Reboot to Power cycle.

## Runtime proof

The failed reboot kept the original QEMU PID `2994`. QGA stayed disconnected
for the full managed reboot timeout, the runtime address disappeared, and the
guest console showed NVIDIA progress errors.

The explicit managed Power cycle then:

1. force-stopped the old QEMU process;
2. observed the required `shut off` boundary;
3. revalidated VFIO ownership and live host capacity;
4. started replacement QEMU PID `95673`;
5. restored QGA connectivity and guest address `10.10.3.198`;
6. restored SSH/Ansible reachability;
7. returned a healthy RTX 3060 in `nvidia-smi`;
8. produced no matching NVIDIA reset/Xid/progress errors in the new guest boot;
9. subsequently supported the cold-start Looking Glass path again.

The recovery proves the full-QEMU replacement path for this reproduced failure.
It does not claim that Power cycle repairs every possible VFIO or GPU fault.

## Regression gate

Keep the following properties pinned:

- a QGA-backed Reboot must cross a disconnect/reconnect boundary;
- Reboot must never call `virsh destroy` or silently replace QEMU;
- Power cycle must require exact destructive confirmation;
- Power cycle must cross `shut off` before starting replacement QEMU;
- the Control Center must describe Reboot and Power cycle as distinct
  operations for VFIO guests.
