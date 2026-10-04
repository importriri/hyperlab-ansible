# ADR 0018 - A disposable Machine discards its writes every time it stops

## Context

[`0002-lifecycle-disposable-permanent.md`](0002-lifecycle-disposable-permanent.md)
made a disposable guest a qcow2 overlay over the sealed base, returned to a
known state by an explicit reset: delete the overlay, recreate it. Between
resets every write persists across shutdowns. A disposable Machine that
keeps what a browser session or a lab experiment wrote until someone
remembers to reset it is not disposable; roadmap milestone 5 asks for one
that really discards its writable layer on shutdown.

Doing that from HyperLab code would mean watching the domain stop (the qemu
hook, or a poller) and recreating the overlay as root, with a window in
which a crash, a forced stop or a host reboot leaves the old writes in
place.

## Decision

A disposable Machine's disk is a libvirt **transient disk**: the domain
XML marks the overlay `<transient/>`. When the domain starts, libvirt puts a
temporary qcow2 overlay on top of it and QEMU writes only there; when the
domain stops, for any reason, libvirt deletes it. The lifecycle overlay
created by the guest transaction is never written after creation, so every
start begins from the sealed base exactly as the first boot did.

- Only `lifecycle: disposable` gets `<transient/>`; a permanent Machine is
  unchanged.
- The managed XML contract compares the flag, so a disposable domain whose
  definition lost it is refused by validation instead of quietly keeping
  writes.
- Explicit reset stays: it rebuilds the overlay, seed, NVRAM and TPM
  state, for repair or a new sealed base.
- Templates may allow `disposable` only where a Machine is useful without
  any state of its own. The server Templates allow it; `workstation-dev`
  does not, because its account and rice are applied after the first boot
  and would be lost at every stop.

## Consequences

- Every start is a first boot. cloud-init runs again from the same seed:
  the account and the key come back, and the guest generates a new
  machine-id and new SSH host keys. The pinned host key is stale after a
  restart; `vm-guest-inventory.yml` reads the new one through QEMU Guest
  Agent and replaces the pin, as it does for a new Machine.
- Snapshots and live migration of a transient disk are not supported by
  libvirt; HyperLab offers neither for disposable Machines.
- libvirt creates the temporary overlay beside the lifecycle overlay in
  `disposable/` and removes it on stop. Whether a temporary file survives a
  host crash, and how the next start treats it, is part of the Nitro
  acceptance, not assumed here.
