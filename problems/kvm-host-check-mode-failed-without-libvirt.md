# `foundation.yml --check` stopped at kvm_host on a host without libvirt

Author: [importriri](https://github.com/importriri).

Status: corrected in `roles/kvm_host` and covered by
`tests/kvm_host_check_mode_contract.py`; to be seen in the nested lab host.

## Symptom

On 2026-10-08, in the nested lab host `hl-lab-host` (a fresh Arch install
that never had libvirt), `ansible-playbook playbooks/foundation.yml -e
host_profile=no-gpu-passthrough --check --diff` ended with `failed=1` at
`kvm_host : Enable socket activation`: "Could not find the requested
service libvirtd.socket" and the same for `virtlogd.socket`. Nothing after
kvm_host was previewed (evidence:
`~/hyperlab-evidence/2026-10-08/lab-host/foundation-check-console.txt`).

## Cause

In check mode the package step only reports libvirt as "would be
installed". The socket units, and the `libvirt` group the next task adds
the admin to, come with that package, so they do not exist yet. The same
first-run problem as
[`usbguard-check-mode-failed-on-first-run.md`](usbguard-check-mode-failed-on-first-run.md).

## Fix

`roles/kvm_host` looks for `libvirtd.socket`'s unit after the package step.
In check mode without it, the run says that the sockets and the group
cannot be previewed and what an apply does, and skips only those two
steps. A run that changes the host has the package by then, so nothing is
skipped there.

## Test

`tests/kvm_host_check_mode_contract.py` requires the unit lookup between the
package step and its use, describe-only only in check mode without the
unit, the message, and the skip on exactly the two steps that need the
packages. It fails on the previous role with "'Enable socket activation'
runs in a check mode that has no libvirt to run against". The check run
itself is to be seen again in the lab host.
