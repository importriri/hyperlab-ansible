# CI turned red when Debian was sealed

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the Nitro gate contract.

## Symptom

The CI run for `61e0c4c` (Debian 13 and Fedora 44 sealed) failed in the
refusal suites:

```text
fatal: [localhost]: FAILED! => {
    "msg": "M3 must remain unusable with a production manifest whose base has not been imported, checksummed and marked sealed."
```

## Root cause

`tests/guest-refusals.yml` proved that the planner refuses an unsealed image
by planning `vm-specs/debian-dev.yml` and expecting
`image debian is not sealed`. The test chose its example by name, not by
property: once `images/debian.yml` became `sealed`, the planner accepted the
spec and the expected refusal never came. `run-nitro-m9-cockpit-gate.sh` used
the same spec and pattern for its intentional refusal before host writes, and
`tests/nitro_gate_contract.py` pinned that pattern, so the gate would have
failed on Nitro the same way.

The local verification battery did not run the refusal suites, so the commit
went out green locally and red in CI.

## Fix

Both refusals now use `vm-specs/parrot-disposable.yml`, whose image `parrot`
is `not-built`, and expect `image parrot is not sealed`. The local
verification before every commit now runs the whole CI workflow, refusal
suites included.

## Regression proof

`tests/nitro_gate_contract.py` reads the spec and the expected pattern from
both the refusal suite and the gate script, opens the spec's image manifest
and requires that image not to be sealed and the pattern to name it. Sealing
Parrot one day fails that contract with a message that says to pick another
unbuilt image, instead of failing CI in the refusal suite.
