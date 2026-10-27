# A disposable restart reopened the agent and left a stale SSH pin

Author: [importriri](https://github.com/importriri).

Status: software-verified; Nitro acceptance pending.

## Symptom

A disposable server could complete its first provisioning with restricted
QEMU Guest Agent access and working strict SSH, then lose both properties
after a stop and start. The closed agent configuration and the generated
SSH host keys lived on the transient disk discarded by libvirt.

## Root cause

First provisioning wrote the allowlist into the guest and pinned its first
host key. Managed Start waited only for the agent to answer; neither the
seed nor Start restored those boot-specific properties. A successful first
provisioning therefore said nothing about the next disposable boot.

## Fix

The disposable cloud-init seed restores the access-closing role's canonical
allowlist and restarts the agent. Managed start waits for this boot's
cloud-init result, then proves that the agent enables exactly the allowlist
and refuses exec as disabled before succeeding; a boot that fails the proof
is force-stopped, so its possibly open agent does not stay running. Waiting for
the result also prevents a restricted agent already in the base from racing
cloud-init and SSH key generation. Start and Power Cycle then use the
existing unprivileged owner-run inventory publisher to replace the strict
SSH pin from the agent channel and publish the current address. An
owner-held publication lock, taken before the boot under the per-VM lock and
released by the publisher, keeps a second Start or Power Cycle from booting
again while the first boot's key is still being pinned.

Existing seeds must be replaced through normal throwaway Machine creation.
Passwordless server sudo remains an explicit limitation. See
[ADR 0018](../docs/adr/0018-disposable-discards-on-stop.md).

## Regression proof

`tests/guest_contract.py` renders and parses Arch, Debian and Fedora seeds,
checks activation and exercises readiness failures with stubbed agent replies.
`tests/guest_inventory_contract.py` evaluates the shared lifecycle tasks and
publisher with stub libvirt commands, then uses strict SSH over a pipe to
accept the second boot's key and reject the stale one. The vault regression
refuses duplicate YAML keys and preserves the vault's original files and
commands. The mutation catalogue records removed restriction/activation,
cloud-init wait, widened readiness, a guest-exec-only proof, a failed proof
left running, a redirected or overridden policy, missing repin, a
publication outside the lock, a suppressed pin failure and running/check-mode
regressions. No physical cleanup claim follows from
these fixtures.
