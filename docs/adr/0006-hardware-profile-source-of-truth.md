# ADR 0006 - One source of truth per question, for physical host profiles

## Context

The same physical-host PCI IDs are written twice: `group_vars/all/hardware.yml` in
hyperlab-ansible and `hardware/compatibility.yml` in
arch-hypervisor-lab. Nothing compares them. `tests/static_contract.py` is
called a cross-repository contract and never leaves its own repository.

## Decision

They answer different questions and both stay, with the overlap checked:

- **hyperlab-ansible** owns *what the pipeline configures* through `host_profiles`: the IDs
  it binds, the quirks it puts on a kernel line, the RAM it reserves.
  This is the operational truth, because it is the file that runs.
- **arch-hypervisor-lab** owns *what has been proven*: verification
  status, evidence links, which subsystems were tested on which laptop.
  Status never enters the ansible file - a repository cannot certify
  itself.

The overlap - vendor, family, `vfio_ids` - is verified by a real
cross-repository check that takes the path to the other checkout and
skips loudly when it is absent, so a single-repo clone still runs green
without pretending it checked anything.

## Consequences

- Adding a laptop means one entry per repository, and the check refuses
  the pair if they disagree on IDs.
- "Component verified" cannot silently become "pipeline verified" by
  editing the repository that would benefit from it.
- The badly named check gets a name that matches what it does, and the
  real cross-repo one gets its own CI job that checks out both.


`host_profile` is reserved for physical-machine selection. VM manifests and
specs use `device_profile: standard|vfio`; the two namespaces must never be
merged or overridden through shared variable precedence.
