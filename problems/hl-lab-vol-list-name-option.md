# The lab host tool asked virsh for an option it does not have

Author: [importriri](https://github.com/importriri).

Status: corrected; covered by `tests/hl_lab_contract.py`.

## Symptom

The first real `tools/lab/hl_lab.py create` on Nitro defined the network and
the pool, then stopped:

```text
hl-lab: virsh vol-list hl-lab-pool --name: error: command 'vol-list' doesn't support option --name
```

## Cause

`net-list`, `pool-list` and `list` accept `--name`; the installed virsh's
`vol-list` does not, and prints a `Name  Path` table instead. The contract's
fake libvirt answered `vol-list --name` like the other listings, so it
passed a call the real virsh refuses.

## Fix

`volumes()` reads the table's first column after its two header lines;
`create` and `destroy` use it. The fake libvirt now answers `vol-list` as
the real one does: `--name` is an error, and the answer is the table.

## Regression proof

The contract runs `create` and `destroy` against the faithful fake and
checks `destroy` deletes exactly the volumes in the table. Against the
previous tool it fails with the same error as Nitro.
