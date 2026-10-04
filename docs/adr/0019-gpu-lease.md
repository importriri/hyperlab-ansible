# ADR 0019 - A GPU-capable Machine leases the GPU for one run

Status: proposed. The decision is recorded; implementation waits for the
preconditions below. Order agreed on 2026-10-04: first
`workstation-dev-standard`, then the Create view proven on Nitro, then the
lease.

## Context

[ADR 0016](0016-gpu-shared-definition-running-lease.md) lets several managed
VFIO domains name the GPU while only the running one owns it. Every VFIO
Machine still always starts with the GPU: its definition carries the
`<hostdev>` functions, the kvmfr device for Looking Glass and the fixed
SPICE port. Roadmap milestone 5b asks for more: a development Machine that
starts without the GPU for everyday work and restarts with it for Blender
or CUDA, and services Machines that may use the GPU through a reviewed
handoff profile.

libvirt starts a persistent domain only with its persistent definition, and
neither the NVIDIA functions nor the kvmfr ivshmem device can be hot-plugged
reliably into a running guest. Owning the GPU is therefore a property of one
run, fixed when that run starts.

## Decision

- **Capability.** A Template may offer `gpu_lease: optional` beside the
  existing `vfio` device capability. A Machine created with it is
  GPU-capable: it may run with the GPU or without it. A Machine without it
  keeps today's behaviour, the GPU on every run.
- **Two reviewed shapes.** The guest planner renders two domain definitions
  for a GPU-capable Machine: the VFIO shape of today, and a standard shape
  with no `<hostdev>`, no kvmfr device and an emulated display. The lease
  mode is recorded in the HyperLab domain metadata.
- **Start chooses.** A managed start takes `gpu: with | without`. Under the
  global GPU lock and the capacity lock, with the domain shut off, it
  defines the chosen shape, re-runs the existing ownership and ladder checks
  for a run with the GPU, and starts. The definition left behind is the
  shape of the last run. A start never edits a running domain.
- **Validation accepts exactly two shapes.** The managed XML contract
  compares a GPU-capable domain against both reviewed shapes and accepts
  only an exact match with one of them, reporting which; any other drift is
  still refused.
- **The ladder sees only real GPU use.** The qemu hook lowers the recorded
  level only when the domain XML it receives carries PCI passthrough. A
  mapped Machine starting without the GPU leaves the ladder untouched; an
  unmapped domain with passthrough is still refused. The ladder still
  guarantees that a lower-trust GPU use never precedes a higher-trust use in
  the same boot.
- **Services.** A services Machine may be GPU-capable only through a
  handoff profile its Template allows; the static rule that excludes
  services from the GPU is replaced by that Template review.
- **The shell** shows the lease: Start offers *with GPU* and *without GPU*
  for a GPU-capable Machine, and the card states which one the current run
  has, from the domain observed by the host, never from the guest.

## Preconditions before implementation

1. An image that has a working session on both shapes. The sealed
   `arch-dev-20261003` carries an NVIDIA-only session; a GPU-less run would
   have no desktop. `workstation-dev-standard`, captured from `arch-dev`,
   is the first candidate.
2. A Nitro test of the define-then-start sequence with the real NVIDIA
   functions: GPU run, GPU-less run, GPU run again in one boot, Looking
   Glass on the GPU run, SPICE on the GPU-less run, and the ladder level
   after each.
3. The operator's choice of which Templates offer the lease, and whether
   the default start is with or without the GPU.

## Consequences

- The domain definition changes between runs, so `virsh dumpxml --inactive`
  shows the last run's shape. Diagnostics reports the lease mode from the
  metadata.
- A crash between define and start leaves a valid reviewed shape defined,
  which validation accepts and the next start replaces.
- `local-ai` and other GPU services become possible on the same rules.
