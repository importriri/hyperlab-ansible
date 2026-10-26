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

## Fix

- `provision_steps()` reads the generated spec with `read_generated_spec()`,
  the reader `withdraw` uses, and requires it to equal
  `project_vm_spec(record)`. A missing spec is "not projected"; a link, an
  unreadable or malformed file and any difference are refusals.
- The registry command is `["/usr/local/bin/privatestack-machine-provision",
  "{domain}"]`; the runner accepts exactly `[PROVISION, NAME]` on NAME's own
  generated spec and keeps pinning that spec's digest from launch to run.
- The provisioner takes NAME alone and matches every step against its exact
  reviewed argv: the host playbooks with `-K` and `guest_spec` of NAME's
  projection, one guest key, the inventory of NAME under the runtime
  directory, the Template's mapped profile (the set equal to hyperlabctl's
  table) for both passes, `guest-close-access.yml` last. Before the first
  step it checks every playbook as a regular file directly in the real
  `playbooks/` directory, with `lstat`, so no link is followed.
- SIGTERM and SIGHUP raise a cancellation, SIGINT stays `KeyboardInterrupt`.
  The running playbook is terminated first, and the hash file is created
  and removed with these signals blocked, so a second signal cannot skip
  its removal. The exit status is 128 plus the signal.

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
with 128 plus the signal, no later step, no hash file and no playbook left.
`tests/host_operation_lifecycle_contract.py` refuses every other provisioner
argv. `tests/host_operation_integration_contract.py` runs the real bridge,
runner and provisioner together. The mutations are in `tests/MUTATIONS.md`.
