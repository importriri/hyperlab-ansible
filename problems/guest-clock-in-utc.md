# A Machine's clock read two hours behind the host

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the workstation guest contract.
The physical recheck on `dev-01` is pending.

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

## Regression proof

`tests/workstation_guest_contract.py` requires the zone to be read on the
controller, validated before it is applied, and applied with
`community.general.timezone`, and checks the name pattern.
