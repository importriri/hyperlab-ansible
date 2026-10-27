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
    proposed: the shell creates a Machine through the reviewed bridge and one
    durable operation; the password and the become prompt stay in its
    terminal.
18. [`0018-disposable-discards-on-stop.md`](0018-disposable-discards-on-stop.md)
    — proposed: a disposable Machine's disk is a libvirt transient disk, so
    every stop discards its writes; access closing and the host-key pin at
    every later boot are not built.
19. [`0019-gpu-lease.md`](0019-gpu-lease.md) — proposed: a GPU-capable
    Machine chooses at each start whether this run owns the GPU.
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
47. [`0047-emergency-stop.md`](0047-emergency-stop.md) — proposed: one host
    key sets every running Machine's network links down and pauses it, and a
    confirmed Restore undoes exactly that.
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
    proposed: the shell creates a Machine in one staged step that publishes
    the record last; a record is withdrawn only by its digest, under the
    registry lock, and never while a projection or a domain follows from it.

The pre-VM baseline that led to these decisions remains available as
[`../historical-audit-m0.md`](../historical-audit-m0.md); it is archival evidence,
not current implementation documentation.
