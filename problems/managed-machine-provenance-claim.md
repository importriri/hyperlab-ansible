# A self-asserted Machine tag could grant a cleaner GPU handoff

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by contracts. The privileged path has
not yet materialized a real managed policy on Nitro.

## Symptom

The C10 privileged path accepts a guest plan for root-owned GPU policy
materialization when the plan carries the `managed-machine` tag, requests
`device_profile: vfio` and names a reviewed `gpu_handoff_profile`.

A hand-written VM-spec could carry that tag directly. With
`network_profile: dirty` and `gpu_handoff_profile: clean`, both `guest_plan.py`
and `tools/gpu_handoff_policy.py ensure` accepted the request, and the root tool
wrote:

```text
forged-dirty clean
```

to the managed policy directory.

## Root cause

The `managed-machine` tag is produced by the Machine projection, but nothing
binds it to a Machine record or a reviewed Template. It is a provenance claim
made by the plan itself.

The Template allowlist for handoff profiles is enforced only in the Machine
factory. The privileged tool checked that the profile was a reviewed trust level
but not whether it made sense for the network identity of the same plan. A dirty
guest recorded as `clean` defeats the monotonic per-boot ladder: a later clean
guest could take a GPU that dirty software had already used.

The person able to write `vm-specs/` and run the lifecycle with sudo already has
administrative power, so this was not privilege escalation. It was an integrity
hole in a policy that is meant to hold even against operator mistakes.

## Failed approach considered

Re-deriving the Template allowlist inside the root tool from `templates/` was
rejected as the main fix. That tree is writable by the same operator, so
reading it as root adds review friction without adding enforcement, and it would
let the privileged path depend on user-owned product state again.

## Fix

A `gpu_handoff_profile` may lower, never raise, the contamination class that a
ranked network identity already implies. The Machine factory, `guest_plan.py`
and `tools/gpu_handoff_policy.py` each enforce the rule independently, so it
holds even for a plan that never came from the factory. `services` is not
ranked and still requests its handoff profile explicitly. Removal skips the rule
so a stale or wrong policy can always be cleaned up.

The C10 contract document now states that the tag is a provenance claim, not a
security boundary, and lists what the privileged path enforces regardless.

## Regression proof

- `tests/c10_gpu_policy_materialization_contract.py`: a forged dirty/clean plan
  is refused and no policy file appears; a dev network lowered to `dirty` is
  accepted; a plan without a network identity is refused.
- `tests/c10_machine_materialization_contract.py`: the factory refuses a dev
  Machine with a clean handoff and accepts a dirty one.
- `tests/guest_contract.py`: `guest_plan.py` refuses a `lab` spec that asks for
  a clean handoff.
