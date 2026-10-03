# GPU handoff policy

The discrete GPU is passed to at most one guest at a time. Once a guest has
used it, the device may carry state that guest wrote. The GPU handoff policy is
the host-owned rule that decides which guest may take the device next in the
same host boot.

This document records the decision and the vocabulary around it. The
implementation lives in `roles/gpu_handoff/files/qemu` (the libvirt hook),
`tools/gpu_handoff_policy.py` (the root-owned managed policy tool) and the
guest planners.

## The ladder

```text
clean  3
dev    2
dirty  1
lab    0
```

Each GPU-capable domain maps to one handoff profile. On the libvirt `prepare`
phase the hook compares the domain's level with the level recorded in
`/run/gpu-handoff/trust` for the current boot:

- equal or lower: the domain may take the GPU and the recorded level drops to
  its level;
- higher: refused. Only a host reboot clears the record and raises the ceiling
  again.

`/run` is a tmpfs, so the record never survives a reboot. A missing, redirected,
corrupt or duplicated policy input is a refusal, never a default.

The ladder is monotonic per boot by design. It does not try to prove that a GPU
reset removed guest state; it assumes it did not. That is why the decision is a
ladder and not a per-guest allowlist: what matters is the worst code that has
run on the device since boot.

`services` is a network identity, not a rung. A services Machine that needs the
GPU (a local inference service, for example) requests a reviewed handoff profile
explicitly, and its Template must allow that profile.

## Where a domain's profile comes from

```text
/etc/gpu-handoff/domains          static map for checked-in fixtures
/etc/gpu-handoff/domains.d/*.conf one root-owned file per C10 Machine
```

The static map is rendered from `gpu_domain_profiles` in
`group_vars/all/networks.yml`. The managed directory is written only by
`tools/gpu_handoff_policy.py` during a privileged guest lifecycle operation.
The hook merges both surfaces and refuses duplicate domain names, symlinks,
files whose name does not match the domain they describe, and unknown profiles.

The hook never reads the user-owned Machine registry or a VM-spec. Product
intent reaches it only after the privileged tool has written the root-owned
file.

A domain absent from both surfaces is not a GPU domain and passes without
touching the recorded level, but only if the domain XML that libvirt passes on
stdin carries no PCI passthrough: no `<hostdev type='pci'>` and no
`<interface type='hostdev'>`. An unmapped domain with PCI passthrough, or a
call with no domain XML at all, is refused. Without that check a domain left out
of the policy could take the GPU without ever lowering the ladder. The domains
provider still reports such a domain as `domains.unguarded_vfio` before anyone
tries to start it.

## The ceiling rule

A handoff profile may lower, never raise, the class that a ranked network
identity already implies:

| network_profile | allowed gpu_handoff_profile |
|-----------------|-----------------------------|
| clean           | clean, dev, dirty, lab      |
| dev             | dev, dirty, lab             |
| dirty           | dirty, lab                  |
| lab             | lab                         |
| services        | any profile its Template allows |

The Machine factory, `tools/guest_plan.py` and the root-owned policy tool each
enforce this rule. The root tool enforces it even for a plan that did not come
from the factory, because the `managed-machine` tag on a plan is a provenance
claim, not a boundary. Removing a policy skips the rule so a stale entry can
always be cleaned up. See
[`problems/managed-machine-provenance-claim.md`](../problems/managed-machine-provenance-claim.md).

## Vocabulary

| Field | Where | Meaning |
|-------|-------|---------|
| `network_profile` | Template defaults, Machine, VM-spec | network identity and host-owned provenance |
| `gpu_handoff_profile` | Template allowlist, Machine, VM-spec, libvirt metadata | requested contamination class for GPU handoff |
| `gpu_trust_profile` | provider output | handoff class observed on the root-owned policy surface |
| `gpu_policy_state` | provider output | for a product Machine: `verified`, `missing`, `mismatch`, `metadata-missing`, `unexpected`, `not-required`, or the policy-surface failure `unavailable`, `unsafe`, `collision`; for any other domain: `legacy-static` or `not-configured` |
| `device_capabilities` | Template | the device capabilities a Template offers (plural map) |
| `device_capability` | Machine | the one capability a Machine was created with |
| `device_profile` | VM-spec, guest plan, VFIO planner, root policy payload | the derived compatibility field; the Machine projection sets it from `device_capability` |

`device_profile` is kept in the derived layers on purpose. Renaming it there
would break the existing guest lifecycle without changing what it means.

## Known open work

- The managed policy surface and the unmapped-passthrough refusal have
  contract coverage only. No real `domains.d` entry has been written on Nitro
  yet, and no unmapped passthrough domain has been refused on hardware.
- A boot-scoped GPU lease (a GPU-capable Machine that may also start without
  the GPU) is a product direction, not an implemented feature.
