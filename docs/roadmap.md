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

1. finish repository cleanup without changing hardware claims and publish each
   software-verified integration milestone directly on `main`;
2. run the complete software verifiers and focused idempotence checks on the final
   clean automation trees;
3. freeze the exact public `arch-bootstrap` and `hyperlab-ansible` `main` commits
   in the release acceptance plan;
4. run the remaining Nitro desktop and `arch-dev-vfio` hardware gates against
   those frozen commits;
5. publish sanitized Nitro evidence and compatibility status only after every
   required Nitro gate is green;
6. replay Predator with the same frozen `arch-bootstrap` and `hyperlab-ansible`
   commits;
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

## Canonical completion order

The candidate is completed in dependency order so later security and performance
work is measured against stable workloads rather than moving targets:

1. finish `arch-dev-vfio`, including pre-login display recovery, input
   isolation, physical audio proof, gaming stack readiness and idempotence;
2. extract reusable workstation behavior from the VFIO-specific path;
3. finish `arch-dev`;
4. finish `arch-minimal-ssh`;
5. seal and validate golden images, clone identity and clone lifecycle;
6. finish VM lifecycle and the Control Center operational/recovery surfaces;
7. freeze network security topology and the explicit allowed-flow matrix;
8. finish the host-owned visual provenance and trust model;
9. add endpoint HIDS with measured overhead and no hypervisor remote-command
   plane;
10. add passive NIDS without turning the sensor into an inline routing
    dependency;
11. correlate endpoint and network evidence in the HyperLab Security Plane;
12. perform final gaming/performance tuning with the complete security plane
    active;
13. run release qualification, idempotence, reboot, cold-start, recovery and
    hardware gates;
14. finish wallpaper/polish, screenshots, video and release documentation;
15. seal the sanitized release evidence and record the exact public `main`
    commits that were exercised on hardware.

Performance tuning comes after HIDS/NIDS so the final benchmark includes the
monitoring cost. HIDS/NIDS come after the network and VM contracts so normal
behavior is defined before anomaly detection is tuned.

### Linux VFIO PRIMARY display decision

The Nitro hardware campaign fixed the Linux VFIO PRIMARY connection contract:

- `Looking Glass` is the normal user-facing action.
- When the guest is at Ly, HyperLab uses an owned temporary `virt-viewer`
  console for authentication, waits for the reviewed Hyprland capture output,
  closes that temporary console, then opens Looking Glass automatically.
- `Console` remains the explicit standalone `virt-viewer` recovery action.
- `SSH` remains the administrative path.
- The Looking Glass built-in SPICE display fallback is hardware-proven for
  display diagnostics but rejected for PRIMARY authentication because its
  pre-login input path was not reliable enough for the release contract.
- The Linux sender lifetime is bound to Hyprland: closing the host client does
  not end the guest session, while guest logout removes the sender.

This decision is frozen for `arch-dev-vfio` completion. Do not reopen the
single-window built-in fallback experiment unless the remaining input-security
work explicitly requires it.
