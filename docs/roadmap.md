# HyperLab roadmap

Software verification and hardware evidence are separate. CI can prove that a
repository contract holds; only a named machine can prove that the hardware path
works.

A checked box that reports a hardware observation names its evidence in one
of two forms: `evidence:` and a link to an acceptance receipt in `docs/`, or
the words *operator-observed, unpublished* when the operator saw the result
and no sanitized record of it is published. Either form keeps the date and
the scope of that one observation. Neither is a replay of frozen release
commits or a full-pipeline acceptance; milestone 14 qualifies those.
`tests/docs_contract.py` checks that every such box carries one of the two
forms. It cannot check that the observation happened, or that a receipt is
enough for the claim.

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

## v1 scope and evidence status

v1 keeps milestones 1, 4 (with the two SSH server Templates, `server-debian`
and `server-fedora`), 5, 5b and the Showcase. Each part below is stated at
the level its evidence reaches today. A design, the name of a checked-in test
or work that is not on `main` does not raise it.

- **Reference workstation (1):** the repeated `changed=0` runs and the Guest
  Workspace Shell on `arch-dev-vfio` are operator-observed, unpublished
  (Nitro, 2026-10-03). The pre-login and input gate and the physical audio
  proof are open.
- **Server Templates (4):** `server-fedora` is ready on the sealed upstream
  Fedora 44 image. `server-debian` is a draft until `debian-server`, the
  Debian image with QEMU Guest Agent, is prepared and sealed. A ready
  Template is not an SSH observation: neither server's SSH observation is
  recorded, and both stay open.
- **Plan and Intent (5):** software-verified. `create-plan` reports what the
  factory allows, and one staged `machine create --project` publishes the
  Machine record only after its projection is written
  ([ADR 0017](adr/0017-shell-machine-creation.md) and
  [ADR 0053](adr/0053-withdraw-machine-intent.md), both proposed).
- **Create view (5):** implemented in the shell and software-verified
  offscreen. No creation from the shell has been accepted on hardware.
- **Provisioning (5):** the runner, the check of the whole plan before the
  first step and the removal of the password hash file are software-verified
  against inert fixture playbooks. That validation and cleanup end at the
  limits ADR 0017 lists: a writer of the checkout after the checks, SIGKILL.
  A real unit stop, a real `ansible-playbook` run and a Machine provisioned
  from the shell are not observed.
- **Disposable Machines (5):** the libvirt transient disk that discards the
  writes at every stop is software-verified
  ([ADR 0018](adr/0018-disposable-discards-on-stop.md), proposed). Access at
  every later boot is not closed: the managed start does not restrict the
  agent again or re-pin the host key. No disposable Machine has been proven
  on hardware.
- **GPU lease (5b):** proposed in [ADR 0019](adr/0019-gpu-lease.md), not
  decided and not built. What it builds on, the shared definition, the
  ladder and GPU-capable services, is software-verified.
- **Showcase:** the storyboard is written and the read-only demo script is
  software-verified; the lease shot waits for ADR 0019, and the recording and
  its privacy review are open.
- **Qualification gap:** the checked-in release order of milestone 14
  (`release/acceptance.v2.yml`) was written before this scope. It has no
  gate for a Machine created from the shell, the disposable discard, the two
  SSH servers, the GPU lease or the Showcase take, so a campaign sealed on it
  does not qualify those parts. What replaces it is not decided yet.

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

## Machine catalogue

Every VM the platform defines today, where it stands and what it waits on. In
the product model each of them becomes a Template over a sealed Golden Image;
until then the VM specs below are the reviewed definitions.

| VM spec | OS image (manifest) | Network | GPU class | Lifecycle | Today | Next |
|---|---|---|---|---|---|---|
| `arch-dev-vfio` | arch (sealed upstream base) | dev | dev | permanent | NVIDIA, kvmfr, Looking Glass, Workspace Shell accepted on Nitro | pre-login and input gate, audio proof, seal as `workstation-dev` |
| `arch-dev` | arch | dev | none | permanent | Nitro lifecycle gate passed; shared workstation roles | capture as `arch-dev-standard` for `workstation-dev-standard` |
| `arch-gaming-clean` | arch | clean | clean | permanent | profile, playbook, spec (software) | build from the sealed workstation image |
| `arch-gaming-dirty` | arch | dirty | dirty | permanent | profile, playbook, spec (software) | build from the sealed workstation image |
| `debian-dev` | debian-server (not built) | dev | none | permanent | spec only | capture `debian-server`, first boot on the shared roles |
| `fedora-dev` | fedora (sealed upstream base) | dev | none | permanent | spec only | first boot on the shared roles |
| `parrot-disposable` | parrot (not built) | lab | none | disposable | spec only | prepare and seal the Parrot image, prove reset |
| `svc-jellyfin` | debian-server (not built) | services | optional | permanent | service contracts green | service and recovery hardware gates |
| `win11clean-valley` | win11clean (not built) | clean | clean | permanent | Windows workshop flow exists | seal the master, VFIO benchmark |
| `win11dirty-disposable` | win11dirty (not built) | dirty | dirty | disposable | Windows workshop flow exists | seal the master, prove reset |
| `arch-minimal-ssh` | arch | dev | none | test fixture | superseded by the `server-arch` Template (`srv-01`) | retire the fixture domain when no gate uses it |
| future `local-ai` | to decide | services | GPU-capable | permanent | requirement only | needs the GPU lease model below |
| future `gaming-offline` | to decide | lab | lab | permanent | requirement only | Template after the gaming images |

