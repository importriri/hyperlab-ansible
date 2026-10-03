# Image import skipped its final check and kept its lock

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the image factory contract.
Verified on Nitro: `arch-dev-vfio` sealed as `arch-dev-20261003`, imported
and validated.

## Symptom

The first import of a Workbench image, `arch-dev-20261003`, reported success,
but two tasks at the end of `image-prepare.yml` were skipped:

```text
TASK [image_factory : Verify the committed image transaction before success]
skipping: [localhost]
TASK [image_factory : Release the per-image factory lock]
skipping: [localhost]
```

The separate `image-validate.yml` run passed, so the image itself was sound,
but the import never checked its own commit and left
`state/locks/image-arch-dev-20261003.lock` behind. A later prepare of the
same id would refuse to start.

## Root cause

The whole transaction ran in a block guarded by
`when: image_factory_transaction_clean`. Ansible evaluates a block's
condition again for every task inside it, `always` included. Right after
the commit, the role sets `image_factory_transaction_clean: false` to record
that the transaction is complete, so every following task of the block,
the post-commit validation and the lock release, was skipped.

A five-task playbook reproduces it: a block guarded by a variable that one
of its tasks sets to false skips both its remaining tasks and its `always`.

## Fix

Before the block, the role copies the condition into
`image_factory_new_transaction`, which nothing changes afterwards, and the
block is guarded by that copy. The same pattern already protects the guest
create transaction (`guest_create_new_transaction`).

## Regression proof

`tests/image_factory_contract.py` requires the copy before the block, the
block guarded by it, no block guarded by `image_factory_transaction_clean`,
and no later change to the copy.

## Recovery on a host that ran the old code

Every earlier successful prepare left an empty lock directory under
`/var/lib/libvirt/images/hyperlab/state/locks/`. While no prepare is
running, remove them with `rmdir`, which refuses anything that is not an
empty directory.
