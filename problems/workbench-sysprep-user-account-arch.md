# virt-sysprep could not remove users from an Arch guest

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the Workbench contract.
Verified on Nitro: `arch-dev-vfio` sealed as `arch-dev-20261003`, imported
and validated.

## Symptom

With the argument order fixed, the second seal of `arch-dev-vfio` stopped in
generalization:

```text
workbench: virt-sysprep failed: virt-sysprep: error: libguestfs error:
aug_get: no matching node
```

As designed, the staging was removed and the domain stayed untouched.

## Diagnosis

Read-only `--dry-run` runs isolated the operation:

- `--operations defaults` completed every operation;
- `--operations user-account` alone failed with the same error;
- the guest's `/etc/login.defs` does define `UID_MIN 1000` and
  `UID_MAX 60000`.

## Root cause

The `user-account` operation reads `UID_MIN` and `UID_MAX` from
`/etc/login.defs` through an Augeas lens. That lens cannot parse Arch's
current `login.defs`, so the lookup finds no node even though the values are
there.

## Fix

The Workbench no longer asks `virt-sysprep` for `user-account`. It runs the
default operations and removes every account with a UID from 1000 to 59999,
the range `login.defs` declares, with the guest's own `userdel -r` inside the
copy, falling back to `userdel` when a home is already gone. The home
deletions stay, and the leftover scan still refuses an image that keeps a
user account or a home directory.

## Regression proof

`tests/workbench_contract.py` requires `--operations defaults` without
`user-account` and the `userdel` command over the ordinary UID range. The
command itself was exercised against a sample `passwd`: it selects the
ordinary users and leaves `root` and `nobody` alone.
