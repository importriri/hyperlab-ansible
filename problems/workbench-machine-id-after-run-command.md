# The sealed image kept a machine-id

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the Workbench contract.
Verified on Nitro: `arch-dev-vfio` sealed as `arch-dev-20261003`, imported
and validated.

## Symptom

With users removed by `userdel`, the third seal of `arch-dev-vfio` completed
generalization and was refused by the leftover scan:

```text
workbench: the generalized image still holds: /etc/machine-id is not empty
```

As designed, the staging was removed, the entry stayed `candidate` and the
domain stayed untouched.

## Root cause

`virt-sysprep` runs its operations first, then its customizations in
command-line order. The `machine-id` operation emptied the file, then the
`--run-command` that removes the users ran inside the guest. Running a
command in a systemd guest can write a machine-id again, and nothing
emptied it afterwards.

## Fix

The last customization of the seal is now `--truncate /etc/machine-id`, after
every command and delete. Arch generates a new machine-id on the first boot
of each Machine. The scan is unchanged: it still refuses any machine-id other
than empty or `uninitialized`.

## Regression proof

`tests/workbench_contract.py` requires `--truncate /etc/machine-id` as the
last arguments of `virt-sysprep`, after `--run-command`.
