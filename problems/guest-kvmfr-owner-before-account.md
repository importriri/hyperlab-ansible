# Looking Glass on a new Machine: the kvmfr device stayed root's

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the Linux Looking Glass contract.
The physical run on `dev-01` is pending.

## Symptom

On `dev-01`, the first Machine from the `workstation-dev` Template, the dev
profile playbook stopped at the Looking Glass transport:

```text
assertion: guest_looking_glass_linux_kvmfr_stat.stat.pw_name == admin_user
The Linux sender requires the passed PCI IVSHMEM device to be bound to kvmfr
and directly readable and writable by the workstation session.
```

`hyperlabctl open looking-glass dev-01` reported the same from the host side:
the guest kvmfr device was not accessible to the graphical user.

## Root cause

The guest rule `70-kvmfr-guest.rules` gives `/dev/kvmfr0` to the workstation
account by name. udev resolves `OWNER` and `GROUP` names when it loads its
rules. A Machine from a sealed image has no account in the image: on its first
boot udev loaded the rules, and created the device, before cloud-init created
`sid`, so the name did not resolve and the device stayed `root:root`. The
role's `udevadm control --reload` keeps rules whose files did not change, so
the later trigger applied the same stale result.

`arch-dev-vfio` never met this: its account existed before the rule was
installed.

## Fix

When the device does not belong to the workstation account, the role
restarts `systemd-udevd`, which re-reads the rules with the account now
present, triggers the kvmfr device again and inspects it again. On every
later boot the account exists before udev starts, so nothing restarts.

## Regression proof

`tests/looking_glass_linux_contract.py` requires the restart between the
first inspection and the transport check, allows no other service in the
role, and requires the second inspection to use its own register so a
skipped restart never overwrites the first result.
