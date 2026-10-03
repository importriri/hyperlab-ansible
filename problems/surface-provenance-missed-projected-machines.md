# The host bar read "Unresolved" over a Machine's Looking Glass window

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the surface provenance contract.
The physical recheck on `dev-01` is pending.

## Symptom

`hyperlabctl open looking-glass dev-01` showed the first Machine from the
`workstation-dev` Template with its rice and Desks, but the host bar named
the focused window **Unresolved** in the warning colour instead of **Dev**.
The GPU readout named `dev-01` correctly.

## Root cause

The launcher registers each Looking Glass window with the digest of the VM
spec it was opened from, and finds a Machine's spec in
`vm-specs/.generated/`. The read-only resolver behind the bar looked for
that spec only in `vm-specs/*.yml`, the checked-in fixtures, so for every
Machine it answered `registered-domain-spec-unavailable` and failed closed,
which is the correct reaction to what it saw.

## Fix

The resolver also reads `vm-specs/.generated/`, under three conditions:

- a generated spec counts only when it carries the `managed-machine` tag the
  projection writes;
- symlinks are ignored, as before;
- a name that matches more than one spec, for example a fixture and a
  Machine with the same name, still resolves to nothing.

The digest recorded at launch must still match, so a spec changed after the
window opened stays unresolved.

## Regression proof

`tests/surface_provenance_contract.py` resolves a projected `dev-01` to
`dev`, refuses a generated spec without the tag, and refuses a name present
both as a fixture and as a Machine.