## Platform checklist

The milestones run in dependency order. Each one is software-verified first,
then accepted on Nitro; Predator replays the frozen result.

### 0. Architecture decisions before the product surfaces

- [x] canonical ADR: Image Factory, Golden Image, Template and Machine
      lifecycle; empty Machines on a fresh install; Machine, Desk and Project
      ([ADR 0021](adr/0021-product-lifecycle.md))
- [x] ADR recorded: network trust versus GPU transition policy and
      GPU-capable SERVICES ([ADR 0022](adr/0022-network-trust-and-gpu-policy.md),
      proposed; the policy it records is built and software-verified, see 5b
      and C10)
- [x] the boot-scoped GPU lease recorded as a proposal
      ([ADR 0019](adr/0019-gpu-lease.md), proposed; not decided and not
      built, see 5b)
- [x] ADR: no separate PLAY identity; `gaming-clean`, `gaming-dirty` and
      `gaming-offline` on clean, dirty and lab
      ([ADR 0023](adr/0023-gaming-identities.md), accepted)
- [ ] an independent architecture review that actually reads the
      repository (the earlier attempt could not open it and does not count)
- [x] the reviewer's package: verification, repository map, trust
      boundaries, proposed decisions and the maintainer's questions
      ([`independent-review-package.md`](independent-review-package.md))

### 1. Finish `arch-dev-vfio` (the reference workstation)

- [ ] pre-login display recovery and input isolation accepted
- [ ] physical audio proof
- [x] idempotence: repeated runs of `guest-arch-dev-vfio.yml` report
      `changed=0` (Nitro, 2026-10-03; operator-observed, unpublished; an
      earlier second pass with `changed=0`, Nitro, 2026-08-31, has a
      receipt, evidence: [`nitro-arch-dev-vfio-acceptance-2026-08-31.md`](nitro-arch-dev-vfio-acceptance-2026-08-31.md))
- [x] guest package installs run as one full Arch transaction
      (software-verified)
- [x] Guest Workspace Shell on the guest: Desks, tiling, theme, identity
      wallpaper and key sheet (Nitro, 2026-10-03; operator-observed,
      unpublished)
- [x] the workstation behaviour lives in the shared roles: `arch-dev` is
      the shared roles plus `dev_ide`, and the accelerated playbooks add only
      the GPU, its telemetry and Looking Glass through a closed set of
      variables; `arch-minimal-ssh` is superseded by the `server-arch`
      Template (software-verified)

### 2. Guest Workspace Shell

