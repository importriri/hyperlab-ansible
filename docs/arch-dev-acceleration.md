# Arch development workstation acceleration

The exact physical-host sequence is documented in [`nitro-arch-dev-vfio-campaign.md`](nitro-arch-dev-vfio-campaign.md).

`arch-dev` remains the recovery-friendly standard VM. `arch-dev-vfio` is a
separate candidate built from the same sealed Arch image so VFIO experiments do
not reinterpret or overwrite the proven standard workstation disk.

## Reviewed runtime profiles

Both VM names provide two resource profiles:

| Profile | RAM | vCPU |
| --- | ---: | ---: |
| `balanced` | 8 GiB | 4 |
| `heavy` | 16 GiB | 4 |

On the Nitro 5, the four-vCPU VFIO plan pins complete SMT pairs `2/6` and `3/7`
to the guest, `0/4` to QEMU emulation and `1/5` to one disk I/O thread. The host
must still pass preflight with eight logical CPUs before this XML can render.

## Recovery and acceleration layers

The accelerated VM deliberately retains loopback SPICE and a virtual VGA during
the hardware campaign. They are recovery paths, not the performance target.
The NVIDIA guest brick is applied only after both reviewed PCI functions are
attached and an NVIDIA function is visible inside the guest.

The full experimental guest order is:

1. Arch Zen kernel and access policy;
2. Hyprland workstation and development tools;
3. open NVIDIA DKMS, DRM modesetting and nouveau exclusion;
4. pinned upstream Looking Glass Linux sender build;
5. manual hardware gate before any sender service exists.

## Linux Looking Glass boundary

`looking_glass_mode: linux-experimental` is intentionally explicit. It enables
the same pinned kvmfr/IVSHMEM transport used by the physical-host client, but it
does not claim Linux sender support is production-ready.

The guest role builds the upstream `host/` target at the shared commit with
PipeWire enabled and XCB disabled. It installs an executable and a user-owned
`looking-glass-host.ini`, records `runtime_enabled: false`, and creates no
systemd unit. The first run must remain interactive so the Hyprland portal can
request a PipeWire screencast and hardware logs can be collected.

A fork is considered only after the pinned upstream sender has been built and
run against the actual passed NVIDIA GPU. The fork boundary, if needed, is the
Linux capture/input implementation; the LGMP protocol, kvmfr transport and
physical-host client stay upstream-compatible.

## Hardware gate still required

No static test can prove GPU reset, IOMMU isolation, NVIDIA DRM node selection,
portal capture, zero-copy behaviour, frame pacing or input return. Those claims
remain blocked until `arch-dev-vfio` passes the Nitro campaign with SPICE
recovery available throughout.

## Nitro acceptance tools

After the VFIO candidate is defined and running, the physical host runs
`tools/nitro/arch_dev_vfio_host_gate.py`. It is read-only and checks the active
`qemu:///system` XML, reviewed PCI addresses, 8/16 GiB profile, exact CPU and I/O
pins, loopback SPICE, virtual recovery video, kvmfr and the shared 64 MiB
IVSHMEM object. It then verifies that both host PCI functions remain
bound to `vfio-pci`, share one IOMMU group and expose a viable VFIO group
device. A PCIe root-port peer of class `0604` may remain on `pcieport`; any
other peer using a host driver causes the gate to refuse.

Inside the guest, run `tools/nitro/arch_dev_vfio_guest_gate.py` as `sid` from
the checked-out repository. It checks the NVIDIA display and audio functions,
the loaded open NVIDIA module set and DRM parameters, `nvidia-smi`, QEMU's
`1af4:1110` IVSHMEM PCI device, the exact shared Looking Glass source pin and
its manual-only runtime stamp.

Only after both markers are green does the operator start
`looking-glass-host` from the active Hyprland session. The first portal choice,
frame production, input path, lock/unlock, reboot and SPICE recovery remain
manual observations and must be recorded before enabling any persistent sender
unit or starting a fork.
