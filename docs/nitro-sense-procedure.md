# Nitro Sense application procedure

This procedure is intentionally separate from the normal host campaign.
`foundation.yml` and `lab.yml` must remain unchanged.

## 1. Prove the repository before hardware changes

```bash
./verify.sh
ansible-playbook -K playbooks/preflight.yml
```

The existing stage-2 host target and its second-run idempotence gate must already
be green. The `base` and `hardware_probe` brick stamps are prerequisites for the
optional role.

## 2. Observe the native-first decision

```bash
ansible-playbook -K playbooks/nitro-sense.yml --check --diff
```

If the running kernel advertises the requested profile, the role keeps
`acer_wmi`. If the profile is absent, the default run refuses and explains that
driver replacement needs explicit authorization.

When the native path is sufficient, apply it without the replacement opt-in and
prove immediate idempotence:

```bash
ansible-playbook -K playbooks/nitro-sense.yml
ansible-playbook -K playbooks/nitro-sense.yml
test -d /sys/module/acer_wmi
test ! -d /sys/module/linuwu_sense
cat /sys/firmware/acpi/platform_profile
```

The second recap must report `changed=0`. Stop here; an unused opt-in must not
become a reason to replace a sufficient native driver.

## 3. Preview the explicit replacement

Only when the native interface is insufficient and the recovery impact has been
reviewed:

```bash
ansible-playbook -K playbooks/nitro-sense.yml --check --diff \
  -e nitro_sense_out_of_tree_enabled=true
```

Check mode validates DMI identity, the exact upstream pin, the hardened-kernel
policy and every requested setting. Compilation and driver transition remain
real-run gates because a predicted package or checkout is not a build proof.

## 4. Apply with a recovery shell open

```bash
ansible-playbook -K playbooks/nitro-sense.yml \
  -e nitro_sense_out_of_tree_enabled=true
```

The role installs dependencies only after the DMI refusal gate, compiles an
isolated copy before unloading anything, registers the exact commit with DKMS,
then replaces `acer_wmi`. A missing fan node or failed module load triggers the
automatic rollback.

## 5. Prove immediate idempotence

```bash
ansible-playbook -K playbooks/nitro-sense.yml \
  -e nitro_sense_out_of_tree_enabled=true
```

The second recap must report `changed=0`. A version bump must change the
full-commit stamp and rebuild through DKMS; the existence of a module binary is
never treated as the source identity.

## 6. Run the hardware checks

Before reboot, verify the driver and the documented interface without recording
serial numbers:

```bash
grep -R -- 'pcie_port_pm=off' /boot/loader/entries
test -d /sys/module/linuwu_sense
test -w /sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/nitro_sense/fan_speed
cat /sys/module/linuwu_sense/drivers/platform:acer-wmi/acer-wmi/nitro_sense/fan_speed
systemctl --no-pager --full status nitro-sense-apply.service
```

Then verify brightness, volume, wireless and Nitro function keys manually. After
one controlled reboot, repeat the boot-argument, module, service, profile and fan
checks. The role never edits the boot entries, and `pcie_port_pm=off` must remain
present. LED checks belong only to a model and mode accepted by the role
preflight.

## 7. Exercise rollback before publication

```bash
ansible-playbook -K playbooks/nitro-sense.yml \
  -e nitro_sense_state=absent
test -d /sys/module/acer_wmi
test ! -e /etc/modprobe.d/nitro-sense-blacklist-acer_wmi.conf
test ! -e /etc/modules-load.d/linuwu_sense.conf
```

Reinstall only after rollback and function-key recovery are both proven. Freeze
the exact repository identity before collecting screenshots, video and sanitized
hardware evidence; any runtime fix invalidates the affected hardware sequence.
