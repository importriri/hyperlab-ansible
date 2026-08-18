# Nitro Sense application procedure

This procedure is intentionally separate from the normal host campaign.
`foundation.yml` and `lab.yml` must remain unchanged.

The first run on a new model needs a recovery shell and physical observation.
A reverse-engineered WMI interface is not accepted solely because a sysfs write
returned success.

## 1. Prove the repository before hardware changes

```bash
./verify.sh
ansible-playbook -K playbooks/preflight.yml
```

The existing host target and its idempotence gate must already be green. The
`base` and `hardware_probe` brick stamps are prerequisites for this optional
role.

## 2. Observe the native-first decision

```bash
ansible-playbook -K playbooks/nitro-sense.yml --check --diff
```

If the running kernel can satisfy the requested policy without driver
replacement, the role keeps `acer_wmi`.

A manual fan policy such as the reviewed AN515-55 `100,100` request is not
silently reinterpreted as a generic platform profile.

When the native path is sufficient, apply it without the replacement opt-in and
prove immediate idempotence:

```bash
ansible-playbook -K playbooks/nitro-sense.yml
ansible-playbook -K playbooks/nitro-sense.yml
test -d /sys/module/acer_wmi
test ! -d /sys/module/linuwu_sense
cat /sys/firmware/acpi/platform_profile
```

The second recap must report `changed=0`. Stop there: an unused opt-in must not
become a reason to replace a sufficient native driver.

## 3. Verify the reviewed source identity

Before a replacement run, confirm that defaults still name the reviewed
Linuwu-Sense commit and any model overlay has the expected filename and
SHA-256.

For the validated AN515-55 path:

```text
commit:
73a25ec243a44ba2b1703e8d0a76fa2735062506

overlay SHA-256:
1a53b4709330ae86dcae16f2efd55ce9468e2cd2d850b48d0f6902641457a778

DKMS version:
6b45d4439e68
```

The pinned checkout must remain clean. Patch experiments belong in temporary
copies because source identity and build evidence must not share one mutable
worktree.

## 4. Preview the explicit replacement

```bash
ansible-playbook -K playbooks/nitro-sense.yml --check --diff \
  -e nitro_sense_out_of_tree_enabled=true
```

Check mode validates DMI identity, source policy, hardened-kernel prerequisites,
ownership and requested settings.

Compilation, DKMS installation and platform-driver transition remain real-run
gates. Check mode must not make those changes.

## 5. Capture the pre-apply runtime identity

Record at least:

```bash
dkms status | grep linuwu_sense || true
cat /usr/local/share/nitro-sense/built-from.yml 2>/dev/null || true
lsmod | grep -E '^linuwu_sense|^acer_wmi' || true
modinfo -n linuwu_sense 2>/dev/null || true
```

This evidence exists because one AN515-55 campaign found the target DKMS state
already satisfied before the expected real transition could be observed.

## 6. Apply with a recovery shell open

```bash
ansible-playbook -K playbooks/nitro-sense.yml \
  -e nitro_sense_out_of_tree_enabled=true
```

The safe ordering is:

1. validate the exact source identity;
2. compile an isolated patched copy;
3. prepare and install the exact DKMS target;
4. retain the previous managed version as recovery state;
5. transition the platform driver;
6. require the documented runtime interface;
7. apply and read back requested settings;
8. remove superseded managed DKMS/source state only after success.

A build failure must not touch the active platform driver.

## 7. Audit the resulting runtime

For the validated AN515-55 policy, verify:

```bash
dkms status | grep linuwu_sense
cat /usr/local/share/nitro-sense/built-from.yml
modinfo -n linuwu_sense
grep -nE 'fan_value|battery_limiter_value' \
  /usr/local/libexec/nitro-sense-apply
cat /sys/bus/platform/drivers/acer-wmi/acer-wmi/nitro_sense/fan_speed
cat /sys/bus/platform/drivers/acer-wmi/acer-wmi/nitro_sense/battery_limiter
systemctl is-active nitro-sense-apply.service
```

The reviewed lab policy expects fan `100,100` and battery limiter `1`.

Service state is not a substitute for value readback.

## 8. Prove immediate idempotence

Repeat the same real playbook:

```bash
ansible-playbook -K playbooks/nitro-sense.yml \
  -e nitro_sense_out_of_tree_enabled=true
```

The second recap should report `changed=0`.

A source commit, overlay hash or running-kernel change must invalidate the old
build identity instead of accepting a module binary by filename alone.

## 9. Run hardware checks

Before reboot, prove that the Nitro role did not rewrite the boot entry that
carries the host PCIe power-management workaround:

```bash
grep -R -- 'pcie_port_pm=off' /boot/loader/entries
```

The Nitro role does not own boot-entry policy. The argument must remain present
before and after the platform-driver campaign.

Verify brightness, volume, wireless, Nitro function keys, suspend behavior and
the intended fan response before treating a new platform-driver run as
successful.

Do not treat the return of `systemctl suspend` as a completed lifecycle. Record
a journal boundary before the request, wait for a newer kernel
`PM: suspend exit`, and only then collect the post-resume runtime, network and
physical checks. See
[`../problems/nitro-suspend-resume-evidence-race.md`](../problems/nitro-suspend-resume-evidence-race.md).

RGB requires an additional rule: first capture a kernel-log baseline, make one
controlled write, inspect new kernel messages and observe the physical keyboard.

For the AN515-55 static path, hardware validation has already proved independent
zone colors and brightness values `10`, `30`, `100`. Do not use those results to
declare untested animated firmware effects supported.

## 10. Reboot and persistence gate

After a controlled reboot, repeat the boot-argument check, module identity,
build stamp, service, fan, battery and function-key checks.

RGB persistence must match the explicit configured RGB policy. Detection of a
four-zone keyboard alone must not cause a boot-time color write.

## 11. Exercise rollback before publication

```bash
ansible-playbook -K playbooks/nitro-sense.yml \
  -e nitro_sense_state=absent

test -d /sys/module/acer_wmi
test ! -e /etc/modprobe.d/nitro-sense-blacklist-acer_wmi.conf
test ! -e /etc/modules-load.d/linuwu_sense.conf
```

Reinstall only after rollback and platform-function recovery are proved.

Any runtime fix after evidence collection invalidates the affected sequence.
Freeze the exact candidate before screenshots, video and sanitized publication
evidence.

## 12. Accepted AN515-55 lifecycle result

The final hardware transaction for the reviewed source and overlay completed
with these recaps:

- rollback: `ok=46`, `changed=10`, `failed=0`;
- reinstall: `ok=113`, `changed=32`, `failed=0`;
- second run: `ok=91`, `changed=0`, `failed=0`.

The rollback restored `acer_wmi`; brightness, volume, Wi-Fi and the Nitro key
worked on that native path. Reinstallation restored the exact DKMS identity,
both services, fan `100,100`, battery limiter `1` and the reviewed four-zone
state. The same physical controls and RGB behavior passed after reinstall.

The transition journal contained no matching driver error, failure, timeout,
oops or kernel bug. The separate suspend campaign did record the unclassified
`Unknown function number - 4 - 0` event. Its accepted scope and reopen criteria
remain documented in
[`../problems/nitro-wmi-unknown-function-four.md`](../problems/nitro-wmi-unknown-function-four.md).

The evidence wrapper's credential failures and final safe handoff are recorded
in
[`../problems/ansible-become-password-handoff.md`](../problems/ansible-become-password-handoff.md).
