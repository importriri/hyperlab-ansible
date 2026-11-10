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

The pinning module replaces only one unmarked entry of the same key type,
so duplicate old pins or a sole RSA/ECDSA pin could leave an earlier boot
trusted after a successful Ed25519 refresh. A marked entry also survives
replacement by an ordinary host pin. The per-Machine
publication lock also did not protect the owner's shared `known_hosts` file
from another Machine's read and replacement: concurrent publishers could
both succeed while one overwrote the other's new pin.

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

An additional owner-wide `known-hosts.lock` in the runtime directory covers
the shared database's inspection, duplicate validation and replacement,
including standalone inventory publication. A contender refuses and releases
its own Machine lock; it never removes the holder's shared lock. Retry the
standalone inventory step after the holder ends, since the refused Machine
may already be running. Forced handlers release acquired locks on failures.
OpenSSH's address lookup matches clear and hashed entries; more than one
match refuses without changing pins or publishing inventory.
Even a sole match must be an unmarked Ed25519 entry: a different key type,
`@cert-authority` or `@revoked` refuses before replacement. Inspect and resolve
these entries before retrying; the publisher preserves policy it cannot
safely replace.

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

The inventory contract also preloads plain, hashed and mixed duplicate pins
and requires refusal without database changes or inventory publication. Two
Machine publishers share one owner database; a fixture copy of the installed
pinning module pauses after reading it and before atomic replacement. Both
managed and standalone entry paths contend, then retry; both current keys
must pass strict SSH over a pipe and both stale keys must fail. Removing
shared serialization reproduces the lost update. Parsed lifecycle lock
acquisition and release tasks must each explicitly declare `become: false`,
even though the fixture lifecycle runs without privilege. Each independent
deletion is detected without requesting privilege.

Sole RSA and ECDSA pins and Ed25519 entries marked `@cert-authority` or
`@revoked`, each in clear and hashed form, must refuse without changing the
database or publishing inventory, and release both acquired locks. Ordinary
Ed25519 entries in both forms still refresh; strict SSH accepts the current
boot's key and rejects the previous one. Removing the compatibility assertion
makes the cross-type regression fail.
