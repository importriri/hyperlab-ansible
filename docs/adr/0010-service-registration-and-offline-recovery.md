# ADR 0010: Register service capacity before VM creation and recover offline

- Status: accepted for M7 software validation
- Date: 2026-07-28

## Context

A service VM consumes resources even when it is temporarily shut down: future
starts must still fit, its network identity must not collide, and backups must
remain attributable to the exact service contract. Libvirt only reports active
memory commitments, while a free-form DHCP or backup procedure can silently
reassign identity or destroy the last recoverable disk.

Installing service packages or controllers on the hypervisor would violate the
empty-host principle. Reusing the guest role for service registration would
also be incorrect: registration must reserve capacity before guest creation,
whereas `guest` owns domain and disk lifecycle.

## Decision

M7 introduces a separate `service_registry` brick.

A service is described by a service spec, a linked permanent standard VM spec
and a reviewed static lease. Registration must happen before VM creation and
writes a root-owned receipt that binds both spec hashes, fixed RAM, DHCP
identity, exposure intent and recovery policy.

Inactive registered services reserve their declared memory. Active services are
excluded from that reservation because libvirt already reports their memory;
the candidate service is excluded from its own reservation while being created
or started.

The persistent and active `services` network XML must both contain exactly the
reviewed lease. M7 records exposure intent but permits no exposure because its
global allowlist is empty.

Backups and restores are offline-only. A backup is built and verified in an
entire staging directory and committed by atomic directory rename. Restore
preserves the current disk as rollback until the replacement passes
`qemu-img check` and independent-qcow2 validation. Destructive unregister,
restore and backup deletion require exact confirmations.

## Consequences

- Service registration cannot claim an existing unowned domain or disk.
- Shut-down services still reduce future guest capacity.
- Static network identity is reviewable and drift-detected.
- M8 application bricks can consume the service contract without writing host
  packages or inventing firewall holes.
- Backup and restore cannot run live; planned downtime is mandatory.
- A changed service/VM/registration receipt invalidates older backup provenance
  until the operator deliberately reconciles the contract.

## Rejected alternatives

- **One fixed service RAM reserve in each laptop profile:** wastes capacity and
  cannot identify which service owns it.
- **Register after VM creation:** permits retroactive ownership of unknown
  artefacts and loses capacity guarantees during creation.
- **Dynamic `virsh net-update` leases:** makes runtime state the source of truth
  and bypasses persistent XML review.
- **Live qcow2 copy or snapshot:** produces consistency claims M7 cannot verify
  without guest/application quiescing.
- **Overwrite-in-place restore:** destroys the only rollback path before the new
  disk is known good.
