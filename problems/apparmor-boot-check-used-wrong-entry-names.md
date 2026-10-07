# Group 10 named the boot entries in the wrong case and grepped the default

Found in the review of the acceptance scripts on 2026-10-07, before group
10 ever ran on Nitro.

## What was wrong

- The script named the AppArmor entry `arch-linux-hardened-vfio-apparmor.conf`.
  `roles/vfio_boot` writes `Arch-Linux-Hardened-Vfio-AppArmor.conf`, and
  `bootctl list` on Nitro shows exactly that. "the AppArmor entry exists"
  would have failed, and `bootctl set-oneshot` would have been given an id
  the boot loader does not have.
- "the default is still the Vfio entry" grepped `bootctl status` for a
  lowercase file name that could match another line and does not match
  the real id at all.
- The one-shot reboot was offered whatever those two checks said.

## Fix

The script takes the ids exactly as the role writes them, reads the
default as the one entry `bootctl list --json=short` marks `isDefault`,
and offers the one-shot reboot only when the AppArmor entry exists and the
Vfio entry is still the default ("REBOOT NOT OFFERED" otherwise). Read on
Nitro without privilege, the new checks find the AppArmor entry and
`Arch-Linux-Hardened-Vfio.conf` as the default, and refuse the lowercase
id.

## Test

`tests/acceptance_scripts_contract.py` requires both ids to be the role's
and runs `10-apparmor-boot.sh prepare` in a pseudo-terminal against a fake
`bootctl`: the reviewed entries offer the reboot; the AppArmor entry as the
default, or a missing AppArmor entry, fail and offer nothing. It fails on
the previous script.
