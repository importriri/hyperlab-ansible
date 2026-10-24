# The boot entries changed on every apply on the vfat ESP

Author: [importriri](https://github.com/importriri).

Status: corrected in `roles/vfio_boot` and covered by
`tests/vfio_boot_esp_mode_contract.py`; to be seen on Nitro, because the
nested lab host skips `vfio_boot` (ADR 0052).

## Symptom

On 2026-10-24, `sudo ansible-playbook -i inventory.ini playbooks/lab.yml
--check --diff` on Nitro reported `changed=12`. Every change under `/boot`
was a mode change only: `vfio_boot : Install the boot profiles` and
`vfio_boot : Make VFIO the normal laboratory boot path` wanted `0644` on
the five files in `/boot/loader/entries` and on `/boot/loader/loader.conf`,
which read `0755`. A second apply could never report `changed=0` on Nitro.
Acceptance group 7 on 2026-10-06 had also ended its foundation apply with
`changed=4`.

## Cause

arch-bootstrap mounts the ESP on `/boot` as vfat. FAT stores no Unix
permissions: Linux gives every file the mode `0777` without the mount's
`fmask` bits, and without the execute bits under `showexec`, and a chmod
to another mode does not change it. Nitro's `findmnt -T /boot` shows
`fmask=0022`, so every file reads `0755`, and the role asked for `0644`
on every run.

The nested lab host did not show it: it runs the `no-gpu-passthrough`
profile, which skips `vfio_boot` altogether.

## Fix

`roles/vfio_boot` reads the mount of `/boot/loader` and
`/boot/loader/entries` with `findmnt -J -T DIR -o TARGET,FSTYPE,OPTIONS`,
also in check mode, and `tools/esp_file_mode.py` decides the mode the
boot files are written with:

- on vfat, the mode the mount gives (`0755` on Nitro);
- on ext2, ext3, ext4, btrfs or xfs, which keep modes, the role's
  `vfio_boot_file_mode` (`0644`);
- a refusal for anything else: another filesystem type, the two
  directories on different mounts or options, a vfat mount without one
  `fmask`, files owned by a uid or gid other than root's, a mode that lets
  group or others write a boot entry, or a findmnt answer that is not one
  filesystem.

The mode is not loosened: on Nitro the files already read `0755`, and the
role now only stops asking for what the mount cannot give. A mount that
would let a user other than root rewrite the kernel command line stops the
role before it writes anything under `/boot`.

## Regression proof

`tests/vfio_boot_esp_mode_contract.py` runs the tool on findmnt documents,
the first being Nitro's real one (`0755`), with the other vfat masks,
`showexec`, the filesystems that keep modes and every refusal above. It
requires every `vfio_boot` task that writes under `/boot` with a mode to
use the decided one, findmnt on exactly the directories those tasks write
into, both reads in check mode and before the first write. Against the
previous role: `the mode wanted where the filesystem keeps modes is not
0644`, and with the defaults in place: `'Install the boot profiles' writes
/boot/loader/entries/{{ item.file }} with a fixed mode '0644', not the one
the ESP keeps`. The mutations are in `tests/MUTATIONS.md`.

## Not covered

The other changes in that `changed=12` run were outside `/boot` and are
not explained here. The apply itself is to be seen on Nitro: `--check
--diff` must list no `vfio_boot` mode change, and a second apply must
report `changed=0`.
