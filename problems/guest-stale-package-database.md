# Installing the Workspace Shell failed on a guest with a stale package database

Author: [importriri](https://github.com/importriri).

Status: corrected in source and pinned by the guest workspace shell contract.
The first physical run on `arch-dev-vfio` failed safely; the corrected run is
pending.

## Symptom

The first run of `guest-arch-dev-vfio.yml` with the Workspace Shell stopped at
"Install the official Hyprland guest stack":

```text
failed retrieving file 'libdwarf-1:2.3.2-1-x86_64.pkg.tar.zst' ... 404
error: failed to commit transaction (failed to retrieve some files)
Errors occurred, no packages were upgraded.
```

`quickshell`, `ttf-ibm-plex` and their dependencies were new to the guest.
Nothing was installed and the guest stayed as it was.

## Root cause

The guest's pacman sync database was older than its mirrors. The role asked
for new packages at the versions that old database named, and the mirrors had
already replaced them. The role had only ever installed packages the guest
already had, so the stale database never mattered before.

Refreshing the database alone would not be a fix: on Arch, `pacman -Sy`
followed by an install is a partial upgrade, which the distribution does not
support and which is especially risky in the VFIO guest, where the kernel,
the NVIDIA module and the initramfs must agree.

## Fix

The role first brings the whole system to one current state
(`update_cache: true`, `upgrade: true`) and only then installs its packages
against that fresh database. The sync reports a change only when packages
changed, so a second run stays at `changed=0`.

The first version of this fix put `name`, `update_cache` and `upgrade` on one
pacman task. The module refuses that combination ("parameters are mutually
exclusive: name|upgrade") before touching the guest, so it had to be two
tasks. The contract now pins the split and its order.

After a run that upgraded the kernel or NVIDIA, reboot the guest before
graphical acceptance, as in
[`guest-package-upgrade-recovery.md`](guest-package-upgrade-recovery.md).

## Regression proof

`tests/guest_workspace_shell_contract.py` requires a full system sync task, without
`name`, before the install task.
