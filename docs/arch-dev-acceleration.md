# Arch VFIO development guest

`arch-dev` remains the standard recovery-friendly workstation. `arch-dev-vfio`
is a separate accelerated candidate built from the same sealed Arch base so GPU
work does not rewrite the proven standard guest.

The ordered hardware procedure is in
[`nitro-arch-dev-vfio-campaign.md`](nitro-arch-dev-vfio-campaign.md).

## What is already proven on Nitro

The current Nitro work has established:

- the RTX 3060 and HDMI-audio functions are attached to the guest;
- the guest runs the reviewed Zen kernel and open NVIDIA driver;
- nouveau is absent and NVIDIA DRM modesetting/fbdev are enabled;
- the guest kvmfr device comes from the IVSHMEM function and is writable by the guest user;
- Hyprland can run against the NVIDIA DRM node without the QEMU recovery display;
- an explicit `HEADLESS-0` receives the managed `1920x1080@144`, position `0x0`, scale `1` rule;
- PipeWire/XDPH capture produced real 1920×1080 frames;
- the Linux Looking Glass sender transported those frames through kvmfr to the physical-host client.

The sender remains manual. No persistent sender service is part of the role.

## VFIO group acceptance

The display and audio functions must share one IOMMU group and that group must
be a viable VFIO group before the accelerated domain is managed. A peer bridge
is accepted only when it has PCI class `0604` and remains bound to `pcieport`;
any other peer using a host driver refuses the gate. This permits the upstream
PCIe bridge needed by the Nitro topology without weakening ownership checks for
other devices in the group.

## Why the headless output is explicit

With `AQ_DRM_DEVICES` restricted to the passed NVIDIA card and its physical HDMI
connector disconnected, Hyprland starts successfully but exposes no output. The
normal monitor rule cannot configure an output that does not exist.

The VFIO guest therefore creates `HEADLESS-0` once from `hyprland.start`; the
existing monitor rule then owns mode, position and scale. Keeping creation and
policy separate avoids timing loops and runtime-only monitor commands.

## Remaining gates

The following are still open and must stay described as such:

- fresh-session proof that the managed headless output appears without a manual command;
- permanent deterministic XDPH selection of that headless output;
- Looking Glass keyboard and pointer return;
- lock/unlock and guest reboot/reconnect observations after the persistence work;
- the final post-reboot idempotent guest pass.

SPICE remains configured for recovery/input plumbing, but it has not been a
reliable video signal on this Nitro setup. Looking Glass frame production is the
video proof.
