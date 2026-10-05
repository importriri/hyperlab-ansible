# ADR 0034 - USB passthrough per Machine through an explicit host action

Status: proposed. The operator chooses before it is built; today every
spec's `usb_allowlist` is empty and no Machine gets a USB device.

## Context

A USB device given to a guest is driven by the guest: a keyboard can type
into it, a storage stick can be read and written by it, and a malicious
device can attack the guest's drivers. Some Machines need one: a hardware
key in `dev`, a controller in a gaming Machine. Roadmap milestone 6 asks for
an explicit host action with a host-side allowlist.

## Options

**A. Host allowlist plus a one-run attach action (recommended).** A
root-owned host allowlist names devices by vendor, product and serial, each
with the network classes it may go to (a hardware security key never to
`dirty` or `lab`). A host action attaches one allowed device to one running
Machine with `virsh attach-device --live` and never `--config`, so a reboot
or a stop returns it to the host. The Machine spec's `usb_allowlist` must
also name the device. The shell shows the device on the Machine's card while
attached, and detaching is one action.

**B. Static per-Machine passthrough in the domain definition.** Simpler, but
the device is the guest's whenever the Machine runs, which is what an
explicit action exists to avoid.

**C. USB/IP or redirection over SPICE.** Rejected: a network or display
channel carrying USB is more surface than a local attach.

## Recommendation

A. Keyboards and mice are never passed through: input stays with the host
and reaches a guest through the display client.
