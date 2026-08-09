# A check-mode playbook lost the brick variables

Author: [importriri](https://github.com/importriri).

## Symptom

A focused `guest_desktop_hyprland` check failed in `brick_guard` because
`brick_stamp_dir` was undefined. The role looked broken even though the normal
playbooks had already used the same brick graph successfully.

## What was wrong

The temporary playbook lived in `/tmp`. Ansible resolved repository-scoped
`group_vars/all/` from the playbook/inventory context, so the ad-hoc harness did
not load the brick variables from the checkout.

The role was not the failure. The test harness had changed the variable-loading
context.

## Fix

Keep focused test playbooks inside the repository root, or provide an inventory
context that deliberately loads the same variables as the real playbooks.

## Regression proof

The corrected check asserted that `brick_stamp_dir`, `brick_requires` and
`brick_playbooks` were present before mounting the role. Check mode then passed,
and the two real applies converged with the second pass at `changed=0`.
