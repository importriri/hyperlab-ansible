# Acer Nitro platform controls

The optional `nitro_sense` brick restores selected NitroSense-class controls on
Linux without making a reverse-engineered platform driver part of the normal
hypervisor target. The role first inspects the generic kernel platform-profile
ABI. When the requested profile already exists, it retains `acer_wmi` and only
persists that native profile. It never installs Linuwu-Sense merely to duplicate
an in-tree capability.

The replacement path uses Linuwu-Sense at the full commit
[`73a25ec243a44ba2b1703e8d0a76fa2735062506`](https://github.com/0x7375646F/Linuwu-Sense/tree/73a25ec243a44ba2b1703e8d0a76fa2735062506).
Upstream describes the module as early-stage, reverse-engineered code that
replaces `acer_wmi` and issues low-level WMI calls. That risk is why the role is
not imported by `foundation.yml` or `lab.yml` and why
`nitro_sense_out_of_tree_enabled` defaults to `false`.

The opt-in grants permission to replace the driver; it does not force a
replacement that is unnecessary. When the requested native profile exists,
both fan values remain at firmware automatic (`0,0`) and LED management is
disabled, the role keeps `acer_wmi` even if the opt-in was supplied. A manual
fan value or an enabled LED mode makes the native path insufficient and still
requires the explicit opt-in.

## What is replaced

The in-tree `acer_wmi` module normally owns Acer hotkeys, radio controls and
platform integration. The out-of-tree module registers the same `acer-wmi`
platform driver identity, so both drivers cannot own the device at once. After a
successful isolated build and DKMS install, the role unloads `acer_wmi`,
blacklists it for later boots and loads `linuwu_sense`.

If that transition fails, the role removes its boot policy, unloads the
replacement and reloads `acer_wmi`. A failed post-load check is never allowed to
leave the host intentionally committed to a driver that did not expose the
documented Nitro fan interface.

The most visible regression is loss of function keys. Radio toggles, brightness
handling, platform profiles or suspend behavior can also change because they
share the same platform driver. Keep an SSH session or a text console available
during the first hardware run.

## Documented interfaces

The role writes only interfaces documented by the pinned upstream source or the
generic kernel ABI:

- `/sys/firmware/acpi/platform_profile_choices`
- `/sys/firmware/acpi/platform_profile`
- `/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/nitro_sense/fan_speed`
- `/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb/per_zone_mode`
- `/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb/four_zone_mode`

Every optional node is checked before use. Enabling an LED mode on a model whose
pinned DMI quirk does not declare a four-zone keyboard is refused before package
installation. The boot service also fails visibly if a requested documented
node disappears after a kernel or module update.

## Conservative policy

The defaults request `balanced`, leave both fans in firmware automatic mode
(`0,0`) and do not manage keyboard lighting. The source build uses
`linux-hardened-headers`, matching the stage-1 kernel contract. DKMS identity is
derived from the pinned commit, while the idempotence stamp records the complete
requested commit, resolved commit, DKMS version and running kernel.

The external replacement is selected only with:

```bash
ansible-playbook -K playbooks/nitro-sense.yml \
  -e nitro_sense_out_of_tree_enabled=true
```

Review [`nitro-sense-procedure.md`](nitro-sense-procedure.md) before the first
hardware apply.

## Source and licensing boundary

This repository remains MIT-licensed and does not vendor Linuwu-Sense source.
The optional role fetches the reviewed upstream commit on the target and builds
it under upstream's GPL-3.0 license. Keep that upstream license and source
obligations with any redistributed source or module build; the pin is a build
identity, not a relicensing of the driver.

## Recovery and rollback

The supported rollback is idempotent and restores the in-tree module:

```bash
ansible-playbook -K playbooks/nitro-sense.yml \
  -e nitro_sense_state=absent
```

It stops and removes the settings service, unloads `linuwu_sense`, removes the
managed DKMS version and source trees, removes both boot-policy files and loads
`acer_wmi`. It also removes the brick stamp so a later installation must pass
the full prerequisite and preflight path again. Destructive cleanup requires
the role's exact ownership markers; an unmarked source tree, DKMS directory or
service path is refused rather than claimed.

If graphical hotkeys fail but a TTY or SSH shell still works, run the rollback
playbook first. If Ansible itself is unavailable, use the narrow emergency path
below from a root shell:

```bash
systemctl disable --now nitro-sense-apply.service || true
modprobe -r linuwu_sense
rm -f /etc/modules-load.d/linuwu_sense.conf
rm -f /etc/modprobe.d/nitro-sense-blacklist-acer_wmi.conf
dkms remove -m linuwu_sense -v 73a25ec243a4 --all || true
depmod -a
modprobe acer_wmi
test -d /sys/module/acer_wmi
```

Do not reboot until the last test succeeds. The emergency commands are a
recovery fallback; rerun the rollback playbook afterward so repository-owned
source, service and stamp state is reconciled completely.

## Known limits

- Not every Acer Nitro model is supported. The role accepts only exact DMI
  products present in the pinned upstream allowlist.
- Some Nitro models have no physical thermal-profile selector. When the generic
  platform-profile ABI exists, select the profile through that ABI instead.
- The pinned upstream source classifies `Nitro AN515-55` as a legacy quirk: it
  promises the Nitro fan interface but does not promise platform-profile or RGB
  capability. Keep `nitro_sense_thermal_profile_required=false` for that path
  unless hardware proves otherwise.
- Four-zone keyboard control exists only on the explicitly allowlisted models.
  Per-key RGB is not supported upstream and is not emulated by this role.
- A future hardened kernel can change the out-of-tree module API. DKMS success
  is not assumed; the role compiles the exact pin for the running kernel before
  touching `acer_wmi`.
