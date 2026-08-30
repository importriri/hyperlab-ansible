# An interrupted Arch guest upgrade required a complete package transaction

Author: [importriri](https://github.com/importriri).

## Symptom

An Arch guest package upgrade was interrupted while the accelerated guest was
being prepared. Continuing with isolated package repairs risked leaving the
kernel, NVIDIA module, initramfs and bootloader view out of sync.

## What was wrong

Arch package upgrades are a system transaction. After interruption, repairing
only the package that was visible at the failure point does not prove that the
rest of the installed set matches the repository state or that kernel-dependent
artifacts were regenerated against that state.

That is especially unsafe in the VFIO guest, where the graphical path depends
on the kernel, NVIDIA modules and initramfs agreeing after reboot.

## Fix

Recover through a complete `pacman -Syu` transaction, then verify the
kernel-module chain rather than treating package-manager exit status as the
whole recovery.

The campaign checked DKMS state, regenerated dependency metadata and initramfs
where required, refreshed the bootloader configuration and rebooted before
continuing graphical acceptance.

## Regression proof

The guest returned with the intended kernel and NVIDIA path available and later
continued the Hyprland and Looking Glass hardware campaign.

The recovery rule is now simple: after an interrupted full Arch upgrade, do not
resume application-level provisioning until the package transaction and
kernel-module boot path are complete again.
