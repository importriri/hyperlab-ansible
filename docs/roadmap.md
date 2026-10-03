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

## Security rules every milestone keeps

These hold for every item below. A change that weakens one is a design
change, reviewed on its own, never a side effect.

1. **The host decides, the guest never claims.** Trust, provenance and GPU
   state are shown only by host-owned surfaces. Nothing a guest paints or
   reports raises its own trust.
2. **Fail closed.** A missing, unreadable, redirected or duplicated policy
   input is a refusal, never a default.
3. **Nothing is adopted implicitly.** A libvirt domain does not become a
   Machine, and a disk does not become a Golden Image, because it exists. Each
   step is an explicit, recorded operator action.
4. **Lower, never raise.** Network identity and the GPU handoff ladder can only
   lower a class within a boot; raising one takes a host reboot.
5. **Cross-boundary data moves only on request.** Clipboard, files and devices
   cross between host and guests, or between guests, only through an explicit,
   one-shot, host-mediated action aimed at one named target.
6. **Least plane.** No guest gets a channel into the hypervisor beyond what its
   Template needs: no shared clipboard, no guest-agent command execution, no
   USB or audio input unless requested.
7. **Evidence before claims.** Software-verified and hardware-accepted are
   separate checkboxes; a milestone closes only with both.

## Platform checklist

The milestones run in dependency order. Each one is software-verified first,
then accepted on Nitro; Predator replays the frozen result.

### 1. Finish `arch-dev-vfio` (the reference workstation)

- [ ] pre-login display recovery and input isolation accepted
- [ ] physical audio proof
- [ ] idempotence: a second run of `guest-arch-dev-vfio.yml` reports
      `changed=0`
- [x] guest package installs run as one full Arch transaction
      (software-verified)
- [ ] Guest Workspace Shell accepted on the guest (see below)
- [ ] extract reusable workstation behaviour from the VFIO-specific path;
      finish `arch-dev` and `arch-minimal-ssh` on the same roles

### 2. Guest Workspace Shell

