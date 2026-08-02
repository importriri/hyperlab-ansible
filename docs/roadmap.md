# Hyperlab software-first roadmap

The repository is developed as ordered milestones. Software contracts and CI
land first; each milestone merges only after its exact head passes the hardware
gate that exercises its ownership boundary.

This avoids two bad extremes: merging untested automation, or keeping already
verified foundations trapped behind unrelated later workload work.

## Milestone state

```text
M0  cockpit and audit                         merged
M1  image, VM and brick contracts            merged after Nitro gate
M2  Hyperlab image store                     merged after Nitro gate
M3  standard guest lifecycle                 draft; next Nitro gate
M4  VFIO guest ownership                     stacked draft
M5  image acquisition and sealing            stacked draft
M6  Windows workshop                         stacked draft
M7  service VM registration and recovery     stacked draft
M8  reference Jellyfin appliance             stacked draft
M9  release and evidence runner              stacked draft
```

### M0 — cockpit and audit

Sway, Foot and input cleanup plus the first architecture decisions.

### M1 — contracts

Host/device profile separation, image manifests, VM specs, memory budgets and
the enforced brick dependency graph. Merged after Nitro preflight,
Looking Glass identity and second-run idempotence passed on the exact head.

### M2 — image store

Canonical, permissioned, NOCOW-aware directory layout. Merged after Nitro proved
runtime QEMU/swtpm identities, traversal, `+C` inheritance and `changed=0` on the
second apply.

### M3 — standard guest lifecycle

Deterministic plan, sealed-base checks, clone/overlay creation, cloud-init,
UEFI/TPM state, libvirt definition, capacity locking, reset and destruction.
Its current hardware gate must prove the `not-built` refusal after the required
network foundation exists and before any package or VM artifact is written.

### M4 — VFIO guest ownership

Host-local PCI planning, exclusive GPU starts, Looking Glass/kvmfr, fixed
recovery SPICE and trust-ranked handoff.

### M5 — image acquisition and sealing

Pinned official-cloud acquisition, private local import, qcow2 inspection and
provenance receipts.

### M6 — Windows workshop

Privacy-safe guest evidence, clean/dirty identity policies and Windows-workshop
hashes bound into image and guest provenance.

### M7 — service VM contract

Registration before VM creation, static DHCP identity, inactive-memory
reservations and offline backup/restore recovery.

### M8 — reference Jellyfin appliance

Guest-only package installation, lifecycle-bound TCP/8096 exposure and inert
future-service slots.

### M9 — release and evidence gates

Cross-repository storage hand-off, canonical Nitro/Predator plans, mode-`0600`
evidence scaffolds, ordered immutable gate recording, semantic storage and
Ansible-recap probes, sensitive-data refusal and deterministic final receipts.

## M9 implementation boundary

M9 completes software orchestration without pretending to complete hardware
validation:

- `bootstrap_storage` observes `/var/lib/libvirt/images` and validates the
  stage-1 contract before image-store writes;
- supported shapes are fixed to `cryptroot:/@vm` and `cryptvm:/`;
- the already validated legacy Nitro host may adopt one observed shape by exact
  confirmation without changing mounts, filesystems or VM data;
- fresh installs receive the contract from the complete `arch-bootstrap`
  entrypoint;
- `release/acceptance.v1.yml` owns gate order and evidence fields;
- `release_acceptance.py` owns plan, scaffold, checkout proof, ordered record,
  status and seal operations;
- `release_probe.py` owns file hashing, typed scalar payloads, live storage proof
  and Ansible recap interpretation;
- raw logs remain local and no tool pushes, publishes, merges or authorizes a
  destructive command.

The complete operator protocol is
[`release-evidence.md`](release-evidence.md). The storage and freeze decision is
recorded in ADR 0012.

## Remaining campaign

1. freeze exact green `arch-bootstrap` and M9 commits;
2. pass the two-loop-device bootstrap gate in an Arch-capable throwaway VM;
3. run the ordered Nitro gates;
4. fix only observed bugs and repeat affected gates when a head changes;
5. merge each milestone whose exact documented hardware gate passes;
6. run Predator with the same stage-1/stage-2 pair that completed Nitro;
7. publish sanitized evidence and final receipts in `arch-hypervisor-lab`;
8. merge the remaining verified milestones in order.

CI proves repository contracts. Hardware evidence authorizes merges.
