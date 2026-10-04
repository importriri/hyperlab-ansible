# A Machine's clock read two hours behind the host

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the workstation and guest
contracts. The physical recheck on `dev-01` is pending; the first-boot zone
of a server Machine is pending on Nitro too.

## Symptom

The Workspace Shell of `dev-01` showed 21:09 while the host bar showed
23:09.

## Root cause

Not a late clock: the same instant in two time zones. Arch cloud images run
in UTC and nothing in the guest roles set a time zone, so every guest read
UTC while the host, installed by `arch-bootstrap` with a local time zone,
read local time.

## Fix

`workstation_access` reads the hypervisor's `/etc/localtime` on the
controller, takes the IANA name it points to and sets the same time zone in
the guest. `workstation_access_timezone` overrides it with an explicit name.
A host whose `/etc/localtime` names no zone, or a name outside the IANA
pattern, stops the run with a clear message instead of guessing.

That fix reached only workstations: a server Machine never runs the profile
playbook, so `srv-01` still ran in UTC. The `guest` role now resolves the
same zone when it creates a new Machine and writes it as `timezone:` in the
NoCloud user data, so every Linux Machine starts in the host's zone on its
first boot. `guest_cloud_init_timezone` overrides it. A host without
`/etc/localtime` runs in UTC, so the Machine does too; a regular file or a
name outside the pattern refuses before any seed is written. The zone is
read only for a new transaction and is not part of the managed state, so
validating an existing domain never compares it and a later change of the
host zone does not invalidate older Machines.

## Regression proof

`tests/workstation_guest_contract.py` requires the zone to be read on the
controller, validated before it is applied, and applied with
`community.general.timezone`, and checks the name pattern.
`tests/guest_contract.py` renders the user data with a zone, requires the
host zone to be read without following the link, validated before the seed
is rendered, only for a new transaction, and kept out of validation and
state, and checks the pattern against injection attempts.