Details and status: [Guest Workspace Shell](#guest-workspace-shell).

- [ ] physical acceptance; layer blur behind the islands
- [ ] `hypridle` DPMS through the reviewed Lua dispatcher form
- [ ] project restore: a project reopens the windows it had, not only its
      launch commands
- [ ] keybinding cheatsheet surface in the guest (`ALT+/`)
- [ ] shell-owned notifications with a do-not-disturb mode per Desk
- [ ] the same shell on every workstation Template, not only `arch-dev-vfio`

### 3. Golden Image Workbench and capture (M12, first half)

- [ ] **Workbench** in Machines: an operator explicitly adopts an existing
      domain as a Golden Image candidate; it can be started, stopped, opened
      and sealed from the shell, and it is never a product Machine
- [ ] capture a shut-off workstation disk into the image store
- [ ] generalize with a reviewed checklist: machine-id, SSH host keys,
      cloud-init state, logs, shell history, browser profiles, keyrings,
      tokens and any personal data removed, and the result scanned for leftovers
- [ ] seal: digest, manifest with source guest, build commits and package
      list; the candidate leaves the Workbench once sealed
- [ ] a sealed image is read-only and verified by digest at every use

### 4. Templates

Every Template pins one Golden Image digest, one network identity and the GPU
profiles it allows; the ceiling rule applies.

| Template | Network | GPU | Purpose |
|---|---|---|---|
| `workstation-dev` | dev | dev | everyday development, the Workspace Shell |
| `gaming-clean` | clean | clean | official stores with real accounts: Steam, Epic, GOG; nothing else installed |
| `gaming-dirty` | dirty | dirty | modded games and third-party launchers; never the store accounts |
| `gaming-offline` | lab (no internet) | lab | untrusted or cracked software, offline |
| `browser-disposable` | dirty | none | throwaway browsing, reset on shutdown |
| `services` | services | per Template | appliances such as Jellyfin |

Store accounts live only in `gaming-clean`. A modded or offline game never
shares a disk, a network or a Machine with an account that owns purchases.
Within one boot the GPU goes clean → dev → dirty → lab, never back up.

- [ ] first published Template, `workstation-dev`, pinned to the sealed image
- [x] Arch rice profiles `dev`, `gaming-clean` and `gaming-dirty` on one set
      of roles, with their playbooks and VM specs (software-verified)
- [ ] `gaming-clean`, `gaming-dirty` and `gaming-offline` Templates for Linux
      and Windows, pinned to sealed images of those profiles
- [ ] `browser-disposable` with reset on shutdown
- [ ] Template review gate: a Template cannot request a network, GPU profile
      or device its class forbids

### 5. C10 Machine Factory to product

Details: [C10 — Machine Factory](#c10--machine-factory).

- [ ] permanent and disposable Machines created, projected, defined and
      started on Nitro from a Template
- [ ] disposable Machines discard their writable layer on shutdown
- [ ] Create view in the shell behind its feature gate

### 6. Controlled data crossing

- [ ] host → guest clipboard: copy on the host, a dedicated host key, pick
      the target Machine, the text is delivered once and nowhere else
- [ ] guest → host and guest → guest clipboard through the same host action;
      moving data from a lower trust class to a higher one asks for
      confirmation and is logged
- [ ] file transfer into a guest through a host-mediated drop folder, one file
      set and one target per action
- [ ] USB passthrough per Machine through an explicit host action, with a
      host-side device allowlist
- [ ] microphone and camera off by default; on only per Machine and per
      session, with a host indicator while active
- [ ] host keybinding cheatsheet that includes the crossing keys

### 7. Snapshots, backups and recovery (M12, second half)

- [ ] snapshots for permanent Machines, from the shell, with retention
- [ ] encrypted backups of Machines, the Machine registry and host
      configuration, to a target that the guests cannot reach
- [ ] restore drill: a Machine restored onto a clean host from a backup
- [ ] Golden Image and Template catalogue backed up with their digests

### 8. VM lifecycle and Control Center (M10, M11)

- [ ] VM lifecycle and Control Center operational and recovery surfaces
      complete (M10 domain manager and M11 shell are implemented; their live
      gates remain)
- [ ] the drawer placement visual recheck on Nitro
- [ ] reviewed desktop-entry catalogue and app-launch bridge on the host

### 9. Network security topology

- [ ] frozen allowed-flow matrix between clean, dev, dirty, lab and services
- [ ] `lab` enforced offline at the host, not only by guest configuration
- [ ] per-network DNS, with no network able to query another's resolver
- [ ] optional per-network VPN egress with a kill switch: if the tunnel
      drops, that network has no internet
- [ ] host firewall default deny for guest-to-host traffic, with the reviewed
      exceptions listed

### 10. Hypervisor hardening

- [ ] sVirt/AppArmor confinement of every QEMU process verified, not assumed
- [ ] QEMU guest agent restricted to the commands HyperLab uses; no guest
      command execution
- [ ] SPICE channels a Template does not need disabled (clipboard, file
      transfer, USB redirection)
- [ ] VM disks at rest on the encrypted host volume only, with swap and
      temporary files of guests never on unencrypted storage
- [ ] firmware updates through `fwupd`, with a recorded result on Nitro
- [ ] host USB device policy so a new device is not trusted automatically

### 11. Visual provenance and trust model

- [ ] finish the host-owned visual provenance and trust model: every focused
      surface named by the host, including fullscreen guests
- [ ] the host frame visible around a Looking Glass window at all times

### 12. Security plane

- [ ] endpoint HIDS with measured overhead and no hypervisor remote-command
      plane
- [ ] passive NIDS that is never an inline routing dependency
- [ ] HyperLab Security Plane correlating endpoint and network evidence, shown
      in Diagnostics

### 13. Performance and gaming tuning

Measured with the complete security plane active.

- [ ] CPU pinning and isolation profiles for gaming Templates
- [ ] huge pages and memory policy for GPU guests
- [ ] latency and frame-time benchmarks recorded per Template

### 14. Release qualification and the Doppiari release

- [ ] release qualification: idempotence, reboot, cold start, recovery and
      hardware gates
- [ ] threat model document: what HyperLab protects against and what it does
      not; no claim of Qubes OS security properties
- [ ] `SECURITY.md` and private vulnerability reporting enabled before the
      release
- [ ] licence and authorship reviewed for publication under Doppiari
- [ ] wallpaper and polish, screenshots, video and release documentation
- [ ] sanitized Nitro evidence sealed with the exact public `main` commits
      exercised on hardware; Predator replayed and published separately

### Later

- **M13 — seamless guest applications:** future work, and never described as
  providing Qubes OS security properties.
- per-Desk focus modes and time tracking in the guest shell
- Sway native parity acceptance (Sway remains the recovery session)

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

## Decisions and closed milestones

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
