# Hyprland autologin executable validation rejected a valid path

## Symptom

The Nitro `arch-dev-vfio` guest reconciliation stopped at the optional Ly
autologin guard even though the configured executable was the absolute path
`/usr/bin/Hyprland`.

The guard used:

```yaml
guest_desktop_hyprland_autologin_exec is match('^/[^[:space:]]+$')
```

## Cause

Ansible's Jinja `match` test uses Python regular-expression semantics. The
POSIX-style `[:space:]` class inside that expression did not express the
intended no-whitespace rule and rejected the reviewed absolute executable.

This was a validation defect, not a missing Hyprland binary and not a guest
runtime failure.

## Fix

Use the Python-regex form directly:

```yaml
guest_desktop_hyprland_autologin_exec is match('^/\\S+$')
```

`tests/workstation_guest_contract.py` now pins `/usr/bin/Hyprland`, checks the
Python-regex behavior and refuses the obsolete guard.

## Verification

On the Nitro:

- the root cause was reproduced before the edit;
- the targeted workstation guest and Nitro campaign contracts passed;
- the guest VFIO playbook syntax check passed;
- the full repository verifier passed;
- the first real guest pass reconciled the updated desktop files;
- the second real guest pass completed with `changed=0`, `unreachable=0` and
  `failed=0`;
- the subsequent host/guest and interactive Looking Glass hardware gates passed.

The correction changes validation only. It does not relax the requirement for
an absolute executable or permit whitespace in the configured path.
