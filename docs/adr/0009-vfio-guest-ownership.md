# ADR 0009 - VFIO ownership extends the guest transaction

## Context

M3 makes standard VM lifecycle transactional, but PCI passthrough adds host-local
facts and exclusivity that cannot be copied into a portable VM manifest. The
same NVIDIA GPU appears at machine-specific PCI addresses, its graphics and
HDMI-audio functions must move together, Looking Glass and kvmfr must agree on
one shared-memory contract, and only one VFIO domain may run at a time.

The existing GPU handoff hook also receives a libvirt **domain name**, while the
original rotation file contained security-domain names such as `clean` and
`dirty`. That mismatch meant a real VM name was not a member of the rotation and
could pass through without changing trust state.

## Decision

VFIO remains part of the existing `guest` transaction rather than becoming a
parallel lifecycle implementation.

A checked-in VM spec and image manifest determine portable intent. The
root-owned report produced by `hardware_probe` supplies host-local PCI BDFs.
`tools/vfio_plan.py` combines both only after checking:

- the selected reviewed laptop profile and its two PCI IDs;
- graphics function 0 and HDMI-audio function 1 on one PCI slot;
- the image's VFIO and Looking Glass support;
- the shared Looking Glass build, `/dev/kvmfr0`, buffer size and fixed loopback
  SPICE endpoint;
- the VM's network against the reviewed GPU trust map;
- no autostart and no memory overcommit for pinned VFIO memory.

Create, reset, start and validation rebuild this host-local plan. The committed
VM state records the resulting PCI and transport identity. Shutdown, forced
stop and destruction can use committed state so recovery does not depend on the
GPU still being present.

The rendered libvirt domain owns both reviewed PCI functions through managed
`hostdev` elements. Looking Glass uses the kvmfr character device through a
pinned QEMU command line; VFIO SPICE uses a private per-domain UNIX socket for
input and recovery and does not expose a TCP listener. A VGA device remains until hardware acceptance proves the complete
Looking Glass path. Linux guests may request the same IVSHMEM transport only
through the explicit experimental mode; SPICE remains available throughout. VFIO domains use virtio keyboard and mouse, explicitly disable the Q35 PS/2
controller so libvirt cannot synthesize duplicate legacy input devices, and
disable the balloon because IOMMU-pinned memory is not reclaimable.

Before definition, every libvirt domain is checked for UUID, MAC and PCI
collisions. Before start, a global GPU lock and the existing capacity lock are
held while libvirt is re-read for PCI and fixed-SPICE ownership. The trust hook
uses two independent files:

1. `rotation`: security-domain to trust-level mapping;
2. `domains`: exact libvirt-domain to security-domain allowlist.

An unlisted VM never touches GPU state. A listed VM may move the GPU only to the
same or a lower trust level until reboot clears `/run/gpu-handoff`.

## Consequences

- Standard and VFIO guests share disk, state, locking, rollback and destructive
  confirmation semantics.
- No public repository file hard-codes laptop PCI addresses.
- The reviewed VFIO allowlist contains `win11clean-valley`,
  `arch-dev-vfio` and `win11dirty-disposable`. The Linux candidate is bound to
  the `dev` trust profile for the Nitro hardware campaign.
- Services can never receive the GPU because no services trust level exists.
- The two Windows images must contain the pinned Looking Glass host application
  before they can be sealed and used. Linux uses no image-host evidence: an
  explicit `linux-experimental` mode builds the sender from the same shared
  source pin and remains disabled pending hardware acceptance.
- USB passthrough and real-time scheduling remain later stages. CPU pinning is
  rendered only when the selected host profile contains a reviewed plan for the
  exact guest vCPU count and preflight confirms the expected host thread count.
- Hardware validation is deferred to the final campaign; until then M4 remains
  a draft stage protected by host-independent plans, render tests, protocol
  tests and CI.
