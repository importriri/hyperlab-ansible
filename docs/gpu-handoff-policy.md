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

## The state transaction

Reading the recorded level, comparing the request and committing the new level
are one transaction. libvirt may run `prepare` hooks for different domains at
the same time (a manual `virsh start`, autostart), so without serialization a
cleaner request could read a stale level and overwrite a dirtier one committed
in between.

```text
/run/gpu-handoff/            real directory, never a symlink
/run/gpu-handoff/lock        hook-owned flock(2) lock, mode 0600
/run/gpu-handoff/trust       the committed level, mode 0644
/run/gpu-handoff/trust.*     a commit in progress, never read
```

For a mapped domain the hook:

1. creates the state directory if needed and refuses one that is a symlink;
2. creates the lock privately if needed, refuses a lock that is a symlink or
   not a regular file, and waits at most 10 s for an exclusive `flock`; any
   failure to create, open or acquire it refuses the start;
3. under the lock, refuses a `trust` that is a symlink, not a regular file,
   unreadable or not a number, and refuses a request above the recorded level;
4. writes the new level to a `mktemp` file in the same directory, makes it
   `0644` (the desktop reads the level without privilege) and renames it over
   `trust`.

Any failure in step 4 exits nonzero and removes the temporary file, and the
previous `trust` stays byte-identical: a failed write can never leave a missing
or truncated level that would authorize a cleaner domain later. The kernel
releases the lock when the hook exits, whether it succeeded, refused, was
interrupted or was killed. A hook killed with `SIGKILL` may leave a `trust.*`
file behind; it is never read, and the next reboot clears it.

The lock is the hook's own. The managed start's GPU and capacity locks are
directories under the guest lock root, taken by the playbook around
`virsh start`; the hook never takes them and the playbook never takes this one,
so a managed start whose hook runs inside them cannot wait on itself. The
managed locks order managed starts; this lock orders every `prepare`, managed
or not.

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
  contract coverage. On Nitro, `dev-01`, created from `workstation-dev`, has
  its `domains.d` entry and runs with the GPU; the physical acceptance of
  that entry being matched at start, and of an unmapped passthrough domain
  being refused, is still open.
- A boot-scoped GPU lease (a GPU-capable Machine that may also start without
  the GPU) is decided in [ADR 0019](adr/0019-gpu-lease.md) and not yet
  implemented.
