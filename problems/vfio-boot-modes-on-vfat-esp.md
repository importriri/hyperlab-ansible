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
to another mode does not change it. The one exception is the DOS read-only
attribute: such a file reads without its write bits, and a chmod that gives
back every write bit the mount allows clears the attribute (the kernel's
`fat_sanitize_mode` and `fat_make_attrs`). A boot file carrying it changes
once, on the first apply, and not after. Nitro's `findmnt -T /boot` shows
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
  `fmask` and one `dmask`, a `dmask` that lets group or others write a
  boot directory (and so create, remove or replace a boot entry), files
  owned by a uid or gid other than root's, a mode that lets group or
  others write a boot entry, or a findmnt answer that is not one
  filesystem.

The role then asserts that the answer is a `0NNN` string before the first
write under `/boot`, so no other value reaches a `mode:` argument.

The mode is not loosened: on Nitro the files already read `0755`, and the
role now only stops asking for what the mount cannot give. A mount that
would let a user other than root rewrite the kernel command line stops the
role before it writes anything under `/boot`.

## Regression proof

`tests/vfio_boot_esp_mode_contract.py` runs the tool on findmnt documents,
the first using the reviewed Nitro mount options (`0755`), with the other vfat masks,
`showexec`, the filesystems that keep modes and every refusal above,
`dmask=0000`, `0002`, `0020` and a missing `dmask` among them. It requires
every `vfio_boot` task that writes under `/boot` with a mode to use the
decided one, findmnt on exactly the directories those tasks write into,
both reads in check mode, and the reads and the shape assertion before the
first write. Against the previous role: `the mode wanted where the
filesystem keeps modes is not 0644`, and with the defaults in place:
`'Install the boot profiles' writes /boot/loader/entries/{{ item.file }}
with a fixed mode '0644', not the one the ESP keeps`. The mutations are in
`tests/MUTATIONS.md`.

The same discovered contract now executes the four parsed production
decision tasks, in their production order, with real `ansible-playbook`
on explicit localhost inventory and a local connection. It loads the real
defaults and overrides only the fixture dependencies (repository root,
Python interpreter and findmnt executable), plus the wanted mode in one
case. A fake findmnt records its argv and returns synthetic documents;
the real mode tool receives the real loop/stdin expression. Only the two
read commands, the set_fact and the shape assertion are selected from the
role, with their modules and command arguments validated before execution.
No complete role, cryptsetup, boot writer, handler or brick stamp is included.

In normal mode and `--check`, Ansible must publish a string `0755` for vfat
with `fmask=0022,dmask=0022`, the default string `0644` for ext4, and string
`0600` for an ext4 request of that mode. An additional Ansible assertion
checks the fact's type and value. Every run must call findmnt exactly once
for each directory with the reviewed `-J/-T/-o` arguments and report zero
changed tasks. Unsafe `dmask=0000`, different mount targets and different
mount options must each stop at `Decide the file mode the ESP keeps`, with
the tool's deliberate diagnostic and rc 2, before publishing any fact or
reaching the success assertion. A crash, timeout, missing tool or transport
error fails the contract.

Each subprocess has private temporary Ansible configuration and state, a
time limit and process-group cleanup on timeout. Fixture overrides use
extra vars because `vars_files` outrank play variables; a preceding Ansible
assertion verifies the effective executable and repository paths before
either command can run. Temporary plays, callbacks, programs and traces
are removed even on failure. HOME is private too, and Python derives its
user site from HOME, so the parent's user base (`PYTHONUSERBASE`) is passed
on: CI installs ansible with `pip install --user`, and without it that
ansible-playbook cannot import `ansible`, prints no report and fails the
contract. A first check compares the child's user site with the parent's.
Runtime checks precede the existing textual
role guards: corrupting stdin, publishing a fixed mode, skipping probes
in check mode or omitting a directory is caught through execution first.
The observed failures and restored passes are recorded in `tests/MUTATIONS.md`.

## Not covered

The other changes in that `changed=12` run were outside `/boot` and are
not explained here. The apply itself is to be seen on Nitro: `--check
--diff` must list no `vfio_boot` mode change, and a second apply must
report `changed=0`.

The fixtures prove the decision wiring with synthetic observations, not
physical ESP observations, file writes, chmod behaviour or bootability.
The nested no-GPU apply skips these tasks, so its second `changed=0` is
not ESP execution evidence. Full render and nested verification remain
required, and Nitro convergence still needs check/apply/apply of the same
accepted host target followed by actual boot-file mode readback. Predator
must repeat that procedure with the same frozen commits and its own mount
observations; neither synthetic filesystem fixture establishes hardware
compatibility.
