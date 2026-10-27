# ADR 0018 - A disposable Machine discards its writes every time it stops

Status: accepted (2026-11-05, operator's decision).

The decision is recorded in the operator's private notes
(operator-observed, unpublished), in the 2026-11-05 task entry and Nitro
session step 11 at 19:28. The operator accepted the design read at `main`
commit `1e42308a863180590fc9b2a209b41227978b8a4f`: only disposable Machines
discard their disk writes on every stop; permanent Machines keep their data.
Readiness still requires protected access on every boot and the Nitro
tests. At acceptance, the transient disk was built and software-verified;
closing access and re-pinning the host key at every later boot were not built.
The amendment below now implements those software prerequisites (see Limits).
This records design acceptance without adding hardware evidence.

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
  restart; this decision needs `vm-guest-inventory.yml` to read the new one
  through QEMU Guest Agent and replace the pin, as it does for a new
  Machine. Nothing runs it at a start yet (see Limits).
- Snapshots and live migration of a transient disk are not supported by
  libvirt; HyperLab offers neither for disposable Machines.
- libvirt creates the temporary overlay beside the lifecycle overlay in
  `disposable/` and removes it on stop. Whether a temporary file survives a
  host crash, and how the next start treats it, is part of the Nitro
  acceptance, not assumed here.

## Limits

- Built and software-verified: only `lifecycle: disposable` gets
  `<transient/>` in
  [`domain.xml.j2`](../../roles/guest/templates/domain.xml.j2), and the
  managed XML contract in
  [`guest_xml_contract.py`](../../tools/guest_xml_contract.py) refuses a
  disposable domain without it
  ([`guest_contract.py`](../../tests/guest_contract.py)).
- Activation: default — every disposable Machine defined through the
  `guest` role (`playbooks/vm-create.yml`, which the provisioner runs)
  gets the transient disk, and the server Templates allow the disposable
  lifecycle.
- Built and software-verified: the amendment below restores the agent
  allowlist from the seed and re-pins the SSH host key after each new
  managed Start or Power Cycle. Existing seeds need recreation, and
  passwordless server accounts still receive passwordless sudo.
- Not proven on hardware: no disposable Machine has been started, stopped
  and started again on Nitro. Normal and forced stops still need evidence
  of discarded writes and temporary-overlay cleanup; host-crash recovery
  remains a separate physical test (see Consequences).
- Readiness prerequisites: the software amendment below, then the Nitro
  tests. [ADR 0025](0025-host-key-without-agent-file-reads.md) still proposes
  a different pin source. Accepting the design does not prove hardware readiness.

## Amendment: restore access policy and SSH identity on every boot

Status: Proposed.

A provisioning-time change on the transient disk disappears on stop too.
The disposable Linux cloud-init seed therefore writes root-owned
`/etc/qemu/qemu-ga.conf` on every new boot and restarts
`qemu-guest-agent.service` from `runcmd` to activate it. It reads the exact
`guest_access_close_agent_rpcs` allowlist from the access-closing role's
defaults; there is no second RPC policy in the seed. Create and reset refuse
the seed when that path is not the role's own defaults file, or when
inventory overrides `guest_access_close_agent_rpcs` with a different list.
Permanent Machines and Machines without cloud-init or the agent keep their
existing behavior.
The vault's existing boot files and commands share the same YAML lists.

The shared managed start path (including create-with-start and Power Cycle)
waits for this boot's `/run/cloud-init/result.json` through the existing
read-only agent file calls and requires `v1.errors` to be an empty list.
cloud-init publishes that runtime link after its final stage. This prevents
an already-restricted agent in a base from satisfying readiness before the
new boot's configuration and SSH key generation finish; for such a boot
this wait replaces the generic agent readiness wait, with the same budget.
The host then waits for `guest-info` to report exactly one disabled
`guest-exec` entry and, as enabled, exactly the allowlist: a `guest-exec`
blocked by something other than this seed, with other calls left open or
allowlisted calls missing, does not pass. The negative exec probe must then
fail specifically because `guest-exec` is disabled. Success, unavailable
agent, timeout, malformed reply and other RPC errors fail the operation, and
the host first force-stops that boot and waits for it to be shut off, since
its agent may still run commands and a stop loses nothing a disposable
Machine would keep. If even that stop fails, the failure says so. The probe
never provisions anything.
See the [cloud-init final stage](https://docs.cloud-init.io/en/latest/explanation/boot.html)
and its [result publication](https://github.com/canonical/cloud-init/blob/main/cloudinit/cmd/main.py),
and the [QEMU agent protocol](https://www.qemu.org/docs/master/interop/qemu-ga-ref.html).

After the new boot passes, public managed Start and Power Cycle import the
existing inventory publisher as the Machine owner, with `become: false`.
It discovers the address and public host key through the agent, replaces
the strict host-owned SSH pin and publishes the runtime inventory. Discovery
or pinning failure fails the operation; an old pin never means the new boot
is usable. No network key is accepted. An already-running Start and check
mode do not run the boot action or republish inventory. Create's existing
separate inventory/provisioning steps stay in place, and Reset with start
(which starts through create) needs the same explicit inventory step: it
proves the agent closed but does not repin.

Existing seed images are immutable lifecycle artifacts: updating host code
cannot add these contents to them. Recreate a throwaway acceptance Machine
through the normal Template flow before testing this change. An old seed
that leaves the agent open fails managed start and is stopped by it. There
is no automatic seed rewrite or in-guest repair through exec.

Passwordless server accounts still retain cloud-init's passwordless sudo.
Removing it would remove their administration path and needs a separate
administration decision. This amendment closes agent execution and refreshes
SSH identity; it does not remove the existing agent file-open authority
([ADR 0025](0025-host-key-without-agent-file-reads.md)). The transient flag,
sealed-base digest verification and lifecycle overlay remain unchanged.
Software contracts cover boot ordering, refused readiness and two distinct
SSH keys. Transient file cleanup and the complete guest boot still need
Nitro acceptance.
