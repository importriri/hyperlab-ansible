# Architecture decision index

These records define the boundaries that outlive individual implementation
milestones. Numbers are unique and ordered by the point at which each decision
entered the pipeline.

1. [`0001-image-store-layout.md`](0001-image-store-layout.md) — canonical image
   store ownership and layout.
2. [`0002-lifecycle-disposable-permanent.md`](0002-lifecycle-disposable-permanent.md)
   — permanent and disposable guest semantics.
3. [`0003-manifest-and-spec-schemas.md`](0003-manifest-and-spec-schemas.md) —
   separation of image manifests and VM instance specs.
4. [`0004-hyperlabctl-placement.md`](0004-hyperlabctl-placement.md) — reviewed
   checkout as the cockpit command source.
5. [`0005-brick-prerequisites.md`](0005-brick-prerequisites.md) — executable
   prerequisite graph for Ansible bricks.
6. [`0006-hardware-profile-source-of-truth.md`](0006-hardware-profile-source-of-truth.md)
   — PrivateStack as the runtime hardware-profile authority.
7. [`0007-memory-budget-policy.md`](0007-memory-budget-policy.md) — host reserve,
   inactive-service reservations and guest capacity checks.
8. [`0008-standard-guest-transaction.md`](0008-standard-guest-transaction.md) —
   transactional standard-guest lifecycle.
9. [`0009-vfio-guest-ownership.md`](0009-vfio-guest-ownership.md) — exclusive PCI
   ownership and trust-ranked GPU hand-off.
10. [`0010-image-provenance-transaction.md`](0010-image-provenance-transaction.md)
    — sealed bases and provenance receipts.
11. [`0011-service-registration-and-offline-recovery.md`](0011-service-registration-and-offline-recovery.md)
    — service registration before VM creation and offline recovery.
12. [`0012-reference-service-exposure-and-appliance.md`](0012-reference-service-exposure-and-appliance.md)
    — lifecycle-bound exposure for the reference Jellyfin appliance.
13. [`0013-cross-repository-storage-and-evidence-freeze.md`](0013-cross-repository-storage-and-evidence-freeze.md)
    — stage-1 storage ownership and cross-repository evidence freeze.
14. [`0014-cockpit-surface.md`](0014-cockpit-surface.md) — one read-only cockpit
    model rendered by Waybar, Rofi and the terminal panel.
15. [`0015-golden-image-capture.md`](0015-golden-image-capture.md) — the
    Workbench and the capture, generalization and seal of a Golden Image.
16. [`0016-gpu-shared-definition-running-lease.md`](0016-gpu-shared-definition-running-lease.md) — several
    managed VFIO domains may name the GPU; only the running one owns it.
