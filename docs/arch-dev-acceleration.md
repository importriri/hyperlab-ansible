# Arch VFIO development guest

`arch-dev` remains the standard recovery-friendly workstation. `arch-dev-vfio`
is a separate accelerated candidate built from the same sealed Arch base so GPU
work does not rewrite the proven standard guest.

The ordered hardware procedure is in
[`nitro-arch-dev-vfio-campaign.md`](nitro-arch-dev-vfio-campaign.md).

## What is already proven on Nitro

The current Nitro work has established:

- the RTX 3060 and HDMI-audio functions are attached to the guest;
- a separate managed ICH9 duplex device carries usable guest audio over SPICE;
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

The opt-in Linux Looking Glass role also installs a root-owned XDPH picker and
points `~/.config/hypr/xdph.conf` at it. The picker refuses a missing or disabled
`HEADLESS-0` and otherwise returns that exact output through the upstream
`hyprland-share-picker` selection protocol. This removes the invisible portal
prompt from a headless session without enabling the sender or creating a
systemd unit. Because the picker grants screen capture without an interactive
consent dialog, it is confined to the explicit Linux Looking Glass experiment.

## Remaining gates

The following are still open and must stay described as such:

- Looking Glass keyboard and pointer return;
- lock/unlock and guest reboot/reconnect observations after the persistence work;
- the final post-reboot idempotent guest pass.

SPICE remains configured for recovery, input and audio plumbing, but it has not
been a reliable video signal on this Nitro setup. Looking Glass frame production
is the video proof; the virtual ICH9 device, rather than the disconnected NVIDIA
HDMI path, is the guest playback contract.

## Performance/security boundary

Guest acceleration is subordinate to the host security contract. See
[`performance-security-contract.md`](performance-security-contract.md) for the
measurement policy, forbidden security regressions and the transactional Gaming
Mode requirements.

The host remains the security boundary. Guest kernels, schedulers and gaming
runtime choices may be performance-oriented, but they do not justify weakening
host mitigations, IOMMU/VFIO ownership, Secure Boot state or managed hardening.
