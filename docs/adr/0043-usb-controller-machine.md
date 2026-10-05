# ADR 0043 - A USB Machine owns the USB controller (sys-usb)

Status: proposed. Nothing is built; the hardware test below decides it.

## Context

Roadmap milestone 10. USBGuard ([ADR 0038](0038-host-usb-device-policy.md))
stops the host from trusting a new USB device, but the host kernel still
enumerates every device plugged in: it reads the descriptors and runs the
USB core's parser before any policy is applied. A malicious device attacks
that code in the control plane. With `iommu=pt`, a controller the host
drives is also outside IOMMU translation. Giving the controller to a Machine
through VFIO moves enumeration, drivers and the controller's DMA into that
Machine.

This is feasible on Nitro because nothing the operator needs to drive the
host is on USB: the internal keyboard is i8042 (`serio0`) and the touchpad
is an I²C device on `00:15.x` (IOMMU group 8), both staying with the host.

Read on Nitro without sudo on 2026-10-05, from `lspci -nn`,
`/sys/kernel/iommu_groups`, each device's `reset_method` and `driver` in
sysfs, and `/sys/bus/usb/devices`:

| Device | PCI | IOMMU group | Reset |
|---|---|---|---|
| Intel xHCI `8086:06ed` (the only USB controller) | `00:14.0` | 6 | none listed |
| Intel shared SRAM `8086:06ef`, no driver | `00:14.2` | 6 | none listed |

Every USB device hangs off that one controller: the internal webcam
(`0408:a061`), the Bluetooth half of the Wi-Fi card (`8087:0026`), and
every external port. There is no second controller to keep for the host.

## What the host loses

- **The camera.** It belongs to sys-usb; a Machine that needs it gets it
  through the device handoff below, which replaces the host PipeWire stream
  of [ADR 0035](0035-microphone-and-camera.md) for the camera.
- **Bluetooth.** Headsets and other Bluetooth devices are no longer the
  host's.
- **Every external USB port**, including storage. If the restic target of
  [ADR 0036](0036-machine-snapshots-and-backups.md) is a USB disk, the host
  cannot write to it directly while sys-usb runs; backups need another
  target or this ADR waits for that decision.
- **USB security keys and external USB input devices on the host.** An
  external keyboard or mouse would reach the host only through an input
  proxy from sys-usb, which turns a guest into a source of host input. Not
  offered: the internal keyboard and touchpad are the host's input.

## Options

**A. A sys-usb Machine owns the controller; devices go to Machines through
an explicit host action (recommended).** A minimal Machine, not offered in
the Create view and on no network, gets `00:14.0` as a VFIO hostdev; the
shared SRAM in the same group stays without a driver (or is bound to
`vfio-pci`), as VFIO requires of a group's other devices. The controller is
bound to `vfio-pci` from boot by a boot profile, so the host never drives
it, with a fallback entry that leaves it to the host.

Handing a device to a Machine keeps ADR 0034's rules (a host allowlist by
vendor, product and serial with the networks each device may go to, one
action, one running Machine, nothing persisted) but changes the transport:
sys-usb exports the one device with USB/IP over a virtio-vsock port, and
the host relays the bytes to the target Machine's vsock port without
parsing them. The host never sees the device as a USB device; sys-usb and
the target do. ADR 0034 rejected USB/IP over a *network*; vsock relayed by
the host is not one, and no network carries USB.

**B. sys-usb with whole-controller assignment only.** No per-device
handoff: when a Machine needs USB, sys-usb stops and that Machine gets the
controller. Simpler, but every device goes with it, the camera included.

**C. Stay with USBGuard on the host.** No new Machine; the host keeps
enumerating every device.

## Giving the controller back to the host

The boot profile that binds `00:14.0` to `vfio-pci` is one entry; the
current entries leave it to the host, so the fallback is choosing an entry
in the boot menu or `bootctl set-oneshot`. The controller lists no reset
method, so VFIO cannot reset it between sys-usb runs; whether sys-usb can
restart without a host reboot is part of the test.

## Hardware test

On Nitro, with the commands in the operator's test plan:

1. Before: the controller's driver, the USB devices (`/sys/bus/usb/devices`),
   `usbguard list-devices`, and the keyboard and touchpad working.
2. Boot the sys-usb profile by one-shot entry: `00:14.0` on `vfio-pci`,
   the host lists no USB devices, the internal keyboard (LUKS prompt,
   session) and touchpad work.
3. sys-usb started: inside it the webcam, Bluetooth and a test USB stick
   enumerate; the guest's kernel log shows no controller error.
4. sys-usb stopped and started again: devices enumerate again, or the test
   records that a host reboot is needed.
5. A device handed to `dev-01` through the vsock relay: it appears there
   and nowhere else, and returns to sys-usb when `dev-01` stops.
6. Suspend and resume with sys-usb running.
7. The fallback entry: the host drives the controller again and USBGuard's
   policy applies as before.
