# ADR 0038 - A new USB device is not trusted by the host automatically

Status: accepted (2026-10-05, option A): generate the policy from the
devices attached, then block every other device. Built as
`roles/host_usbguard` (`playbooks/host-usbguard.yml`); the shell action that
allows a blocked device is built (`playbooks/host-usb-allow.yml`, the USB
devices view), not yet exercised on Nitro.

## Context

Roadmap milestone 10 asks for a host USB policy so a new device is not
trusted automatically. A USB stick can present itself as a keyboard and
type into the host session, which is the control plane for every Machine.
Two facts limit the choice on Nitro: the internal keyboard and touchpad are
not USB devices, so blocking USB cannot lock the operator out, and passing a
device to a guest ([ADR 0034](0034-usb-passthrough.md)) needs the host to
know the device first.

## Options

**A. USBGuard with a generated base policy (recommended).** Install
`usbguard`, generate the initial rules from the devices attached when the
policy is created (the internal hubs, camera, Bluetooth, and any external
device the operator chooses), and block everything else by default. A new
device stays blocked until the operator allows it from the host shell, once
(for this insertion) or permanently (a reviewed rule by vendor, product and
serial); input-class devices are never allowed automatically. The shell
shows a blocked device and the action to allow it.

**B. Kernel authorization defaults.** Set `authorized_default=0` on the USB
controllers and authorize devices through sysfs from a small host tool.
Fewer moving parts, but no rule language and no daemon to ask.

**C. Leave USB open.** Rejected: the roadmap asks for the opposite.

## Implementation

`roles/host_usbguard` installs USBGuard and, only when no policy exists,
generates one from the devices attached now; it installs that policy
root-only after checking it allows exactly as many devices as the kernel
reports. Only then does it set the implicit block, apply the policy to
present and inserted devices, keep the controllers, restrict IPC to root and
start the daemon (`tests/host_usbguard_contract.py`). On Nitro today the
attached USB devices are the two xHCI root hubs, the Intel Bluetooth adapter
(`8087:0026`) and the user-facing camera (`0408:a061`).

**Allowing a device.** The shell's USB devices view lists what
`hyperlabctl usb list` reads from `/sys/bus/usb/devices` without privilege:
each device's port, ids, strings, whether the kernel has authorized it, and
its interface classes, taken from the raw descriptors because a blocked
device is not configured and has no interface directories yet. **Allow
once** and **Allow always** are offered for a blocked device that presents
no keyboard or mouse (interface class 03); input-class devices, and devices
whose interfaces cannot be read, are allowed only from a terminal. The
machine bridge reads the list again and refuses the same cases, then hands
`usb:PORT:SCOPE` to the operation runner, which resolves the registry action
`usb.allow` to `playbooks/host-usb-allow.yml -K` with that port and scope and
pins the target in its record. As root, the playbook checks once more that
sysfs reports the device blocked with no keyboard or mouse interface, that
USBGuard lists exactly one device at that `via-port`, blocked, whose
`with-interface` has no class 03, and only then runs
`usbguard allow-device <id>` (`-p` for always, which appends a rule to the
policy); it reads `authorized` back from sysfs before it reports
(`tests/host_usbguard_contract.py`, `tests/host_machine_actions_bridge_contract.py`,
`tests/host_operation_lifecycle_contract.py`). From a terminal,
`sudo usbguard list-devices` and `sudo usbguard allow-device <id>` (with
`-p` to make it permanent) still do it.

## Recommendation

A. It is the established tool, its rules name devices exactly, and the
same allowlist can later decide which allowed devices may also be passed to
a Machine.
