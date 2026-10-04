# ADR 0025 - Pinning a Machine's SSH host key without agent file reads

Status: proposed. The operator chooses before any of it is built; today the
host key is read through QEMU Guest Agent file calls.

## Context

A new Machine's SSH host key is read by the host through QEMU Guest Agent
(`guest-file-open/read/close` on `/etc/ssh/ssh_host_ed25519_key.pub`) and
pinned, so the first SSH connection never trusts a key shown on the network
([`../../problems/guest-host-key-unknown-after-first-boot.md`](../../problems/guest-host-key-unknown-after-first-boot.md)).
Three things press on that path:

- a distribution may block the agent's file calls or confine the agent
  ([`../../problems/fedora-host-key-through-agent.md`](../../problems/fedora-host-key-through-agent.md));
- roadmap milestone 10 restricts the agent to the calls HyperLab uses. The
  agent filters by call, not by mode: allowing `guest-file-open` also allows
  opening a file for writing, which truncates it, even with
  `guest-file-write` blocked;
- a disposable Machine generates new host keys at every start
  ([ADR 0018](0018-disposable-discards-on-stop.md)) and needs a fresh pin each
  time.

## Options

**A. The serial console, logged by the host.** cloud-init prints the new
host keys to the console between fixed markers
(`-----BEGIN SSH HOST KEY KEYS-----`). The domain's serial port gets a
host-side log file (`<log file=… append='off'/>`), root-owned in the store;
the inventory step takes the one ed25519 line from the first block after the
domain started and pins it. The channel is the hypervisor's, not the
network's, like the agent. No agent call is needed, so the agent can drop
every `guest-file-*` call. Cost: the console log must be bounded and parsed
strictly; a guest root process could write a fake block, which is the same
trust as the agent reading a file that guest root controls.

**B. Keep the agent, open only what is needed.** Ship an explicit agent
configuration in the image (`--allow-rpcs` with `guest-ping`, `guest-info`,
`guest-sync*`, `guest-shutdown`, `guest-network-get-interfaces` and the three
`guest-file-*` calls) and, where SELinux confines the agent, a reviewed rule
for the public host keys only. Cost: open-for-write remains possible through
`guest-file-open`; one more artefact per distribution.

**C. Host-generated host keys.** The host generates the Machine's ed25519
host key and passes it in the NoCloud seed (`ssh_keys:`), pinning the public
half before the first boot. Nothing is read back from the guest, and a
disposable Machine keeps one key across starts. Cost: the private host key
exists on the host, in the root-owned seed directory, for the life of the
Machine; that changes who owns the guest's identity.

## Recommendation

A. It works the same on every distribution, needs nothing from the agent, and
lets milestone 10 remove the agent's file calls entirely, which also closes
the open-for-write gap of option B. C is the better fit for disposable
Machines if the operator accepts host-held host keys; it can follow A.

## Consequences if accepted

- The inventory step gains a console source beside the agent, chosen by
  the image manifest; the agent path stays until every image is moved.
- The domain XML gains a console log path, so the managed XML contract and
  existing domains need a reviewed migration.
