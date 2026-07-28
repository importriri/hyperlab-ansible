# ADR 0007 - Memory is a run-time budget, never a laptop literal

## Context

The two target laptops have different RAM today and both may be upgraded.
A literal guest allocation is therefore either unsafe on the smaller host or
wasteful on the larger one. VFIO makes the failure sharper: hostdev memory is
pinned, kvmfr is a fixed allocation, and ballooning is not a recovery plan.

A correct decision must account for running domains, per-domain QEMU cost,
capacity reserved for service VMs, and the candidate VM itself. It must also
avoid charging the same service memory twice.

## Decision

### Static consistency and run-time fit are separate

The static validator runs in CI without a hypervisor. It checks only facts
that do not require a host: positive sizes, image floors, device support,
Looking Glass pins and the rule that VFIO cannot opt into overcommit. A green
static result never means that a VM will fit.

The run-time fit check, implemented in M2, reads host memory and live libvirt
state immediately before create/start. It is the only component allowed to
approve capacity.

### Host-profile inputs

Each physical `host_profile` declares:

- `host_reserved_mb`: operating system, page cache and optional cockpit;
- `qemu_overhead_per_domain_mb`: memory outside each guest allocation;
- `services_reserved_mb`: capacity promised to service VMs even while idle;
- `vfio_fixed_overhead_mb`: kvmfr and the pinned-guest margin;
- `max_auto_memory_mb`: ceiling for one `memory_mb: auto` candidate;
- `standard_overcommit_ratio`: commitment ceiling for standard VMs, normally
  `1.0` and never applied to VFIO.

No profile declares total RAM. `memtotal_mb` is a run-time fact, so a RAM
upgrade needs no repository edit.

### Values read from libvirt

At run time the checker records:

- `active_guest_mb`: sum of configured memory for every running domain;
- `active_domain_count`: number of running domains;
- `active_service_mb`: part of `active_guest_mb` belonging to the services
  domain;
- whether any active domain uses VFIO.

The unconsumed service reserve is:

```text
unconsumed_services_mb = max(services_reserved_mb - active_service_mb, 0)
```

Active service VMs are therefore counted once in `active_guest_mb`; only the
unused part of their promise is deducted separately.

### Physical candidate budget

For a candidate VM:

```text
overhead_mb = (active_domain_count + 1) * qemu_overhead_per_domain_mb

base_guest_pool_mb = memtotal_mb
                   - host_reserved_mb
                   - unconsumed_services_mb
                   - overhead_mb
                   - candidate_vfio_overhead_mb

candidate_vfio_overhead_mb = vfio_fixed_overhead_mb for vfio, otherwise 0
physical_remaining_mb = base_guest_pool_mb - active_guest_mb
```

The `+ 1` charges QEMU overhead for the candidate as well as every running
domain. Negative results fail closed.

For VFIO, `physical_remaining_mb` is the final budget. Overcommit is always
refused, and starting any overcommitted standard VM while a VFIO domain is
running is also refused.

### Standard overcommit

A standard VM may set `memory_overcommit: true`. The ratio lives in the
selected physical host profile, not in prose and not independently in every
spec:

```text
commit_limit_mb = floor(base_guest_pool_mb * standard_overcommit_ratio)
commit_remaining_mb = commit_limit_mb - active_guest_mb
```

The checker uses `commit_remaining_mb` only when the candidate is standard,
it explicitly opts in, no VFIO domain is active, and the ratio is greater
than `1.0`. Otherwise it uses `physical_remaining_mb`.

### `auto`

```text
memory_mb: auto -> min(selected_remaining_mb, max_auto_memory_mb)
                  rounded down to a multiple of 1024
```

The result must still meet `image.min_memory_mb`. Failure reports every input:
total RAM, host reserve, service reserve consumed/unconsumed, active domain
allocations, domain count, per-domain overhead, VFIO overhead, selected ratio,
remaining capacity and the image floor.

## Consequences

- RAM upgrades require no edits.
- Service VMs are never counted twice.
- QEMU overhead scales with the number of active domains and includes the
  candidate.
- Standard overcommit is explicit and data-driven; VFIO remains physical-only.
- CI validates consistency without pretending to validate fit.
- M2 can implement the arithmetic directly without interpreting ambiguous
  prose.