17. [`0017-shell-machine-creation.md`](0017-shell-machine-creation.md) —
    accepted: the shell creates a Machine through the reviewed bridge and one
    durable operation; the password and the become prompt stay in its
    terminal (operator's decision, 2026-11-05).
18. [`0018-disposable-discards-on-stop.md`](0018-disposable-discards-on-stop.md)
    — accepted: a disposable Machine's disk is a libvirt transient disk, so
    every stop discards its writes (operator's decision, 2026-11-05).
    Protected access and the host-key pin at every later boot are not built;
    Nitro evidence remains open (see the record's Limits).
19. [`0019-gpu-lease.md`](0019-gpu-lease.md) — accepted: a GPU-capable
    Machine chooses at each start whether this run owns the GPU; initially
    `workstation-dev-standard` only, default without the dedicated NVIDIA
    GPU (operator's decision, 2026-11-05; unpublished source in the record).
    Not built; image readiness, Create acceptance and the physical
    GPU → no-GPU → GPU test remain open (see the record's preconditions).
20. [`0020-host-to-guest-clipboard.md`](0020-host-to-guest-clipboard.md) —
    host-to-guest clipboard is one host action aimed at one Machine, over
    the pinned SSH channel to a fixed receiver.
21. [`0021-product-lifecycle.md`](0021-product-lifecycle.md) — the canonical
    map from Image Factory to Golden Image, Template, Machine, Desk and
    Project; a fresh install has no Machines.
22. [`0022-network-trust-and-gpu-policy.md`](0022-network-trust-and-gpu-policy.md)
    — proposed: network identity and GPU handoff class are separate
    authorities; the ladder, the ceiling rule and services, with the per-run
    lease left to ADR 0019.
23. [`0023-gaming-identities.md`](0023-gaming-identities.md) — gaming
    uses clean, dirty and lab, not a separate PLAY identity.
24. [`0024-rereceipt-after-policy-change.md`](0024-rereceipt-after-policy-change.md)
    — a sealed official image's receipt is re-issued after a policy change
    only when its base still is the vendor's verified download.
25. [`0025-host-key-without-agent-file-reads.md`](0025-host-key-without-agent-file-reads.md)
    — proposed: pin a Machine's SSH host key from the host-logged serial
    console instead of agent file reads.
26. [`0026-offline-derived-images.md`](0026-offline-derived-images.md) — the
    Workbench derives a Golden Image offline from a sealed base with a
    reviewed package list, never booting it.
27. [`0027-guest-notification-owner.md`](0027-guest-notification-owner.md)
    — proposed: mako keeps owning guest notifications and the shell drives
    it; a quiet Desk is built on mako's do-not-disturb mode.
28. [`0028-image-build-provenance.md`](0028-image-build-provenance.md) — a
    Workbench image's manifest records the checkout commit, the base and its
    digest, and a package list read offline and pinned by digest.
29. [`0029-template-review-gate.md`](0029-template-review-gate.md) — every
    Template names a class that bounds its networks, devices, GPU profiles,
    lifecycles and presentation.
30. [`0030-disposable-browser-image.md`](0030-disposable-browser-image.md)
    — proposed: the disposable browser image gets its session through a
    Workbench capture of a reviewed kiosk profile.
31. [`0031-service-appliance-templates.md`](0031-service-appliance-templates.md)
    — proposed: a services Template names its reviewed service spec, which
    owns the appliance's address, exposure and backups.
32. [`0032-guest-clipboard-out.md`](0032-guest-clipboard-out.md) — proposed:
    clipboard out of a guest is a host pull with confirmation upward and
    control characters refused.
33. [`0033-file-transfer-drop-folder.md`](0033-file-transfer-drop-folder.md)
    — proposed: files reach a guest's inbox over the pinned SSH channel, one
    set and one target per action.
34. [`0034-usb-passthrough.md`](0034-usb-passthrough.md) — proposed: a host
    allowlist and a live-only attach action per device and Machine.
35. [`0035-microphone-and-camera.md`](0035-microphone-and-camera.md) —
    proposed: capture streams linked by the host on demand, with a host
    indicator.
36. [`0036-machine-snapshots-and-backups.md`](0036-machine-snapshots-and-backups.md)
    — proposed: offline independent snapshots with retention, and restic
    backups to a host-only target.
37. [`0037-qemu-process-confinement.md`](0037-qemu-process-confinement.md)
    — accepted: per-Machine DAC identities plus one AppArmor profile for
    every QEMU process; Arch's libvirt has no AppArmor driver.
38. [`0038-host-usb-device-policy.md`](0038-host-usb-device-policy.md) —
    accepted: USBGuard blocks a new USB device until the operator allows it.
39. [`0039-host-frame-around-fullscreen-guests.md`](0039-host-frame-around-fullscreen-guests.md)
    — accepted: a host-drawn provenance ring on the overlay layer around a
    fullscreen guest window.
40. [`0040-security-plane.md`](0040-security-plane.md) — accepted: auditd
    and AIDE on the host, Suricata on bridge mirrors, a read-only
    correlation shown in Diagnostics, and logs shipped off the host to an
    append-only receiver.
41. [`0041-seamless-guest-applications.md`](0041-seamless-guest-applications.md)
    — proposed: whole desktops for now; later waypipe per application,
    confined and without clipboard forwarding.
42. [`0042-network-device-machine.md`](0042-network-device-machine.md) —
    proposed: a sys-net Machine owns the Wi-Fi card; the host routes the five
    networks through it and keeps their isolation.
43. [`0043-usb-controller-machine.md`](0043-usb-controller-machine.md) —
    proposed: a sys-usb Machine owns the only USB controller; a device goes to
    a Machine through a host-relayed vsock port.
44. [`0044-measured-boot.md`](0044-measured-boot.md) — proposed: a signed
    multi-profile unified kernel image measured into PCR 11, TPM2 with a PIN
    for the root volume, and a recovery key kept off the host.
45. [`0045-looking-glass-stream-health.md`](0045-looking-glass-stream-health.md)
    — proposed: the shell asks the guest's sender whether its stream is
    alive and restarts the capture without restarting the Machine.
46. [`0046-nested-lab-host.md`](0046-nested-lab-host.md) — proposed: an
    `hl-lab-host` VM, made by a script without privilege and installed like
    the host, where host-level changes are tested with root.
47. [`0047-emergency-stop.md`](0047-emergency-stop.md) — proposed: explicit
    CLI stop, status and confirmed Restore implemented and software-verified;
    the host key is unbound pending the operator's choice and the physical
    campaign remains open.
48. [`0048-key-vault.md`](0048-key-vault.md) — proposed: SSH keys in a vault
    Machine without a network, reached through a host relay that asks the
    operator before every signature.
50. [`0050-hardware-readiness-and-profile.md`](0050-hardware-readiness-and-profile.md)
    — proposed: a read-only readiness check before install that proposes a
    host profile for the operator to review.
51. [`0051-disposable-viewer-and-safe-documents.md`](0051-disposable-viewer-and-safe-documents.md)
    — proposed: documents open in a disposable viewer without a network, and
    a PDF is rebuilt from its pixels only.
52. [`0052-host-without-gpu-passthrough.md`](0052-host-without-gpu-passthrough.md)
    — proposed: a host profile without GPU passthrough, chosen only by name,
    never by `auto`.
53. [`0053-withdraw-machine-intent.md`](0053-withdraw-machine-intent.md) —
    accepted: option A creates a Machine in one staged step that publishes
    the record last; a record is withdrawn only by its digest, under the
    registry lock, and never while a projection or a domain follows from it.
    Operator's decision, 2026-11-05; unpublished source in the record.
    Transaction remediation and Nitro refusal evidence remain open.

54. [`0054-private-machine-diagnostics.md`](0054-private-machine-diagnostics.md) —
    proposed, software built: supervise one private diagnostics collection
    through the typed bridge; managed lifecycle stays with the durable runner.
55. [`0055-recovery-readback-verification.md`](0055-recovery-readback-verification.md)
    — proposed: recovery trust readbacks match the CLI authority, and
    Networks tile allocation replaces stale implementation literals.

56. [`0056-product-symbol-geometry-b.md`](0056-product-symbol-geometry-b.md)
    — accepted operator decision: filled arcs with vertical cuts, top/bottom
    gaps and a small form shared by the shell and identity relief.

57. [`0057-trust-pool-pixel-verification.md`](0057-trust-pool-pixel-verification.md)
    — proposed: compare every trust pool pixel across Qt releases, retain
    compressed-file hashes and check all negative space and shared geometry.

58. [`0058-product-wallpaper-pool-materials.md`](0058-product-wallpaper-pool-materials.md)
    — proposed: share v3 stone and sphere materials with the native product
    and quieter lock family, retaining geometry B and pool dimensions.

59. [`0059-visible-name-migration-boundary.md`](0059-visible-name-migration-boundary.md)
    — proposed: document the remaining visible surfaces and pin accurate session
    names while their shared-identity migration remains open; load cosmetic
    CLI identity only for help/version so emergency stop stays independent;
    align byte/path refusals across shell, CLI and Bash readers; pin host
    login and guest presentation exceptions and require a widening locale.

The pre-VM baseline that led to these decisions remains available as
[`../historical-audit-m0.md`](../historical-audit-m0.md); it is archival evidence,
not current implementation documentation.

## Proposed decisions and their code

A record whose own Status line says proposed has not been accepted, whatever
code exists for it. This inventory lists every such record once and says
how much of it is built, how that code becomes active and what still stands
between it and acceptance. It is read from the sources and playbooks linked
in each entry, not from the names of tests: a contract proves what it
exercises in software, never that a playbook ran on the operator's host or
that hardware behaved. Nothing here accepts a decision or records a physical
observation. A record without a Status line is neither proposed nor
accepted by default and is not listed; there is no record 0049.
`tests/docs_contract.py` checks the inventory's membership, fields, labels
and links; review of the sources establishes what each entry says.

Every entry has five fields. **Decision** repeats the record's status.
**Built** and **Activation** each open with one label and a description:

| Built | Meaning |
| --- | --- |
| `none` | No code in the tree implements the decision. |
| `partial` | Some of the decided software is built; the entry names what is missing. |
| `built` | The software the record describes is built and exercised by contracts; acceptance and lab or hardware proof may still be open. |

| Activation | Meaning |
| --- | --- |
| `none` | There is nothing to activate. |
| `default` | Some of it is installed and acts without a HyperLab-specific choice, through `playbooks/v1-host.yml` (including `lab.yml` and `foundation.yml`), or the playbooks the Machine provisioner runs. |
| `on request` | Installed by an ordinary path, it acts only when the operator runs the command or takes the shell action. |
| `opt-in` | Nothing is installed or acts until the operator runs a separate playbook, sets a switch that is off by default or names a profile. |
| `not established` | The sources read do not settle how it becomes active. |

**Source** links the code and the checks that exercise it, or says `none`.
**Prerequisites** lists the decision, software, lab and hardware steps that
remain.

- [ADR 0022](0022-network-trust-and-gpu-policy.md)
  - Decision: proposed; no record accepts it, although the policy runs.
  - Built: built — the two fields, the ladder in the qemu hook, the ceiling
    rule in the factory, the guest planner and the root policy tool, and
    GPU-capable services through a reviewed handoff profile. The per-run
    lease it refers to is ADR 0019 and is not built.
  - Activation: default — `playbooks/foundation.yml` installs the hook and
    its rotation through `gpu_handoff` on a host profile that passes a GPU
    through; the factory and the planner apply the ceiling rule to every
    Machine they create or plan.
  - Source: [`qemu`](../../roles/gpu_handoff/files/qemu),
    [`gpu_handoff_policy.py`](../../tools/gpu_handoff_policy.py),
    [`guest_plan.py`](../../tools/guest_plan.py),
    [`machine_factory.py`](../../tools/hyperlabctl/hyperlabctl/machine_factory.py),
    [`hook.bats`](../../tests/hook.bats)
  - Prerequisites: the operator's decision on a policy that is already
    active; the lease of ADR 0019. The record names no hardware procedure.

- [ADR 0025](0025-host-key-without-agent-file-reads.md)
  - Decision: proposed; the operator chooses before any of it is built.
  - Built: none — the host key is still read through QEMU Guest Agent file
    calls; no serial console log, console parser or host-made host key
    exists.
  - Activation: none — there is no code to activate.
  - Source: none
  - Prerequisites: the choice between options A, B and C; then the console
    source in the inventory step and a reviewed migration of existing
    domain definitions.

- [ADR 0027](0027-guest-notification-owner.md)
  - Decision: proposed; the operator chooses who owns notifications.
  - Built: partial — what the record builds under every option:
    `hyperlab-desk quiet` with its state, mako's do-not-disturb mode
    following the Desk in front, `quiet sync` at session start, and the
    guest status island showing a quiet Desk. No shell notification server
    and no list of waiting notifications exist.
  - Activation: default — the `guest_desktop_hyprland` role installs it in
    every workstation profile playbook the provisioner runs, such as
    `playbooks/guest-arch-dev.yml`.
  - Source: [`hyperlab-desk.py`](../../roles/guest_desktop_hyprland/files/hyperlab-desk.py),
    [`hyprland.lua.j2`](../../roles/guest_desktop_hyprland/templates/hyprland.lua.j2),
    [`StatusIsland.qml`](../../roles/guest_desktop_hyprland/files/quickshell/hyperlab-workspace/StatusIsland.qml),
    [`guest_desk_helper_contract.py`](../../tests/guest_desk_helper_contract.py)
  - Prerequisites: the choice between options A, B and C; for B, the shell's
    notification server and a contract that proves the name handover.

- [ADR 0030](0030-disposable-browser-image.md)
  - Decision: proposed; the operator chooses before the image is built.
  - Built: none — the `browser-disposable` Template is a draft and the
    `arch-browser` image manifest says `not-built`; there is no browser
    profile playbook, account role or capture.
  - Activation: none — the draft Template is not offered for creation.
  - Source: none
  - Prerequisites: the choice between options A and B, and of the browser;
    the image built, sealed and validated; the download question of
    milestone 6.

- [ADR 0031](0031-service-appliance-templates.md)
  - Decision: proposed; the operator chooses before a services Template is
    ready.
  - Built: none — `svc-jellyfin` is a draft Template; Jellyfin is deployed
    by `playbooks/jellyfin.yml` under ADR 0012, not by this decision.
  - Activation: none — the draft Template is not offered for creation.
  - Source: none
  - Prerequisites: the choice between options A and B; then the singleton
    services Template and its provisioning through the operation runner.

- [ADR 0032](0032-guest-clipboard-out.md)
  - Decision: proposed; the operator chooses before any of it is built.
  - Built: none — only host to guest exists (ADR 0020); there is no guest
    offer program and no `clipboard take`.
  - Activation: none — there is no code to activate.
  - Source: none
  - Prerequisites: the choice between options A and B; then the pull, its
    confirmations, the control-character refusal and the crossing log.

- [ADR 0033](0033-file-transfer-drop-folder.md)
  - Decision: proposed; the operator chooses before it is built.
  - Built: none — no file crosses between host and guests; SPICE file
    transfer and shared folders are off in every spec.
  - Activation: none — there is no code to activate.
  - Source: none
  - Prerequisites: the choice between options A and B; then the host action
    and the fixed guest receiver with its limits and log.

- [ADR 0034](0034-usb-passthrough.md)
  - Decision: proposed; the operator chooses before it is built.
  - Built: none — every spec's `usb_allowlist` is empty and the guest
    planner refuses a non-empty one; the host USB policy of ADR 0038 is a
    separate, accepted record.
  - Activation: none — there is no code to activate.
  - Source: none
  - Prerequisites: the choice between options A and B; then the host
    allowlist, the live-only attach and detach actions and their shell
    presentation.

- [ADR 0035](0035-microphone-and-camera.md)
  - Decision: proposed.
  - Built: none — no domain definition gives a guest an audio input or a
    camera, and `tests/media_input_contract.py` keeps it that way until
    this is decided.
  - Activation: none — there is no code to activate.
  - Source: none
  - Prerequisites: the operator's choice for the microphone and the camera;
    then the on-demand capture link and the host-drawn indicator.

- [ADR 0036](0036-machine-snapshots-and-backups.md)
  - Decision: proposed; the operator chooses before any of it is built.
  - Built: none — only registered services have backups, offline, local and
    unencrypted, under ADR 0011; Machines have neither snapshots nor
    encrypted backups.
  - Activation: none — there is no code to activate.
  - Source: none
  - Prerequisites: the choice of snapshot and backup options; the backup
    target, which ADR 0043 constrains if it is a USB disk; the restore drill
    on a clean host.

- [ADR 0041](0041-seamless-guest-applications.md)
  - Decision: proposed; future work in the roadmap's "Later".
  - Built: none — a Machine is a whole desktop.
  - Activation: none — there is no code to activate.
  - Source: none
  - Prerequisites: the host frame holding in every case (ADR 0039) and QEMU
    confinement in force (ADR 0037); then the confined waypipe client and a
    tested clipboard and drag-and-drop filter.

- [ADR 0042](0042-network-device-machine.md)
  - Decision: proposed; the hardware test decides it.
  - Built: none — the host drives the Wi-Fi card; there is no sys-net
    Machine and no uplink network.
  - Activation: none — there is no code to activate.
  - Source: none
  - Prerequisites: the record's Nitro hardware test, then the operator's
    decision, then the Machine, the uplink and the fallback.

- [ADR 0043](0043-usb-controller-machine.md)
  - Decision: proposed; the hardware test decides it.
  - Built: none — the host drives the only USB controller; there is no
    sys-usb Machine, boot profile or vsock relay.
  - Activation: none — there is no code to activate.
  - Source: none
  - Prerequisites: the record's Nitro hardware test, then the operator's
    decision, then the boot profile, the Machine and the device handoff.

- [ADR 0044](0044-measured-boot.md)
  - Decision: proposed; every step that changes how Nitro boots stays the
    operator's.
  - Built: partial — step 1 and the measured part of step 2 of option A: a
    signed multi-profile UKI with signed PCR 11 policies, checked against
    the host's `db` certificate, the previous image kept, and an mkinitcpio
    post hook. TPM2 enrollment with a PIN, the recovery key, a new default
    entry and the removal of the type 1 entries are not built and stay the
    operator's.
  - Activation: opt-in — only `playbooks/measured-boot.yml` runs the role,
    no default playbook imports it, and with `measured_boot_enabled: false`,
    the default, it builds nothing, removes its rebuild hook and records
    the `measured_boot` brick stamp.
  - Source: [`main.yml`](../../roles/measured_boot/tasks/main.yml),
    [`defaults/main.yml`](../../roles/measured_boot/defaults/main.yml),
    [`hyperlab-uki-build.py`](../../roles/measured_boot/files/hyperlab-uki-build.py),
    [`measured-boot.yml`](../../playbooks/measured-boot.yml),
    [`measured_boot_contract.py`](../../tests/measured_boot_contract.py)
  - Prerequisites: the operator's decision; every profile booted from the
    image in the lab host (OVMF in setup mode, swtpm); the record's Nitro
    hardware test in its order, TPM2 enrollment included.
    `measured-boot.yml` has no GPU-passthrough condition. On a host without
    passthrough (ADR 0052), enabling it installs the UKI tooling and, if the
    Secure Boot key check succeeds, creates the key directory and PCR
    signing key before refusing the empty VFIO IDs. The UKI configuration
    is not rendered.

- [ADR 0045](0045-looking-glass-stream-health.md)
  - Decision: proposed; the Nitro test decides it.
  - Built: built — `hyperlabctl looking-glass health` and
    `restart-capture`, the bridge's `stream-health` and `restart-capture`
    for a running managed Linux Looking Glass Machine, and the Stream
    section of the Machine pane.
  - Activation: on request — the commands run when the operator calls them,
    and the Stream section is in the Quickshell shell of the Hyprland
    session (`playbooks/host-desktop-hyprland.yml`). The sender they
    observe is built by the Looking Glass workstation and gaming profile
    playbooks and started only when Looking Glass is opened.
  - Source: [`looking_glass.py`](../../tools/hyperlabctl/hyperlabctl/commands/looking_glass.py),
    [`privatestack-machine-actions.py`](../../roles/host_desktop_common/files/privatestack-machine-actions.py),
    [`MachineContextPane.qml`](../../roles/host_desktop_common/files/quickshell/hyperlab/MachineContextPane.qml),
    [`test_looking_glass.py`](../../tools/hyperlabctl/tests/test_looking_glass.py),
    [`host_machine_actions_bridge_contract.py`](../../tests/host_machine_actions_bridge_contract.py)
  - Prerequisites: the operator's decision; the record's hardware items 2 to
    5, which wait for the installed host shell. Its amendment of 2026-10-13
    reports the earlier Nitro run; this inventory does not re-check it.

- [ADR 0046](0046-nested-lab-host.md)
  - Decision: proposed.
  - Built: built — `tools/lab/hl_lab.py` checks, creates, starts, stops and
    removes only `hl-lab-*` resources without privilege, its checker
    refuses any other domain definition, and the `hl-lab-testbed` network
    is declared beside the guest networks.
  - Activation: default — `lab_isolation`, in `playbooks/foundation.yml`,
    loads the host's rules for the lab bridge on every apply. The lab
    resources exist only after the operator runs `hl_lab.py create`, and
    `start` requires `--isolation-checked`.
  - Source: [`hl_lab.py`](../../tools/lab/hl_lab.py),
    [`hl_lab_check.py`](../../tools/lab/hl_lab_check.py),
    [`hl-lab-host.xml`](../../tools/lab/hl-lab-host.xml),
    [`lab_isolation defaults`](../../roles/lab_isolation/defaults/main.yml),
    [`hl_lab_contract.py`](../../tests/hl_lab_contract.py)
  - Prerequisites: the operator's decision; the record's Nitro test of the
    loaded isolation, the definition, the reachability and the install
    inside. This inventory does not establish that a lab host built with
    this tool exists.

- [ADR 0047](0047-emergency-stop.md)
  - Decision: proposed; the key choice is the operator's.
  - Built: partial — `hyperlabctl panic engage`, `status` and
    `restore --confirm`, the bridge's `panic-status` and `panic-restore`
    (it cannot engage), and the shell's banner with a typed Restore. At
    this revision neither the Hyprland template nor the host key sheet
    binds or lists an emergency key; the Sway configuration binds none
    either, and no check guards Sway.
  - Activation: on request — a stop is engaged only by running
    `hyperlabctl panic engage`; the banner and Restore appear in the
    Hyprland shell while a record exists. Whether a host's installed
    configuration still carries the earlier `SUPER+SHIFT+Escape` binding
    is not established here.
  - Source: [`panic.py`](../../tools/hyperlabctl/hyperlabctl/commands/panic.py),
    [`privatestack-machine-actions.py`](../../roles/host_desktop_common/files/privatestack-machine-actions.py),
    [`WorkspaceSurface.qml`](../../roles/host_desktop_common/files/quickshell/hyperlab/WorkspaceSurface.qml),
    [`hyprland.lua.j2`](../../roles/host_desktop_hyprland/templates/hyprland.lua.j2),
    [`test_panic.py`](../../tools/hyperlabctl/tests/test_panic.py),
    [`host_key_sheet_contract.py`](../../tests/host_key_sheet_contract.py)
  - Prerequisites: the operator's decision and key choice; a separately
    authorized binding with its sheet row and parity checks; the installed
    absence check on Nitro and Predator; the physical stop and restore
    campaign with running, paused, shut-off and VFIO Machines.

- [ADR 0048](0048-key-vault.md)
  - Decision: proposed.
  - Built: built — the host relay with its confirmation helper, the
    `key_vault` spec field and its domain checks, the vault Machine's
    cloud-init with its listener, and the client agent.
  - Activation: opt-in — the relay comes only from `playbooks/host-vault.yml`,
    the vault only from creating `vm-specs/vault.yml`, the client only from
    `playbooks/guest-vault-client.yml`, and the client agent becomes the
    default `SSH_AUTH_SOCK` only with `guest_vault_client_default_agent`.
  - Source: [`hyperlab-vault-relay.py`](../../roles/host_vault/files/hyperlab-vault-relay.py),
    [`hyperlab-vault-confirm.py`](../../roles/host_vault/files/hyperlab-vault-confirm.py),
    [`vault.yml`](../../vm-specs/vault.yml),
    [`user-data.j2`](../../roles/guest/templates/user-data.j2),
    [`hyperlab-vault-agent.py`](../../roles/guest_vault_client/files/hyperlab-vault-agent.py),
    [`vault_relay_contract.py`](../../tests/vault_relay_contract.py),
    [`vault_guest_contract.py`](../../tests/vault_guest_contract.py),
    [`key_vault_domain_contract.py`](../../tests/key_vault_domain_contract.py)
  - Prerequisites: the operator's decision; that vhost-vsock carries a
    guest's packets only to the host, and the confirmation dialog's output,
    both still unobserved; the record's test in the lab host, then on Nitro.

- [ADR 0050](0050-hardware-readiness-and-profile.md)
  - Decision: proposed.
  - Built: built — `hyperlabctl doctor --hardware` and its `--profile NAME`
    proposal, reading `/proc` and `/sys` without privilege.
  - Activation: on request — a read-only command; no installer in this
    repository calls it.
  - Source: [`hardware.py`](../../tools/hyperlabctl/hyperlabctl/hardware.py),
    [`doctor.py`](../../tools/hyperlabctl/hyperlabctl/commands/doctor.py),
    [`test_hardware.py`](../../tools/hyperlabctl/tests/test_hardware.py)
  - Prerequisites: the operator's decision; the runs on the Predator and in
    the lab host that the record leaves to do; the installer that would
    call it.

- [ADR 0051](0051-disposable-viewer-and-safe-documents.md)
  - Decision: proposed.
  - Built: partial — step 1 only, `hyperlab-safe-pdf to-pixels` and
    `from-pixels` with the stream reader's limits. The viewer Machine, the
    host relay and `hyperlab-open-disposable` are not built.
  - Activation: opt-in — only `playbooks/guest-safe-documents.yml` installs
    the converter, and no profile playbook imports it.
  - Source: [`hyperlab-safe-pdf.py`](../../roles/guest_safe_documents/files/hyperlab-safe-pdf.py),
    [`main.yml`](../../roles/guest_safe_documents/tasks/main.yml),
    [`guest-safe-documents.yml`](../../playbooks/guest-safe-documents.yml),
    [`safe_pdf_contract.py`](../../tests/safe_pdf_contract.py)
  - Prerequisites: the operator's decision; steps 2 to 4 of the record; its
    test in the lab host, then on Nitro.

- [ADR 0052](0052-host-without-gpu-passthrough.md)
  - Decision: proposed.
  - Built: built — the `no-gpu-passthrough` profile, the selection rules
    that keep `auto` from considering it, and the skip of `vfio_boot` and
    `gpu_handoff` without their brick stamps.
  - Activation: opt-in — only `host_profile: no-gpu-passthrough` selects it.
    The default `host_profile: auto` runs the same selection on every
    `foundation.yml` apply, never picks it and still stops when no profile
    matches completely: there is no automatic fallback. On such a host a
    VFIO Machine's GPU policy step refuses without the `gpu_handoff`
    directory. The separate `measured-boot.yml` still runs its role on
    this profile; its VFIO-ID refusal stops it before UKI configuration
    rendering, after tooling and key setup (ADR 0044).
  - Source: [`select.yml`](../../roles/hardware_probe/tasks/select.yml),
    [`hardware.yml`](../../group_vars/all/hardware.yml),
    [`foundation.yml`](../../playbooks/foundation.yml),
    [`vfio-policy.yml`](../../roles/guest/tasks/vfio-policy.yml),
    [`render.yml`](../../tests/render.yml),
    [`static_contract.py`](../../tests/static_contract.py)
  - Prerequisites: the operator's decision; the record's run in the lab
    host with the profile named, and `auto` on Nitro; nothing is tested on
    a real one-GPU host.

- [ADR 0054](0054-private-machine-diagnostics.md)
  - Decision: proposed.
  - Built: built — the bridge's supervised `collect_diagnostics` over the
    fixed registry routes, its result validation and the shell's handlers,
    exercised with synthetic sources.
  - Activation: on request — the Diagnostics action of the selected Machine
    in the Hyprland shell, through the bridge `host_desktop_common` installs.
  - Source: [`privatestack-machine-actions.py`](../../roles/host_desktop_common/files/privatestack-machine-actions.py),
    [`diagnostics.py`](../../tools/hyperlabctl/hyperlabctl/commands/diagnostics.py),
    [`test_diagnostics.py`](../../tools/hyperlabctl/tests/test_diagnostics.py),
    [`host_machine_actions_bridge_contract.py`](../../tests/host_machine_actions_bridge_contract.py),
    [`host_operation_integration_contract.py`](../../tests/host_operation_integration_contract.py)
  - Prerequisites: the operator's decision; collection from the installed
    shell and on hardware, on Nitro and Predator.

- [ADR 0055](0055-recovery-readback-verification.md)
  - Decision: proposed.
  - Built: built — M11 invokes the recovery ladder and Networks allocation
    contracts instead of requiring the inverted tuple and fixed canvas.
  - Activation: default — the contracts run through M11 and the discovered
    repository checks; presentation changes require deployment.
  - Source: [`m11_control_center_contract.py`](../../tests/m11_control_center_contract.py),
    [`recovery_gpu_ladder_contract.py`](../../tests/recovery_gpu_ladder_contract.py),
    [`recovery_network_layout_contract.py`](../../tests/recovery_network_layout_contract.py),
    [`privatestack-hyperlab-domains.py`](../../roles/host_desktop_sway/files/privatestack-hyperlab-domains.py)
  - Prerequisites: the operator's decision; installed Nitro visual rechecks
    and the frozen Predator replay remain open.

- [ADR 0057](0057-trust-pool-pixel-verification.md)
  - Decision: proposed.
  - Built: built — exact decoded-pixel regeneration, independent manifest
    hashes, full negative-space checks and product geometry parity.
  - Activation: default — the discovered contract runs through repository
    verification and CI; no deployment or authority rule changes.
  - Source: [`trust_pool_v3_generated_contract.py`](../../tests/trust_pool_v3_generated_contract.py),
    [`render_trust_pool.py`](../../tools/wallpaper/render_trust_pool.py)
  - Prerequisites: the operator's decision; a hosted workflow run remains
    separate from local Arch and Ubuntu runtime evidence.

- [ADR 0058](0058-product-wallpaper-pool-materials.md)
  - Decision: proposed.
  - Built: built — shared v3 shader and capture, native product and lock
    outputs, pixel/hash, neutral-core and material geometry contracts.
  - Activation: default — `host_desktop_common` installs the product and
    dedicated lock assets; the discovered contracts run in repository checks.
  - Source: [`pool_material.py`](../../tools/wallpaper/pool_material.py),
    [`render_isolation_ring.py`](../../tools/wallpaper/render_isolation_ring.py),
    [`render_trust_pool.py`](../../tools/wallpaper/render_trust_pool.py),
    [`host_identity_asset_contract.py`](../../tests/host_identity_asset_contract.py),
    [`product_symbol_geometry_contract.py`](../../tests/product_symbol_geometry_contract.py)
  - Prerequisites: the operator's decision; Nitro product and lock inspection
    at 1920×1080 under both compositors, then Predator replay.

- [ADR 0059](0059-visible-name-migration-boundary.md)
  - Decision: proposed.
  - Built: built — explicit remaining visible-surface inventory, accurate
    session documentation and narrowly pinned documentation exceptions;
    lazy help/version identity leaves operational dispatch independent;
    shared byte/path fixtures cover every reader and installed UTF-8 locale,
    requiring a language locale that exercises Bash range widening.
  - Activation: default — product contract checks documentation and existing
    host/guest QML, desktop/Waybar/lock/login labels, helper stderr, reader
    parity and operational independence from cosmetic input; no session or
    authority change.
  - Source: [`product_display_name_contract.py`](../../tests/product_display_name_contract.py).
  - Prerequisites: the operator's decision; the remaining visible migration
    and physical Nitro/Predator gates remain open.
