# Hyperlab software-first roadmap

The repository is developed as ordered milestones. Software contracts and CI
land first; each milestone merges only after its exact head passes the hardware
gate that exercises its ownership boundary.

This avoids two bad extremes: merging untested automation, or keeping already
verified foundations trapped behind unrelated later workload work.

## Milestone state

```text
M0  cockpit and audit                         published foundation
M1  image, VM and brick contracts            published foundation
M2  Hyperlab image store                     published foundation
M3  standard guest lifecycle                 Nitro VM gate passed
M4  VFIO guest ownership                     software green; hardware gate pending
M5  image acquisition and sealing            Arch path passed; private paths pending
M6  Windows workshop                         software green; guest evidence pending
M7  service registration and recovery        software green; hardware gate pending
M8  reference Jellyfin appliance             software green; appliance gate pending
M9  release and evidence runner              software green; full campaign pending
```

“Software green” means the discovery-based repository battery passed. It is not
a hardware claim. The disposable Arch guest and two-loop storage path completed
on the Nitro; VFIO, private Windows images, service recovery, Jellyfin and the
full Predator campaign keep their own pending evidence boundaries.

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
The Nitro gate proved the `not-built` refusal, deterministic create/validate/
start flow, QEMU Guest Agent readiness, runtime SSH identity and the complete
two-loop Arch storage test without changing the sealed base.

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
recorded in ADR 0013.

## Remaining campaign

1. publish the exact green stage-1 and stage-2 trees on `main`;
2. keep the completed Nitro disposable-VM and two-loop evidence bound to those
   code trees;
3. run the remaining ordered Nitro gates without broadening their claims;
4. fix only observed bugs and repeat every affected gate when executable code
   changes;
5. run Predator with the same stage-1/stage-2 code trees that completed Nitro;
6. publish only sanitized evidence and final receipts in
   `arch-hypervisor-lab`.

CI proves repository contracts. Hardware evidence authorizes merges.
