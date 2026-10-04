# ADR 0022 - Network trust and GPU transition policy are separate authorities

## Context

A Machine has two security classes that look alike and are not: the network
it lives on, which is its identity and what the host frame shows, and the
contamination class it brings to the one discrete GPU. They were first
derived from each other, which excluded `services` Machines from the GPU and
let a GPU rule decide a network question. Roadmap milestone 0 asks for one
record of how the two relate, including GPU-capable services and the
boot-scoped lease. The mechanics are recorded in
[`../gpu-handoff-policy.md`](../gpu-handoff-policy.md),
[`0009`](0009-vfio-guest-ownership.md), [`0016`](0016-gpu-shared-definition-running-lease.md)
and [`0019`](0019-gpu-lease.md).

## Decision

- **Two fields, two authorities.** `network_profile` (clean, dev, services,
  dirty, lab) is the Machine's network identity and host-owned provenance.
  `gpu_handoff_profile` (clean, dev, dirty, lab) is the class it brings to
  the GPU. Neither is inferred from the other at run time.
- **The ladder.** Within one host boot the GPU moves only down
  clean 3 → dev 2 → dirty 1 → lab 0, enforced by the root-owned qemu hook
  against a tmpfs record. Only a reboot raises the ceiling again. The
  ladder assumes a GPU reset removes nothing.
- **The ceiling rule.** A handoff profile may lower, never raise, the class
  a ranked network implies: a dev Machine hands off as dev, dirty or lab,
  never clean. The Machine factory, the guest planner and the root policy
  tool each enforce it.
- **Services are not a rung.** A services Machine has no implied class. It
  may use the GPU only with a handoff profile its reviewed Template allows.
  That review replaces the static rule that excluded services from VFIO;
  the replacement itself is still open in roadmap milestone 5b.
- **Owning the GPU is per run.** Several managed domains may name the GPU;
  only the running one owns it (ADR 0016). A GPU-capable Machine chooses at
  each start whether this run has it (ADR 0019, proposed), and only a run
  that carries passthrough touches the ladder.
- **Fail closed.** An unmapped domain with PCI passthrough, a missing,
  redirected or duplicated policy input, or a profile outside the ladder is
  a refusal.

## Consequences

- A local inference service can live on `services` with a `dev` or lower
  GPU class, without renaming its network or inventing a services rung.
- The trust colour on screen is always the network identity; the GPU class
  appears in Diagnostics and on the GPU badge, never in place of it.
- The guarantee that matters holds whatever the Machine mix: no lower-trust
  code runs on the GPU before higher-trust code in the same boot.
