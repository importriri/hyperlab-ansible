# The first Machine refused SSH: its new host key was unknown

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the guest inventory contract. The
physical run on `dev-01` is pending.

## Symptom

`dev-01` was created from the `workstation-dev` Template, booted, answered
QEMU Guest Agent and got its address, then the dev profile playbook could not
connect:

```text
No ED25519 host key is known for 10.10.3.131 and you have requested strict
checking.
Host key verification failed.
```

## Root cause

Working as designed on both sides, with a step missing in between. The seal
removes the SSH host keys from the Golden Image, so every Machine generates
its own on first boot. The runtime inventory connects with
`StrictHostKeyChecking=yes`. Nothing put the new key into `known_hosts`;
`arch-dev-vfio`'s key had been accepted by hand once.

Accepting the key on first connection, or with `ssh-keyscan`, would trust
whatever answered on the network at that address.

## Fix

`vm-guest-inventory.yml` reads `/etc/ssh/ssh_host_ed25519_key.pub` from the
guest through QEMU Guest Agent, the hypervisor's own virtio channel, checks
that it is one well-formed ed25519 key, and pins it in the operator's
`known_hosts` to the address it has just resolved through the same agent. A
different key already recorded for a reused address is replaced.

## Regression proof

`tests/guest_inventory_contract.py` drives `tools/guest_host_key.py` with a
fake agent (open, read, close), refuses a non-ed25519 key, a malformed key,
two keys and a host name instead of an address, and requires the inventory
to read and pin the key after resolving the address and before writing the
inventory, never through `ssh-keyscan`.
