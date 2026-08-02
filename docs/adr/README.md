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

The pre-VM baseline that led to these decisions remains available as
[`../historical-audit-m0.md`](../historical-audit-m0.md); it is archival evidence,
not current implementation documentation.
