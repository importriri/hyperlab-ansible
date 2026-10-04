# ADR 0017 - The shell creates a Machine through the reviewed bridge and one durable operation

## Context

[`../first-machine.md`](../first-machine.md) creates a Machine by hand:
`hyperlabctl machine create` and `project` without privilege, then
`vm-create.yml` and `vm-guest-inventory.yml` with `-K`, and for a
workstation the profile playbook twice, the first time with a password hash
read from a file that lives in memory and is deleted after the run.

Roadmap milestone 5 asks for the same steps from the shell's Machines
destination. The shell is presentation: it never calls a hypervisor,
`sudo` or a shell, and it names reviewed actions that something else
performs ([`../hyperlab-shell.md`](../hyperlab-shell.md)). Three things in
the manual path must not move into the shell: the privilege prompt, the
workstation password and the choice of the guest SSH key.

## Decision

Creation is split along the existing boundary.

- **Plan.** `privatestack-machine-actions create-plan` returns
  `hyperlabctl machine create-plan`: the ready Templates with what each one
  allows (lifecycle, networks, resource profiles), the resources every
  profile resolves to, the custom limits (disk at least the sealed image,
  memory at least the image floor, vCPUs at most the host's), whether the
  Template needs a password, and the guest key's fingerprint. Every value
  comes from the same factory code that creates the record; the shell only
  shows them.
- **Intent.** `privatestack-machine-actions create TEMPLATE NAME NETWORK
  PROFILE [MEMORY VCPUS DISK]` takes positional, validated values only. It
  runs `hyperlabctl machine create` and `project`, which refuse anything the
  Template forbids, and answers with structured JSON. A refusal leaves no
  record behind.
- **Provision.** It then launches the durable operation `machine.provision`
  through `privatestack-operation`, the runner that already owns managed
  start and shutdown. The command is never taken from the caller: the
  runner resolves it through the action registry to
  `privatestack-machine-provision NAME` and pins the projected spec's
  digest. The provisioner asks `hyperlabctl machine provision-steps NAME`
  for the documented steps, derived from the Machine record, its projected
  spec and its Template, accepts only `ansible-playbook` runs of reviewed
  playbooks, and runs them in order inside the operation's private
  terminal.
- **Privilege.** Each `-K` playbook asks for the become password in that
  terminal, exactly as by hand. Nothing caches it.
- **Password.** For a Template whose profile needs one, the provisioner asks
  for it twice without echo in the same terminal, turns it into a SHA-512
  crypt hash with `openssl passwd -6 -stdin`, writes the hash to a 0600 file
  below `$XDG_RUNTIME_DIR/hyperlab/provision/`, passes the file to the first
  profile pass and deletes it in every outcome. The password never reaches
  QML, an argument vector, the operation record or the transcript.
- **Key.** The guest key is the host's one HyperLab guest key,
  `~/.ssh/hyperlab_ed25519.pub`: one public ed25519 line, validated before
  use. The shell shows its fingerprint and offers no choice; the private key
  is never read.

## Consequences

- The shell gains a Create view without any new authority: everything it
  submits is re-validated by the factory, and everything privileged runs in
  the operation terminal under the operator's own become prompt.
- A creation asks for the become password once per privileged playbook:
  twice, for `vm-create.yml` and `vm-guest-inventory.yml`. The profile
  passes of a workstation reach the guest over SSH and need no become
  password on the host.
- A failed step leaves the Machine record, the projected spec and possibly
  the domain in place, exactly as the manual path would; the operation
  window shows the step and its output, and the next step is the same
  documented command.
- Template profile playbooks are a reviewed table in `hyperlabctl`. A
  workstation Template without an entry is not offered for creation.
- Disposable Machines and the GPU lease (roadmap 5 and 5b) reuse this flow
  when their Templates allow them.
