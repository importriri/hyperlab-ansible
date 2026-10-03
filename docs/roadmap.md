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
- **Host desktop / Hyprland migration:** the controlled first launch, managed Ly/session lifecycle and dedicated HyperLab Gate login theme are accepted on Nitro. The dual-compositor product contract remains frozen: Hyprland is preferred, Sway is first-class and the recovery compositor. Quickshell Phase 2A is installed and the Hyprland-first pilot now arms the shared shell inside the managed Hyprland session while preserving Sway/Waybar/GTK recovery.
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

## C10 — Machine Factory

Contract: [`c10-machine-factory-contract.md`](c10-machine-factory-contract.md).
GPU policy: [`gpu-handoff-policy.md`](gpu-handoff-policy.md).

Software-verified:

- [x] Template and Machine record schemas
- [x] Template catalogue with sealed Golden Image digest pins
- [x] user-owned Machine registry (intent and membership only)
- [x] Machine materialization and Machine to VM-spec projection
- [x] network identity separated from GPU handoff policy
- [x] root-owned managed GPU policy surface merged by the qemu hook
- [x] GPU handoff ceiling enforced by factory, planner and root tool
- [x] product Machine CLI and registry-backed inventory
- [x] root GPU-policy observability and remedies
- [x] Diagnostics lists libvirt domains outside the product inventory
- [x] the qemu hook refuses an unmapped domain that carries PCI passthrough
- [x] complete discovered contract suite green

Open before C10 can be used as a product path:

- [ ] a captured, generalized and sealed workstation Golden Image; the
      upstream `arch` cloud image is a base, not the workstation
- [ ] the first published Template pinned to that Golden Image
- [ ] a Machine created, projected, defined and started on Nitro, with its
      managed `domains.d` policy written and verified by the hook
- [ ] physical proof that the hook refuses an unmapped domain with PCI
      passthrough (software-verified in `tests/hook.bats`)
- [ ] physical acceptance of the product-only Machines workspace and the
      Diagnostics outside-domain list

## Guest Workspace Shell

Reference: [`guest-workspace-shell.md`](guest-workspace-shell.md).

The workstation guest gets its own desktop before it is sealed into the first
Golden Image, so every Machine made from it starts with it.

Software-verified:

- [x] Machine → Desk → Project model; Desk n owns workspaces n*10+1..n*10+9
- [x] `hyperlab-desk` helper with validated, never half-applied configuration
- [x] Quickshell shell: context and status islands, dock, Desks overview,
      launcher, OSD; every readout from a real guest source
- [x] `hyperlab-workstation` theme, palette followed live, generated wallpaper
- [x] hyprlock restyled; the lock stays outside the shell
- [x] every key works without the shell; a failing shell falls back to Waybar
- [x] offscreen runtime contract over the real QML with Quickshell stand-ins

Open:

- [ ] physical acceptance on `arch-dev-vfio`: shell start, keys, overview,
      launcher, lock, theme change, Waybar fallback
- [ ] Hyprland layer blur behind the islands

## Next milestone — Golden Image capture

The Image Factory prepares and validates upstream images. It cannot yet turn a
finished workstation guest into a reusable Golden Image. The next milestone
adds that path:

1. capture a shut-off workstation disk into the image store;
2. generalize it: machine identity, SSH host keys, cloud-init state, logs,
   shell history and any personal data removed, with a reviewed checklist;
3. seal it with a digest and a manifest that records its source guest and the
   commits that built it;
4. publish the first Template against it;
5. prove permanent and disposable Machines from it on Nitro.

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

<!-- HYPERLAB_QUICKSHELL_READONLY_CORE_V1 -->
### HyperLab Shell Phase 2B — read-only core

- [x] physical Quickshell per-screen panel creation
- [x] 37px exclusive-zone acceptance on Hyprland
- [x] event-driven trust transport
- [x] slow RAM/GPU/VM status surface
- [x] native Quickshell clock
- [x] compositor-neutral shared QML boundary
- [x] compositor-neutral workspace data adapter
- [x] theme semantic palette migration
- [x] host telemetry migration
- [x] reviewed interactive HyperLab controls
  - [x] keyboard / wallpaper / Controls session surface
  - [x] HyperLab / trust / VM / audio action routing
- [x] command surface, system panel and OSD in the shared shell
- [x] fixed IPC receivers for compositor keybindings
- [x] quiet idle desktop: the permanently visible cockpit is retired
- [x] native product workspace: Machines, Control Center and Diagnostics in one
      ordinary compositor-managed window
- [x] drawer / Control Center migration: no detached HyperLab route is bound in
      the preferred session
- [x] typed machine operation boundary with backend-derived capabilities
- [x] one shared target-bound confirmation for destructive operations
- [x] HyperLab Platform identity: one circular symbol from rail to lock
- [x] physical screenshot and interaction acceptance on Nitro
- [x] reviewed focused-surface provenance resolver wired live into the shell
      (software-verified)
- [x] physical Nitro acceptance of live focused-surface provenance
- [ ] reviewed desktop-entry catalogue and app-launch bridge (Rofi remains a
      transitional application launcher)
- [ ] reviewed focused-window targeting (fullscreen/opacity stay compositor
      shortcuts; the shell cannot request them)
- [ ] native Create, Networks and Nitro hardware views behind their feature gates
- [ ] visual theme and wallpaper browsers (needs reviewed per-theme palette export)
- [ ] shell-owned notifications (mako remains the reviewed daemon)
- [ ] complete keybinding cheatsheet surface
- [ ] Sway native parity acceptance (Sway remains the recovery session)
