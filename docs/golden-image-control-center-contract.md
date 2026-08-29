# Golden-image and Control Center contract

The lab is intended to be reproducible from ArchISO to a usable hypervisor
without reconstructing machine state from memory.

This document fixes the target boundary. It does not claim that every Control
Center action described here is implemented yet.

## Pipeline end state

The repository pipeline is responsible for reaching the same host baseline that
is used to build and validate the current Nitro lab:

```text
ArchISO
  -> arch-bootstrap
  -> hyperlab-ansible
  -> reconciled hypervisor host
  -> sealed golden-image catalog
  -> Control Center lifecycle operations
```

The host side includes the hardened kernel, KVM/libvirt, VFIO ownership,
desktop/session integration, Looking Glass host integration and optional
hardware controls accepted by the detected profile.

Manual setup that exists only on the development laptop is not part of the
product. If a clean rebuild needs it, it must become repository state or an
explicit workshop step.

## Golden images

A finished development VM is not a special snowflake. Once its hardware and
software campaign is sealed, it becomes a reusable image source.

`arch-dev-vfio` is being finished with that role in mind. The same model applies
to the Windows and other Linux images prepared by the project.

Golden images are immutable lifecycle inputs. Per-instance identity, writable
storage and runtime state belong to clones.

## Permanent clones

A permanent guest receives an independent writable disk derived from the
selected golden image and retains its state between boots.

Destroying a permanent guest is therefore an explicit destructive lifecycle
operation. Reset is not a synonym for destroy and recreate.

## Disposable clones

A disposable guest receives an overlay over the sealed base image.

Reset removes only disposable-owned identity and writable state and recreates
the guest from the same sealed base. The golden image itself is never repaired
in place by a disposable workload.

This is the reason the guest role keeps permanent and disposable storage
contracts separate instead of treating lifecycle as a UI label.

## Trust and GPU handoff

GPU assignment participates in the existing trust ladder. A clone request must
carry enough domain information for the lifecycle layer to refuse a GPU move
that would raise trust during the current boot.

The Control Center presents that state; it does not override the handoff
protocol.

## Control Center boundary

The Control Center is the normal operator surface for:

- choosing a golden image;
- selecting permanent or disposable lifecycle;
- creating, starting, stopping, resetting and destroying managed guests;
- showing trust/domain state;
- presenting host and guest acceptance problems;
- exposing supported hardware controls such as the Nitro panel.

The UI does not gain arbitrary root access to make those operations convenient.
Privileged actions continue through narrow repository-owned helpers or existing
managed lifecycle commands with explicit validation.

## Publication gate

A golden image enters the catalog only after its relevant hardware and
idempotence gates are closed.

For `arch-dev-vfio`, real Looking Glass video is already proved, but input
isolation remains a separate acceptance gate. A VM is not sealed merely because
it boots or renders a desktop.

The final repository evidence should allow a clean ArchISO rebuild to reach the
same catalog and lifecycle behavior without relying on the history of the
development machine.
