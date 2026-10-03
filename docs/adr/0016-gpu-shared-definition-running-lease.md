# ADR 0016 - Several managed VFIO domains may name the GPU; one runs with it

## Context

[`0009-vfio-guest-ownership.md`](0009-vfio-guest-ownership.md) refused to
define a VFIO domain while any other defined domain named the same PCI
functions. With one VFIO workstation that was enough. The product needs more:
`arch-dev-vfio`, Machines created from `workstation-dev`, and the
`gaming-clean` and `gaming-dirty` workstations all use the one GPU of the
laptop, at different times.

The first Machine from a Template, `dev-01`, was refused for exactly this:

```text
VFIO registry refused: VFIO devices ['0000:01:00.0', '0000:01:00.1'] are
already assigned to libvirt domain arch-dev-vfio
```

`arch-dev-vfio` was shut off. Only one domain can use the GPU at a time,
but defining a second one is not using it.

## Decision

Naming the GPU in a definition is not owning it. Owning it is a lease that
starts when the domain starts and ends when it stops.

- **Define.** A HyperLab-managed VFIO domain may name the same PCI functions
  as other HyperLab-managed VFIO domains. Managed means the domain carries
  HyperLab instance metadata with `device-profile="vfio"`, current or legacy
  namespace. A domain without it, for example one defined in virt-manager,
  still blocks: HyperLab never shares the GPU with a domain it does not
  manage.
- **Start.** Under the global GPU lock, the start refuses when a running
  domain names any of the same PCI functions, or the same Looking Glass
  device (`/dev/kvmfr0`), or the fixed SPICE port.
- **Trust.** Unchanged. The qemu hook still applies the contamination ladder
  at every start, so within one host boot the GPU still only moves clean →
  dev → dirty → lab.

## Consequences

- `arch-dev-vfio`, Machines from `workstation-dev`, `arch-gaming-clean` and
  `arch-gaming-dirty` can all be defined at once; one of them runs with the
  GPU.
- libvirt also refuses to start a second domain on PCI functions in use; the
  start check refuses first, under HyperLab's own lock, with a clear message.
- A domain started outside HyperLab (plain `virsh start`) still meets the
  hook's ladder and libvirt's own refusal; it does not meet HyperLab's lock.
- Still open in roadmap 5b: a GPU-capable Machine that can also start
  without the GPU, which needs a domain definition without the hostdev.