Details and status: [Guest Workspace Shell](#guest-workspace-shell).

- [x] physical acceptance of the shell, Desk keys, tiling and theme
      (Nitro, 2026-10-03; operator-observed, unpublished)
- [ ] physical acceptance of the launcher, Desks overview, lock and the
      Waybar fallback, one by one
- [x] layer blur behind the islands and panels, through the reviewed Lua
      `hl.layer_rule` form (software-verified)
- [x] `hypridle` DPMS through the reviewed Lua dispatcher form: the host
      adapter only, checked against the Hyprland 0.56.2 source; guests never
      touch display power (software-verified)
- [x] project restore: a project reopens the applications it had, from
      their desktop entries, not only its launch commands; desktop ids only,
      never process arguments (software-verified)
- [x] keybinding sheet in the guest (`ALT+H`), from one `keys.json` that the
      contract checks against the bound keys
- [x] a reviewed Lua form for a gradient active border: the `HL.Gradient`
      table of Hyprland 0.56, executed per theme by the contract
      (software-verified)
- [x] a do-not-disturb mode per Desk, through mako's documented quiet mode
      (software-verified)
- [ ] shell-owned notifications: who owns them is
      [ADR 0027](adr/0027-guest-notification-owner.md), proposed
- [x] per-Desk focus (a quiet Desk for a set time) and opt-in, local time
      tracking per Desk and slot, in the Desk helper (software-verified)
- [x] the status island shows a quiet Desk and a running focus, from the
      helper (software-verified, offscreen runtime contract)
- [x] the time report in the shell: today's time on each Desk card of the
      overview, only while tracking is on (software-verified)
- [x] the same shell on every workstation Template, not only `arch-dev-vfio`:
      the role's default, applied by every workstation Template's profile
      playbook and overridden by none (software-verified)

### 3. Golden Image Workbench and capture (M12, first half)

Decision: [`adr/0015-golden-image-capture.md`](adr/0015-golden-image-capture.md).
Procedure: [`golden-image-workbench.md`](golden-image-workbench.md).

- [x] explicit adoption into a root-owned Workbench registry, read without
      privilege by `hyperlabctl workbench list` (software-verified)
- [x] capture a shut-off disk as a flat copy outside the store; the source is
      only read (software-verified)
- [x] generalize the copy offline with `virt-sysprep`, every user account and
      home removed, and refuse on any leftover the scan finds
      (software-verified)
- [x] digest and a local-import manifest for the existing image factory
      (software-verified)
- [x] the first real seal of `arch-dev-vfio` on Nitro, imported and validated
      as `arch-dev-20261003` (Nitro-verified: operator-observed, unpublished;
      the manifest `images/arch-dev-20261003.yml` records the digest)
- [x] **Workbench** section in the shell: start, stop, open and seal a
      candidate, never shown as a product Machine; a product Machine is
      refused at adoption and seal (software-verified)
- [x] build commits and the package list in the image manifest
      ([ADR 0028](adr/0028-image-build-provenance.md), software-verified)
- [x] a sealed image is read-only and verified by digest at every use:
      root:qemu 0440 in the store; a disposable Machine verifies it on every
      operation that opens its overlay, a permanent one is an independent
      clone of a verified base, a derivation checks it first
      (`tests/sealed_base_use_contract.py`, software-verified)

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

The catalogue is a matrix of ready combinations, each a few clicks from a
Machine. Every Template still pins one sealed image:

| Kind | Arch | Debian | Fedora | GPU | Desktop |
|---|---|---|---|---|---|
| server (SSH only) | `server-arch` | `server-debian` | `server-fedora` | no | no |
| workstation | `workstation-dev`, `workstation-dev-standard` | later | later | yes / no | Workspace Shell |
| gaming | `gaming-clean`, `gaming-dirty` | | | yes | Workspace Shell |
| services | `svc-*` | `svc-*` | | per Template | no |
| disposable | `browser-disposable` | | | no | minimal |

`server-arch` and `server-fedora` need no Workbench capture: they use the
sealed upstream cloud images with cloud-init. `server-debian` does: the
upstream Debian image has no QEMU Guest Agent, so it waits, as a draft, for
the `debian-server` capture. At creation the operator chooses name, network
and resources (profile or custom RAM, vCPUs and disk) within what the
Template allows.

Store accounts live only in `gaming-clean`. A modded or offline game never
shares a disk, a network or a Machine with an account that owns purchases.
Within one boot the GPU goes clean → dev → dirty → lab, never back up.

- [x] first published Template, `workstation-dev`, pinned to the sealed image
      `arch-dev-20261003` (software-verified)
- [x] first Machine, `dev-01`, created from `workstation-dev` on Nitro, the
      rice applied by the dev profile playbook, second pass `changed=0`,
      Looking Glass, Desks, host provenance and trust colours (Nitro-verified:
      operator-observed, unpublished)
- [x] `ALT+SHIFT+W` in the guest changes only the wallpaper, with a short
      fade, instead of reloading the session (software-verified)
- [x] Arch rice profiles `dev`, `gaming-clean` and `gaming-dirty` on one set
      of roles, with their playbooks and VM specs (software-verified)
- [x] `server-arch`: SSH-only Machines from the sealed upstream Arch image,
      standard device, dev, services or lab network (software-verified)
- [x] `srv-01` from `server-arch` created and reached over SSH on Nitro
      (Nitro-verified: operator-observed, unpublished)
- [x] Debian 13 and Fedora 44 cloud images pinned from downloads verified on
      Nitro against the official checksums; `server-debian` and
      `server-fedora` published as drafts (recorded 2026-10-04;
      operator-observed, unpublished)
- [x] Debian 13 and Fedora 44 images prepared, validated and sealed on
      Nitro (recorded 2026-10-04; operator-observed, unpublished); at that
      point both server Templates were marked ready. Only `server-fedora`
      is ready now: the next item returned `server-debian` to a draft
- [x] a manifest's QEMU Guest Agent claim is checked inside the image,
      read-only, before it is sealed or validated; the upstream Debian
      genericcloud has no agent, so `server-debian` is a draft again
      (software-verified)
- [ ] `debian-server`: the Debian cloud image captured through the
      Workbench with QEMU Guest Agent, generalized, scanned and sealed;
      `server-debian` ready on it
- [x] the Workbench derives an image offline from a sealed base with a
      reviewed package list, scans apt and dpkg residues and requires the
      agent to start by itself ([ADR 0026](adr/0026-offline-derived-images.md),
      software-verified)
- [ ] a Machine from `server-debian` and one from `server-fedora` reached
      over SSH on Nitro
- [x] every new Linux Machine, server or workstation, starts in the host's
      time zone from cloud-init (software-verified)
- [x] the Machine account is in its distribution's polkit administrator
      group (`wheel`, or `sudo` on Debian), so polkit never asks for root
      (software-verified)
- [ ] `workstation-dev-standard` from a Workbench capture of `arch-dev`
- [x] its draft Template and the placeholder manifest that reserves
      `arch-dev-standard`; the Workbench replaces only such a placeholder
      (software-verified)
- [x] Linux `gaming-clean` and `gaming-dirty` draft Templates, with the
      placeholder manifests that reserve their Workbench captures and their
      reviewed profile playbooks (software-verified)
- [ ] `gaming-clean` and `gaming-dirty` ready on sealed captures of
      `arch-gaming-clean` and `arch-gaming-dirty`
- [ ] `gaming-offline` (needs its own rice profile) and the Windows gaming
      Templates, pinned to sealed images of those profiles
- [x] `browser-disposable` draft Template (class disposable, dirty network,
      transient disk) and the `arch-browser` placeholder (software-verified)
- [ ] `browser-disposable` ready: its image built as
      [ADR 0030](adr/0030-disposable-browser-image.md) decides, sealed, and a
      Machine reset on shutdown proven on Nitro
- [ ] Debian, Fedora and Parrot images prepared and sealed; `debian-dev`,
      `fedora-dev` and `parrot-disposable` proven from them
- [ ] Windows masters sealed through the workshop; `win11clean` and
      `win11dirty` Templates
- [x] `svc-jellyfin` draft Template of the services class (software-verified)
- [ ] `svc-jellyfin` ready: created from the shell as
      [ADR 0031](adr/0031-service-appliance-templates.md) decides, on a sealed
      `debian-server`
- [x] Template review gate: a Template cannot request a network, GPU profile
      or device its class forbids ([ADR 0029](adr/0029-template-review-gate.md),
      software-verified)

### 5. C10 Machine Factory to product

Details: [C10 — Machine Factory](#c10--machine-factory).

- [ ] permanent and disposable Machines created, projected, defined and
      started on Nitro from a Template
- [x] disposable Machines discard their writable layer on every stop: a
      libvirt transient disk over the lifecycle overlay; server Templates
      offer them ([ADR 0018](adr/0018-disposable-discards-on-stop.md),
      proposed; software-verified)
- [ ] a disposable Machine closed again at every later boot: the agent
      allowlist restored and the host key re-pinned after each start (not
      built: the managed start runs neither step, ADR 0018 Limits)
- [ ] a disposable Machine proven on Nitro: a file written in the guest is
      gone after a stop and start, and no temporary overlay is left behind
- [x] Create view in the shell: Template, name, network and resources
      within the Template's limits, provisioned as one durable operation;
      password and become prompt only in the operation window
      ([ADR 0017](adr/0017-shell-machine-creation.md), proposed;
      software-verified)
  - [x] a refused creation leaves no record: one staged `machine create
        --project` under the registry lock, a failure after the record's
        publication undone record first, and the manual `machine withdraw`
        held by digest, projection, a readable spec and the libvirt domain
        list ([ADR 0053](adr/0053-withdraw-machine-intent.md), proposed,
        software-verified)
  - [x] provisioning prepared for Nitro: the runner accepts exactly
        `privatestack-machine-provision NAME` on NAME's own projection,
        `provision-steps` refuses a spec that is not the record's
        projection with its scalar types, the whole plan, its profile
        bound to the record's Template, and its playbook files are checked
        before the first step, and the hash file is removed after success,
        failure, SIGINT, SIGTERM and SIGHUP, also when the runner is
        stopped while a playbook is slow to end, ignores SIGTERM or is
        still being started, only after that playbook is stopped and reaped
        ([ADR 0017](adr/0017-shell-machine-creation.md), proposed;
        software-verified within the limits that ADR lists)
- [ ] Create view accepted on Nitro: a server and a workstation created
      from the shell

### 5b. GPU as a capability and a boot-scoped lease

- [x] several managed VFIO domains may name the GPU in their definitions;
      only the running one owns it, checked under the GPU lock at start
      ([ADR 0016](adr/0016-gpu-shared-definition-running-lease.md),
      software-verified)
- [ ] a Machine declares `gpu_capable`; owning the GPU is a host-owned lease
      for one run, so a dev Machine can start without the GPU and restart
      with it for Blender or CUDA
- [ ] the lease decided: [ADR 0019](adr/0019-gpu-lease.md) is proposed and
      nothing of it is built (it waits for an image with a session on both
      shapes, a hardware test of define-then-start and the choice of
      Templates; it comes after `workstation-dev-standard` and the Create
      view accepted on hardware, both open)
- [x] SERVICES Machines may be GPU-capable through a reviewed handoff
      profile; the static rule that excludes them is replaced: a service spec
      names `gpu_handoff_profile` (null by default) and its VM spec must match
      it; the services Template class allows VFIO (software-verified)
- [ ] `local-ai` service Machine (local inference) on that model
- [x] the ladder still guarantees that a lower-trust GPU use never precedes a
      higher-trust use in the same host boot: a services Machine's GPU use is
      a rung like any other, so a cleaner domain after it is refused and it
      is refused after a dirtier use (`tests/hook.bats`, software-verified)

### Showcase: from Golden Image to running Machine

Once 5 and 5b are done on Nitro, a short public demonstration of the
platform, recorded on the host:

- [x] storyboard of 60 to 90 seconds: create a Machine from
      `workstation-dev` in the shell, first boot with the rice, the GPU lease,
      Looking Glass, the Desks, the host frame showing trust and network
      ([`showcase.md`](showcase.md); the lease shot waits for ADR 0019)
- [x] a demo script that runs the steps in order, so the take is clean
      (`tools/showcase/demo.sh`, read-only; it prints a generic privacy
      checklist, never this host's names, paths or addresses, and a failing
      tool only as a fixed reason; software-verified with `sh` as Bash and
      as dash, the CI runner's shell)
- [ ] recording on the host, editing, captions
- [ ] review before publishing: no host name, user name, address or private
      path on screen

### 6. Controlled data crossing

- [x] host → guest clipboard: copy on the host, `SUPER + SHIFT + V`, pick
      the target Machine, the text is delivered once and nowhere else
      ([ADR 0020](adr/0020-host-to-guest-clipboard.md), software-verified)
- [ ] host → guest clipboard accepted on Nitro into a workstation Machine
- [ ] guest → host and guest → guest clipboard through the same host action;
      moving data from a lower trust class to a higher one asks for
      confirmation and is logged ([ADR 0032](adr/0032-guest-clipboard-out.md),
      proposed)
- [ ] file transfer into a guest through a host-mediated drop folder, one file
      set and one target per action ([ADR 0033](adr/0033-file-transfer-drop-folder.md),
      proposed)
- [ ] USB passthrough per Machine through an explicit host action, with a
      host-side device allowlist ([ADR 0034](adr/0034-usb-passthrough.md),
      proposed; no USB device reaches a guest today, `tests/media_input_contract.py`)
- [ ] microphone and camera off by default; on only per Machine and per
      session, with a host indicator while active
      ([ADR 0035](adr/0035-microphone-and-camera.md), proposed); the Looking
      Glass client already denies the microphone
- [x] a PDF rebuilt from its pixels only: the stream reader trusts nothing,
      and a PDF carrying JavaScript, an embedded file, a link and a form comes
      back with the same picture and none of them
      ([ADR 0051](adr/0051-disposable-viewer-and-safe-documents.md), proposed;
      `roles/guest_safe_documents`, `tests/safe_pdf_contract.py`,
      software-verified)
- [ ] the disposable viewer Machine without a network, the host relay and
      `hyperlab-open-disposable` (ADR 0051 steps 2–4)
- [ ] the same seen in the lab host and on Nitro (ADR 0051 hardware test)
- [x] host keybinding cheatsheet that includes the crossing keys:
      `SUPER + F1`, checked against the bindings (software-verified)

### 7. Snapshots, backups and recovery (M12, second half)

Decision pending: [ADR 0036](adr/0036-machine-snapshots-and-backups.md) (proposed).

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
- [x] reviewed desktop-entry catalogue and app-launch bridge on the host:
      the launcher's Applications group starts only catalogue entries the
      shell action bridge resolves to root-owned desktop files
      (software-verified; also the shell checklist item below)

### 8a. Test infrastructure

- [x] a nested lab host for host-level tests, made without privilege and
      touching only `hl-lab-*` resources, with its own network in the flow
      matrix ([ADR 0046](adr/0046-nested-lab-host.md), proposed;
      `tools/lab/hl_lab.py`, `tests/hl_lab_contract.py`; software-verified)
- [x] a host profile without GPU passthrough, chosen only by name, so the
      lab host can run the host roles; `auto` still selects `nitro-3060` on
      the Nitro's IDs and refuses an unknown computer
      ([ADR 0052](adr/0052-host-without-gpu-passthrough.md), proposed;
      `roles/hardware_probe/tasks/select.yml`, `tests/render.yml`,
      software-verified)
- [ ] the lab host started on Nitro once the guest isolation with the
      fail-closed catch-all is loaded, installed with `arch-bootstrap`, and
      the host playbooks applied inside

### 8b. Reliability

- [x] Looking Glass stream health in the host shell: the guest agent's
      answer, the sender and the stream state on the selected Machine's pane,
      and a capture restart (sender and portals, the guest keeps running)
      ([ADR 0045](adr/0045-looking-glass-stream-health.md), proposed;
      `hyperlabctl looking-glass`, `tools/hyperlabctl/tests/test_looking_glass.py`,
      the runtime contract's stream-health scenario; software-verified)
- [ ] the same accepted on Nitro with the rebuilt sender
- [x] no host suspend while a VFIO Machine holds the GPU: a libvirt hook
      holds a systemd block inhibitor (sleep, idle, suspend and hibernate
      keys, lid) for each running domain with a PCI hostdev
      (`roles/host_sleep_guard`, `tests/host_sleep_guard_contract.py`,
      software-verified)
- [ ] the same seen on Nitro: Suspend from the shell refused while `dev-01`
      holds the GPU, accepted after it stops
- [x] "collect diagnostics": one private archive of a Machine's host and
      guest logs, redacted (keys, passwords, hashes, tokens, emails), with a
      manifest of what was and was not collected (`hyperlabctl diagnostics
      collect`, `tools/hyperlabctl/tests/test_diagnostics.py`,
      software-verified)
- [ ] the same as an action on the Machine pane, and run once on Nitro

### 9. Network security topology

- [x] frozen allowed-flow matrix between clean, dev, dirty, lab and services
      ([`network-flows.md`](network-flows.md),
      `tests/network_flow_matrix_contract.py`, software-verified)
- [x] `lab` enforced offline at the host, not only by guest configuration:
      no libvirt forward and a host forward drop in both directions
      (software-verified)
- [ ] the three above and the guest-to-host deny applied and observed on
      Nitro
- [x] per-network DNS, with no network able to query another's resolver
      (software-verified)
- [ ] optional per-network VPN egress with a kill switch: if the tunnel
      drops, that network has no internet
- [x] host firewall default deny for guest-to-host traffic, with the reviewed
      exceptions listed: replies, DHCP, DNS to the own gateway
      ([`network-flows.md`](network-flows.md), software-verified)

### 10. Hypervisor hardening

- [ ] sVirt/AppArmor confinement of every QEMU process verified, not assumed:
      verified absent on Nitro (DAC only, one QEMU user for every Machine;
      [`problems/qemu-processes-share-one-identity.md`](../problems/qemu-processes-share-one-identity.md));
      [ADR 0037](adr/0037-qemu-process-confinement.md) accepted, option A2:
      per-Machine DAC identities plus one AppArmor profile for QEMU
- [x] the shared QEMU AppArmor profile (`roles/qemu_apparmor`,
      `tests/qemu_apparmor_contract.py`; compiled by `apparmor_parser`,
      software-verified), starting in complain mode
- [x] per-Machine QEMU identities (ADR 0037 part 2a), behind
      `hyperlab_qemu_identity_mode`, off
      (`tests/qemu_identity_contract.py`, software-verified)
- [x] sealed bases with their own reader group, disposable Machines, and
      the move of existing Machines while shut off (ADR 0037 part 2b,
      same switch, software-verified)
- [ ] both proved in the lab host, then on Nitro, and the profile enforced
- [x] the kernel side of AppArmor prepared: a VFIO boot entry with AppArmor in
      `lsm=`, not the default (`tests/apparmor_boot_contract.py`,
      software-verified)
- [ ] that entry booted and proved on Nitro, then made the default
- [x] QEMU guest agent restricted to the commands HyperLab uses; no guest
      command execution: the last provisioning step writes the allowlist and
      proves `guest-exec` refused from the host (software-verified)
- [x] remove the Machine account's passwordless sudo at the end of its
      first provisioning; later profile passes then ask for the guest
      account's password (decided 2026-10-04): done for every Machine whose
      account has a password (software-verified)
- [ ] the same for server Machines, whose account has no password today
- [x] SPICE channels a Template does not need disabled (clipboard, file
      transfer, USB redirection): no Machine gets the SPICE agent channel or
      USB redirection, and file transfer is off (`tests/media_input_contract.py`,
      software-verified)
- [x] no display server beyond loopback: SPICE only on a UNIX socket or
      loopback, the domain XML guard refusing any SPICE or VNC elsewhere and
      any second display device, and no ready Template projecting the SPICE
      clipboard on (decided 2026-10-05; `tests/graphics_exposure_contract.py`,
      software-verified)
- [x] VM disks at rest on the encrypted host volume only, with swap and
      temporary files of guests never on unencrypted storage: the store
      guard accepts only a dm-crypt source, guest disks, transient overlays
      and their swap and temporary files live in it, and the host refuses
      swap that is not zram or dm-crypt (`tests/bootstrap_storage_contract.py`,
      `tests/host_swap_contract.py`, software-verified)
- [ ] firmware updates through `fwupd`, with a recorded result on Nitro
- [x] host USB device policy so a new device is not trusted automatically
      ([ADR 0038](adr/0038-host-usb-device-policy.md), `roles/host_usbguard`,
      `tests/host_usbguard_contract.py`, software-verified)
- [ ] that policy applied on Nitro, with the internal keyboard and touchpad
      proved unaffected, and a device allowed from the host shell
      (the shell action is built and software-verified: the USB devices view,
      `playbooks/host-usb-allow.yml`, `tests/host_usbguard_contract.py`;
      Nitro acceptance remains)
- [ ] Wi-Fi card in a sys-net Machine through VFIO, the host routing the five
      networks through it and keeping their isolation, with a tested way to
      give the card back to the host
      ([ADR 0042](adr/0042-network-device-machine.md), proposed; IOMMU group
      checked: the card is alone in its group)
- [ ] USB controller in a sys-usb Machine, devices handed to Machines through
      an explicit host action
      ([ADR 0043](adr/0043-usb-controller-machine.md), proposed; one
      controller for every USB device, camera and Bluetooth included)
- [x] the measured boot image builder: one signed multi-profile UKI whose
      profiles mirror the boot entries, with signed PCR 11 policies, behind
      `measured_boot_enabled` (off) (`roles/measured_boot`,
      `tests/measured_boot_contract.py`, software-verified)
- [ ] measured boot: the boot profiles as one signed multi-profile unified
      kernel image measured into PCR 11, TPM2 with a PIN for the root volume,
      a recovery key kept off the host, the type 1 entries removed last
      ([ADR 0044](adr/0044-measured-boot.md), proposed; Secure Boot with
      HyperLab's own keys is already enabled)

### 11. Visual provenance and trust model

- [x] finish the host-owned visual provenance and trust model: every focused
      surface named by the host, including fullscreen guests
      ([ADR 0039](adr/0039-host-frame-around-fullscreen-guests.md): a host
      ring on the overlay layer while a guest is fullscreen, software-verified)
- [x] the host frame visible around a Looking Glass window at all times
      (same ADR, software-verified)
- [ ] the fullscreen ring accepted on Nitro over Looking Glass and the SPICE
      console
- [ ] study: Looking Glass as the everyday window for Linux Machines without
      a GPU too (the PipeWire sender captures any guest desktop), one kvmfr
      device per running Machine, SPICE kept as recovery only; Windows needs
      a GPU for its capture ([`study-looking-glass-without-gpu.md`](study-looking-glass-without-gpu.md);
      written; its Nitro experiment decides it)

### 12. Security plane

Decided: [ADR 0040](adr/0040-security-plane.md) (accepted: auditd and AIDE,
Suricata on bridge mirrors, logs shipped off the host).

- [x] host evidence without a command plane: auditd on HyperLab's trust
      points and an hourly file integrity check (`roles/host_audit`,
      `roles/host_integrity`; Arch has no AIDE; software-verified)
- [ ] endpoint HIDS with measured overhead and no hypervisor remote-command
      plane
- [ ] passive NIDS that is never an inline routing dependency (Suricata in a
      Machine on a bridge mirror: Arch has no Suricata package)
- [ ] HyperLab Security Plane correlating endpoint and network evidence, shown
      in Diagnostics
- [ ] host logs shipped as they are written to an append-only receiver off
      the host, with the host journal sealed (forward-secure) and a stale
      shipping state shown in Diagnostics; auditd and AIDE are detection, not
      prevention, and their evidence counts only once it has left the host
- [x] key vault, host side: a relay that passes only identity listing and
      signing to a vault Machine and asks the operator before every
      signature, per Machine and key, with a capped time allowance
      ([ADR 0048](adr/0048-key-vault.md), proposed; `roles/host_vault`,
      `tests/vault_relay_contract.py`, software-verified)
- [x] the vault Machine's domain: `key_vault: vault` plans no interface and
      one vsock device, `key_vault: client` adds the vsock device, and the
      domain XML guard refuses either added to a live domain
      (`tests/key_vault_domain_contract.py`, software-verified)
- [x] the vault's listener (host only, list and sign only) and its first-boot
      key, from its cloud-init alone (`vm-specs/vault.yml`), and a client's
      agent socket (`roles/guest_vault_client`,
      `playbooks/guest-vault-client.yml`; `tests/vault_guest_contract.py`,
      software-verified)
- [ ] the vault created in the lab host and a client signing through the
      relay there
- [ ] the same seen on Nitro: `ssh -T git@github.com` from `dev-01` asks on
      the host, succeeds when allowed, fails when denied or ignored

### 12b. Emergency stop

Proposed: [ADR 0047](adr/0047-emergency-stop.md) (the key is the operator's
to decide).

- [x] one host key cuts every running Machine's network links and then
      pauses it, recording exactly what it changed; the shell shows the stop
      and restores exactly that after a typed confirmation
      (`hyperlabctl panic`, `tools/hyperlabctl/tests/test_panic.py`,
      `tests/host_quickshell_runtime_contract.py`, software-verified)
- [ ] the emergency stop pressed and restored on Nitro, with running, paused
      and VFIO Machines (ADR 0047 hardware test)

### 13. Performance and gaming tuning

Measured with the complete security plane active.

- [ ] CPU pinning and isolation profiles for gaming Templates
- [ ] huge pages and memory policy for GPU guests
- [ ] latency and frame-time benchmarks recorded per Template

### 14. Release qualification and the Doppiari release

- [x] C10, C11: a read-only readiness check before install and a host
      profile proposal to review (`hyperlabctl doctor --hardware [--profile
      NAME]`, [ADR 0050](adr/0050-hardware-readiness-and-profile.md),
      proposed; `tools/hyperlabctl/tests/test_hardware.py`; run read-only on
      the Nitro on 2026-10-06: every check ok, operator-observed,
      unpublished)
- [ ] the same on the Predator and in the lab host
- [ ] release qualification: idempotence, reboot, cold start, recovery and
      hardware gates, in the checked-in order: repository-software,
      bootstrap-dry-run, bootstrap-clean-install, storage-handoff,
      host-idempotence, network-isolation, standard-vm-lifecycle,
      vfio-trust-lifecycle, looking-glass, jellyfin-service, service-recovery,
      sanitized-publication (this order does not cover the v1 additions:
      see [v1 scope and evidence status](#v1-scope-and-evidence-status))
  - [x] a passed gate needs every reviewed boolean exactly true on record,
        status and seal; `spice_socket_private` is a typed boolean
        ([`problems/release-pass-with-false-booleans.md`](../problems/release-pass-with-false-booleans.md),
        `tests/release_acceptance_contract.py`,
        `tests/release_probe_contract.py`, software-verified on fixture
        campaigns)
- [ ] `arch-bootstrap` frozen at the same campaign; `arch-hypervisor-lab`
      receives only the sanitized evidence
- [x] threat model document: what HyperLab protects against and what it does
      not; no claim of Qubes OS security properties
      ([`threat-model.md`](threat-model.md), `tests/threat_model_contract.py`,
      software-verified)
- [x] `SECURITY.md` (private reporting through GitHub)
- [ ] private vulnerability reporting enabled in the repository settings
      before the release
- [ ] licence and authorship reviewed for publication under Doppiari
- [ ] wallpaper and polish, screenshots, video and release documentation
- [ ] sanitized Nitro evidence sealed with the exact public `main` commits
      exercised on hardware; Predator replayed and published separately

### Later

- **M13 — seamless guest applications:** future work, and never described as
  providing Qubes OS security properties; its shape is
  [ADR 0041](adr/0041-seamless-guest-applications.md), proposed.
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

- [x] a captured, generalized and sealed workstation Golden Image, the first
      published Template pinned to it, and a Machine created, projected,
      defined and started from it on Nitro: `arch-dev-20261003`,
      `workstation-dev` and `dev-01` (milestones 3 and 4, Nitro-verified:
      operator-observed, unpublished)
- [ ] the managed `domains.d` policy of a Machine created from a Template
      read back on Nitro and matched by the hook at its start
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
- [x] Hyprland layer blur behind the islands (software-verified)

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

- [x] physical Quickshell per-screen panel creation (operator-observed,
      unpublished)
- [x] 37px exclusive zone accepted in the physical Hyprland session
      (operator-observed, unpublished)
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
      (operator-observed, unpublished)
- [x] reviewed focused-surface provenance resolver wired live into the shell
      (software-verified)
- [x] physical Nitro acceptance of live focused-surface provenance
      (operator-observed, unpublished)
- [x] reviewed desktop-entry catalogue and app-launch bridge (milestone 8;
      Rofi stays on `SUPER + D` for applications outside the catalogue)
- [ ] reviewed focused-window targeting (fullscreen/opacity stay compositor
      shortcuts; the shell cannot request them)
- [ ] native Networks and Nitro hardware views behind their feature gates
      (the Create view needs none: it runs the same steps as the CLI)
- [ ] visual theme and wallpaper browsers (needs reviewed per-theme palette export)
- [ ] shell-owned notifications (mako remains the reviewed daemon)
- [x] complete keybinding cheatsheet surface: `SUPER + F1`, every host binding
      on the sheet and nothing else (`tests/host_key_sheet_contract.py`;
      the same item as in milestone 6, software-verified)
- [ ] Sway native parity acceptance (Sway remains the recovery session)
