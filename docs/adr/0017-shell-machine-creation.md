# ADR 0017 - The shell creates a Machine through the reviewed bridge and one durable operation

Status: proposed. No record accepts it; what is built of it is listed
under "Implementation status" below.

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
- **Intent.** `privatestack-machine-actions create TEMPLATE NAME LIFECYCLE
  NETWORK PROFILE [MEMORY VCPUS DISK]` takes positional, validated values
  only. It
  runs one staged `hyperlabctl machine create --project`
  ([ADR 0053](0053-withdraw-machine-intent.md), proposed), which refuses
  anything the Template forbids, writes the projected spec first and
  publishes the Machine record last under the registry lock. It answers
  with structured JSON, and the bridge launches nothing unless that answer
  names the Machine, its `vm-specs/.generated/NAME.yml` spec and the
  record's SHA-256 digest. A refusal leaves no record behind.
- **Provision.** It then launches the durable operation `machine.provision`
  through `privatestack-operation`, the runner that already owns managed
  start and shutdown. The command is never taken from the caller: the
  runner resolves it through the action registry and accepts exactly
  `["/usr/local/bin/privatestack-machine-provision", NAME]`, for a NAME
  whose spec is its own generated projection
  (`vm-specs/.generated/NAME.yml`), never a checked-in spec. It pins the
  digest of that spec's bytes in the operation record at launch and
  checks it again before it runs anything: a spec changed in between is
  a durable failure with no child started. The provisioner takes NAME
  alone and asks `hyperlabctl machine provision-steps NAME` for the
  documented steps, derived from the Machine record, its projected spec
  and its Template. `provision-steps` reads the generated spec as stored
  and refuses it unless it is exactly what the record projects to now,
  scalar types included (`true` is not `1`, `2048.0` is not `2048`): a
  missing spec, a link, an unreadable or malformed file and a spec edited
  by hand are refused alike. Before the steps, the provisioner reads the
  Machine record itself with `hyperlabctl machine show NAME`; the record's
  Template and workspace, not the plan, decide whether the steps are a
  server's or a workstation's and which profile playbook both profile
  passes run. A missing or malformed record is a refusal. The provisioner
  then holds the whole plan to the reviewed one before the first step runs
  or anything is asked: each step has its exact reviewed command (the host
  playbooks with `-K`, the profile playbook the record's Template maps to,
  `guest-close-access.yml` last), and every playbook is an existing
  regular file directly in the real `playbooks/` directory of the reviewed
  checkout, with no link anywhere on the way. Then it runs the steps in
  order inside the operation's private terminal.
- **Privilege.** Each `-K` playbook asks for the become password in that
  terminal, exactly as by hand. Nothing caches it.
- **Password.** For a Template whose profile needs one, the provisioner asks
  for it twice without echo in the same terminal, turns it into a SHA-512
  crypt hash with `openssl passwd -6 -stdin`, writes the hash to a 0600 file
  below `$XDG_RUNTIME_DIR/hyperlab/provision/` (0700), passes the file to
  the first profile pass only and deletes it in every outcome: success, a
  failed step, Ctrl-C (SIGINT), a stopped operation unit (SIGTERM) and a
  terminal that hangs up (SIGHUP). On those signals the running playbook is
  stopped first (SIGTERM, then SIGKILL after ten seconds) and reaped; the
  file is created and removed with them held back, and only the first of
  them ends the run, so the ones that follow (a stopped runner's hangup, its
  SIGTERM, systemd's signal to the unit) cannot cut the cleanup short. A
  signal that arrives while a playbook is being started is noted and raised
  only once the provisioner holds the started process, so that playbook is
  stopped and reaped too; it is not blocked in the kernel there, so the
  playbook inherits no blocked signal. A stopped
  operation gives its command three seconds before the runner kills it,
  except `machine.provision`, which gets thirty, longer than the
  provisioner's own ten-second escalation and inside the user manager's
  default 90 s stop timeout. The password never reaches QML, an argument
  vector, a child's environment, the operation record or the transcript.
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
  record ends `failed` with the step's exit status, the operation window
  shows the step and its output, and the next step is the same documented
  command. Failed provisioning is not refused intent: the creation had
  already succeeded, so nothing is withdrawn
  ([ADR 0053](0053-withdraw-machine-intent.md) covers only refused
  creations).
- Closing the operation window is not a signal: the window only observes,
  the operation keeps running and the window can be reopened.
- Limits. The checks hold when the plan is validated and when the runner
  starts: the spec and the playbooks are read again by `ansible-playbook`
  later, and a writer of the checkout between those moments is not
  detected. The Machine record holds no digest of its projection; the
  comparison recomputes the projection every time. The table of reviewed
  profile playbooks by Template is held both in `hyperlabctl` and in the
  provisioner, which cannot import it; a contract keeps the two equal. The
  thirty seconds are a bound, not a handshake: a provisioner stuck past
  them for another reason is killed. SIGKILL (or a lost
  power) cannot be handled: the hash file then stays in the runtime
  directory, which is memory, until logout or the next provisioning of the
  same Machine replaces it. The signal handling is proven with handled
  signals against inert fixture playbooks under the real runner, with
  systemd replaced; a real unit stop and a real `ansible-playbook` are
  hardware checks.
- Template profile playbooks are a reviewed table in `hyperlabctl`. A
  workstation Template without an entry is not offered for creation.
- Disposable Machines and the GPU lease (roadmap 5 and 5b) reuse this flow
  when their Templates allow them.

## Implementation status

- Built and software-verified: the plan, the staged intent, the Create
  view in the shell (`CreateMachineView.qml`) and the provisioning runner
  with its whole-plan check and its hash-file cleanup
  (`tests/c10_machine_create_plan_contract.py`,
  `tests/host_quickshell_create_view_contract.py`,
  `tests/host_machine_provision_contract.py`). These contracts run on
  fixtures, with the limits listed above.
- Not proven on hardware: no Machine has been created from the shell on
  Nitro, and a real unit stop and a real `ansible-playbook` under the
  runner have not been observed.
- Of the flows that reuse this one, a disposable Machine is offered by the
  server Templates, but what it needs after its first stop is open
  ([ADR 0018](0018-disposable-discards-on-stop.md)); the GPU lease is a
  proposal and is not built ([ADR 0019](0019-gpu-lease.md)).
