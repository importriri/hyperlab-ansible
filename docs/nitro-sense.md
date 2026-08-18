# Acer Nitro platform controls

The optional `nitro_sense` brick restores selected NitroSense-class controls on
Linux without making a reverse-engineered platform driver part of the normal
hypervisor target.

The role is native-first. It inspects the generic kernel platform-profile ABI
before considering driver replacement. When the requested policy can be
satisfied by the in-tree path, `acer_wmi` remains in control.

The replacement path uses Linuwu-Sense at the full commit
[`73a25ec243a44ba2b1703e8d0a76fa2735062506`](https://github.com/0x7375646F/Linuwu-Sense/tree/73a25ec243a44ba2b1703e8d0a76fa2735062506).
Upstream describes the module as early-stage, reverse-engineered code that
replaces `acer_wmi` and issues low-level WMI calls. That risk is why the role is
not imported by `foundation.yml` or `lab.yml` and why
`nitro_sense_out_of_tree_enabled` defaults to `false`.

The opt-in grants permission to replace the driver. It does not bypass DMI,
source, build or runtime refusal gates.

## What is replaced

The in-tree `acer_wmi` module normally owns Acer hotkeys, radio controls and
platform integration. The out-of-tree module registers the same `acer-wmi`
platform driver identity, so both drivers cannot own the device at once.

A replacement transition is allowed only after the exact reviewed source has
compiled for the running hardened kernel and DKMS has installed the target
module. The previous managed DKMS version remains available for recovery until
the new driver is active and its required runtime controls have passed readback.

Only after those checks may superseded managed source and DKMS state be removed.

If the transition fails, the role removes its boot policy, unloads the
replacement and restores `acer_wmi`. A failed post-load check is never allowed
to leave the host intentionally committed to a driver that did not expose the
required Nitro interface.

The most visible regression is loss of function keys. Radio toggles, brightness
handling, platform profiles or suspend behavior can also change because they
share the same platform driver. Keep an SSH session or text console available
during the first hardware run on a new model.

## Reviewed AN515-55 overlay

The tested Nitro AN515-55 needs a model-scoped compatibility overlay for its
four-zone keyboard.

The upstream legacy quirk exposes the Nitro fan interface but does not advertise
that keyboard. Enabling the generic four-zone path alone was not sufficient:
sysfs accepted writes while the physical keyboard turned off.

The reviewed overlay adds an AN515-55 quirk that uses the four-byte legacy
static-color payload, hardware zone masks `1`, `2`, `4`, `8`, the gaming LED
enable sequence and explicit static-mode selection.

The overlay SHA-256 is:

```text
1a53b4709330ae86dcae16f2efd55ce9468e2cd2d850b48d0f6902641457a778
```

Together with the pinned source commit it produces managed DKMS version
`6b45d4439e68`.

The pinned checkout itself remains pristine. The overlay is applied only to the
isolated build probe and the managed DKMS source copy.

See [`nitro-an515-55-hardware.md`](nitro-an515-55-hardware.md) and
[`../problems/nitro-an515-55-rgb-protocol.md`](../problems/nitro-an515-55-rgb-protocol.md)
for the hardware evidence.

The final AN515-55 lifecycle campaign also proved genuine suspend/resume,
complete managed rollback to `acer_wmi`, reconstruction of the pinned DKMS
replacement and immediate `changed=0` idempotence. Unclassified WMI function
`4` events remain visible as a model-scoped observation rather than an inferred
capability.

## Managed interfaces

The role uses only interfaces documented by the pinned source or the generic
kernel ABI and checks optional nodes before use.

Relevant paths include:

- `/sys/firmware/acpi/platform_profile_choices`
- `/sys/firmware/acpi/platform_profile`
- `/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/nitro_sense/fan_speed`
- `/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/nitro_sense/battery_limiter`
- `/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb/per_zone_mode`
- `/sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/four_zoned_kb/four_zone_mode`

Enabling an LED mode on a model without an accepted four-zone capability is
refused before package installation. The boot helper also fails visibly if a
requested documented node disappears after a kernel or module update.

## Nitro host policy

The reviewed AN515-55 lab policy requests maximum CPU and GPU fan duty:

```text
100,100
```

That is intentional. `0,0` means firmware automatic control and does not satisfy
the selected policy.

The battery limiter is enabled and is read back after application.

A non-zero manual fan request makes the native platform-profile path
insufficient even when generic profiles exist. The explicit replacement opt-in
is still required:

```bash
ansible-playbook -K playbooks/nitro-sense.yml \
  -e nitro_sense_out_of_tree_enabled=true
```

Review [`nitro-sense-procedure.md`](nitro-sense-procedure.md) before the first
hardware apply.

Keyboard lighting is not forced by the normal settings helper merely because
the model exposes RGB. RGB persistence belongs to an explicit control policy,
not to detection.

## RGB acceptance boundary

Static AN515-55 RGB is hardware-validated for:

- one color across all four zones;
- four independent zone colors;
- brightness changes at `10`, `30` and `100`.

Matching sysfs readback is necessary but not sufficient. An earlier incorrect
payload returned the written value while turning the physical keyboard off, so
new RGB paths require physical observation.

Animated firmware effects are not declared supported by this campaign.

The role therefore keeps per-zone and firmware-effect model allowlists
separate. The AN515-55 is accepted for `per_zone`; it is deliberately absent
from the `effect` allowlist until that distinct WMI path is physically proved.

## Source and licensing boundary

This repository remains MIT-licensed and does not vendor Linuwu-Sense source.
The optional role fetches the reviewed upstream commit on the target and builds
it under upstream's GPL-3.0 license.

The repository overlay changes the build identity. Its hash is therefore part
of preflight, DKMS version derivation and the installed build stamp.

Keep upstream licensing and source obligations with any redistributed source or
module build.

## Recovery and rollback

The supported rollback is idempotent and restores the in-tree module:

```bash
ansible-playbook -K playbooks/nitro-sense.yml \
  -e nitro_sense_state=absent
```

It stops and removes the settings service, unloads `linuwu_sense`, removes
managed DKMS/source state and boot-policy files, restores `acer_wmi` and removes
the brick stamp.

Destructive cleanup requires the role's ownership markers. An unmarked source
tree, DKMS directory or service path is refused rather than claimed.

If graphical hotkeys fail but a TTY or SSH shell still works, use the rollback
playbook first. If Ansible itself is unavailable, the emergency path is limited
to restoring the in-tree platform driver and removing the boot policy:

```bash
systemctl disable --now nitro-sense-apply.service || true
modprobe -r linuwu_sense
rm -f /etc/modules-load.d/linuwu_sense.conf
rm -f /etc/modprobe.d/nitro-sense-blacklist-acer_wmi.conf
depmod -a
modprobe acer_wmi
test -d /sys/module/acer_wmi
```

Do not reboot until the last test succeeds. Do not guess a DKMS version in the
emergency shell. Rerun the rollback playbook afterward so repository-owned
DKMS, source, service, stamp and ownership state are reconciled completely.

## Known limits

- Support is DMI-scoped. A working AN515-55 path is not evidence for every Acer
  Nitro model.
- The tested AN515-55 exposes no generic ACPI platform-profile interface.
- Static four-zone color and brightness are proved; firmware animation effects
  are not.
- Per-key RGB is not provided by this hardware path.
- A future hardened kernel can change the out-of-tree module API. DKMS success
  is never assumed across kernel updates.
- The provenance of one already-satisfied `6b45d4439e68` real-run observation
  remains under investigation; see
  [`../problems/nitro-sense-dkms-provenance.md`](../problems/nitro-sense-dkms-provenance.md).
