# Machine provisioning trusted names where it needed files and signals

Found while finishing the provisioning half of ADR 0017, on `main` at
c1b64d7.

## What was wrong

- `hyperlabctl machine provision-steps NAME` checked only that
  `vm-specs/.generated/NAME.yml` was a regular file. A spec edited by hand
  after `project` (more memory, another device or network profile) was
  provisioned as if it were the Machine's projection, although the record
  is the authority and the spec only derived from it.
- The provisioner validated a step by the arguments that began with
  `playbooks/`. Any other argument passed unseen: `ansible-playbook` takes
  several playbooks, so a step
  `ansible-playbook playbooks/vm-guest-inventory.yml /tmp/other.yml -K ...`
  was accepted and would have run `/tmp/other.yml`, and so were another
  inventory, extra variables and any `playbooks/guest-*.yml` as the profile,
  mapped to the Template or not. Playbook files were never looked at: a
  missing `guest-close-access.yml` was found only after the domain had been
  created, the inventory published and the profile applied, and a playbook
  replaced by a link was followed.
- The registry resolved `machine.provision` to
  `privatestack-machine-provision --spec SPEC NAME`, so the spec path was an
  argument the runner had to compare instead of something the provisioner
  derives from the name.
- The provisioner handled only Ctrl-C. SIGTERM, which a stopped operation
  unit sends, killed it at once, so a workstation's password hash file
  stayed in `$XDG_RUNTIME_DIR/hyperlab/provision/` and the running playbook
  went on alone. SIGHUP was not handled either; the runner ignores SIGHUP
  for itself before it starts the provisioner, and an ignored disposition
  survives `exec` (`subprocess` restores only SIGPIPE, SIGXFZ and SIGXFSZ),
  so the provisioner silently inherited the ignore and kept waiting on a
  terminal that had gone.

An independent review of the first fix found three more:

- The spec was compared with the projection by plain equality. In Python
  `True == 1` and `2048.0 == 2048`, so a spec saying `vcpus: true` or
  `memory_mb: 2048.0` passed as the projection of `1` and `2048`, types the
  spec's own readers refuse.
- The provisioner took the profile from the plan's first profile pass and
  checked only that it was one of the reviewed profiles. Another
  Template's reviewed profile, the same in both passes, was accepted.
- A stopped operation gives its command three seconds before the runner
  kills it, and the provisioner gives its playbook ten before it removes
  the hash file. A playbook slow to end got the provisioner killed with the
  file in place. The signal tests drove the provisioner alone, with a
  playbook that ended at once, so they never saw the runner's deadline. A
  stopped runner also sends more than one signal (its PTY hangs up, it
  terminates the provisioner, systemd signals the whole unit), and one of
  them arriving between the first cancellation and the removal could still
  skip it.

## Fix

- `provision_steps()` reads the generated spec with `read_generated_spec()`,
  the reader `withdraw` uses, and requires it to equal
  `project_vm_spec(record)` with the same type at every level
  (`same_document()`). A missing spec is "not projected"; a link, an
  unreadable or malformed file and any difference are refusals.
- The registry command is `["/usr/local/bin/privatestack-machine-provision",
  "{domain}"]`; the runner accepts exactly `[PROVISION, NAME]` on NAME's own
  generated spec and keeps pinning that spec's digest from launch to run.
- The provisioner takes NAME alone and matches every step against its exact
  reviewed argv: the host playbooks with `-K` and `guest_spec` of NAME's
  projection, one guest key, the inventory of NAME under the runtime
  directory, for both passes the profile that the Template of the record
  read with `hyperlabctl machine show NAME` maps to (a table equal to
  hyperlabctl's), `guest-close-access.yml` last; the record also decides
  whether the steps are a server's or a workstation's. Before the first
  step it checks every playbook as a regular file directly in the real
  `playbooks/` directory, with `lstat`, so no link is followed.
- SIGTERM and SIGHUP raise a cancellation, SIGINT stays `KeyboardInterrupt`.
  The running playbook is terminated first (SIGKILL after ten seconds,
  `PLAYBOOK_GRACE`), and the hash file is created and removed with these
  signals blocked. Only the first of them ends the run; the later ones are
  ignored, so none can skip the removal. The exit status is 128 plus the
  first signal.
- The runner keeps three seconds (`STOP_GRACE`) for every action except
  `machine.provision`, which gets thirty (`PROVISION_STOP_GRACE`): longer
  than the provisioner's whole escalation, inside the user manager's
  default 90 s stop timeout.

## Test

`tests/c10_machine_creation_plan_contract.py` edits a real projected spec
field by field and requires a refusal with the registry and the specs
unchanged; it also compares the real `provision-steps` output with the
`ansible-playbook` commands parsed out of `docs/first-machine.md`.
`tests/host_machine_provision_contract.py` runs the real provisioner over
real inert playbook files and refuses each tampered plan and each missing,
linked or non-regular playbook with no call and no prompt; it runs the
provisioner over the real CLI with an edited spec (no call), and in its own
process on a PTY it delivers SIGINT, SIGTERM and SIGHUP after the first
profile pass announces itself with the hash file in place: the run ends
with 128 plus the signal, no later step, no hash file and no playbook left;
with more signals sent while the playbook takes two seconds to end, the
status still names the first and the file is gone. The real CLI also
refuses `vcpus: true` on a one-vCPU Machine and `memory_mb: 2048.0`, and a
plan running another Template's reviewed profile in both passes is refused
with no call and no prompt.
`tests/host_operation_lifecycle_contract.py` refuses every other provisioner
argv and holds every action's stop deadline.
`tests/host_operation_integration_contract.py` runs the real bridge,
runner and provisioner together, and stops the runner while the first
profile pass ignores the hangup and takes five seconds to end: the record
is interrupted and the hash file is gone. The mutations are in `tests/MUTATIONS.md`.
