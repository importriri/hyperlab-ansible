# HyperLab roadmap

Software verification and hardware evidence are separate. CI can prove that a
repository contract holds; only a named machine can prove that the hardware path
works.

## Current state

- **Encrypted Arch bootstrap:** validated on Nitro; the frozen release replay is
  still required.
- **Host KVM, networks and VFIO:** live Nitro validation passed.
- **Sway host desktop:** functional and idempotent on Nitro. The corrected drawer
  placement needs one visual recheck after cleanup.
- **Windows workshop:** the workflow exists; private master evidence stays local.
- **Arch standard guest:** Nitro lifecycle gate passed.
- **Arch VFIO guest:** NVIDIA, kvmfr and Looking Glass video are proven. Final
  session persistence and input checks remain open.
- **Service lifecycle:** software contracts are green; the hardware campaign is
  incomplete.
- **Predator:** profile reviewed; full replay of the frozen Nitro commits is
  pending.

## Release order

1. finish repository cleanup without changing hardware claims;
2. run the complete software verifiers and focused idempotence checks;
3. make local candidate commits and freeze their exact identities without pushing;
4. run the remaining Nitro desktop and `arch-dev-vfio` hardware gates against
   those clean commits;
5. publish the reviewed automation commits and sanitized Nitro evidence only after
   every required Nitro gate is green;
6. replay Predator with the same `arch-bootstrap` and `hyperlab-ansible` commits;
7. publish Predator evidence separately;
8. start reusable workstation or golden-image work only after the host release is
   coherent.

## Later work

- **M10 — domain manager and VM composition:** implemented; the live workload
  gate remains part of the release campaign.
- **M11 — desktop shell and Control Center:** implemented; the corrected Nitro
  drawer placement still needs its visual recheck.
- **M12 — snapshots, backups and golden images:** planned after the host release
  is coherent.
- **M13 — seamless guest applications:** future work and must not be described
  as providing Qubes OS security properties.
