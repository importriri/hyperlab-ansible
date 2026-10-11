# `foundation.yml --check` used commands, units and users it had not installed

Author: [importriri](https://github.com/importriri).

Status: corrected in every role of `playbooks/foundation.yml` and covered by
`tests/foundation_check_mode_contract.py`; to be seen in the nested lab host.

## Symptom

On 2026-10-11, in the nested lab host (a fresh Arch install), `foundation.yml
-e host_profile=no-gpu-passthrough --check --diff` with the kvm_host fix
([`kvm-host-check-mode-failed-without-libvirt.md`](kvm-host-check-mode-failed-without-libvirt.md))
got past kvm_host and stopped at `network_domains : List all defined libvirt
networks`: `virsh` was not installed (ok=46 changed=18 failed=1 skipped=17;
evidence in `~/hyperlab-evidence/2026-10-11/lab-host-check/`).

## Cause

The same as for kvm_host and
[`usbguard-check-mode-failed-on-first-run.md`](usbguard-check-mode-failed-on-first-run.md):
in check mode a package step only reports "would be installed", and a later
task in the same run used what that package brings. Every role of
`foundation.yml` was read for it:

- `hardware_probe` ran `lspci` right after installing `pciutils`;
- `network_domains` asked `virsh` and the libvirt Python binding, which
  kvm_host and its own first task install;
- `lab_isolation` enabled, asked and reloaded nftables after installing it,
  and its reload handler would run in check mode as well;
- `image_store` refused the QEMU and swtpm identities, which the libvirt,
  QEMU and swtpm packages create, and would have created directories owned
  by their groups.

`base`, `vfio_boot`, `gpu_handoff` and `bootstrap_storage` run nothing the
playbook installs (`cryptsetup`, `mkinitcpio`, `findmnt` and `lsattr` come
with the installed system).

## Fix

Each role looks for what it needs after the package step. In check mode
without it, the run says what it cannot preview and what an apply does, and
skips only what needs it:

- `hardware_probe` reads the same numeric identities from
  `/sys/bus/pci/devices`, where `lspci` reads them, and says so; the real run
  still uses `lspci -Dn`;
- `network_domains` renders the definitions (with their diff), then skips
  every task that asks libvirt;
- `lab_isolation` renders the ruleset (a template's `validate` does not run in
  check mode), then skips enabling, asking and reloading nftables, the
  handler included;
- `image_store`, when the only missing identities are QEMU's and swtpm's and
  libvirt is not installed, previews the administrator's directories and
  skips the others and the base reader group; any other missing identity is
  still refused.

Every describe-only state holds only in check mode.

## Test

`tests/foundation_check_mode_contract.py` holds the four roles to that
pattern and fails on each previous role with its own message (for example
"network_domains asks virsh in a check mode that has no libvirt"). It also
runs the sysfs reading and `lspci -Dn` on the machine that runs it and
requires the same identities and addresses.
