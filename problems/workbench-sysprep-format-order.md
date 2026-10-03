# The first Workbench seal failed: virt-sysprep refused the argument order

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the Workbench contract. The
physical seal on Nitro is pending.

## Symptom

The first `workbench-seal.yml` run against `arch-dev-vfio` copied the disk and
then stopped:

```text
workbench: virt-sysprep failed: If reporting bugs, run virt-sysprep with
debugging enabled and include the complete output: | | virt-sysprep -v -x [...]
```

The seal behaved as designed: the staging was removed, nothing reached the
image store and the domain was untouched. The message itself said nothing
useful.

## Diagnosis

`libguestfs-test-tool` passed on the host, so the appliance was not the
problem. The same arguments with `--dry-run`, which opens the disk read-only,
gave the real error:

```text
virt-sysprep: error: --format parameter must appear before -a parameter
```

## Root cause

Two faults in `tools/workbench.py`:

1. it passed `-a <image> --format qcow2`; `virt-sysprep` applies `--format`
   only to the `-a` options that follow it and refuses the reverse order;
2. on failure it kept only the last lines of the tool's output, which for
   `virt-sysprep` are its advice on reporting bugs, not the error.

The contract's `virt-sysprep` stand-in accepted any order, so it could not
catch the first fault.

## Fix

`--format qcow2` now precedes `-a`. A failing tool is reported by the lines
that name an error, without the bug-report advice. The stand-in refuses the
wrong order exactly as the real tool does.

## Regression proof

`tests/workbench_contract.py`: the stand-in rejects `--format` after `-a`, the
source pins the corrected call, and `failure_detail` keeps a real
`virt-sysprep` error line while dropping the advice. Restoring the old order
fails the contract.
