# Can the host read a Fedora Machine's SSH host key through the agent?

Author: [importriri](https://github.com/importriri).

Status: diagnosis waiting for Nitro. No Fedora Machine has been created yet;
nothing here is a confirmed failure.

## Question

`vm-guest-inventory.yml` pins a new Machine's SSH host key by reading
`/etc/ssh/ssh_host_ed25519_key.pub` through QEMU Guest Agent
(`guest-file-open`, `guest-file-read`, `guest-file-close`). Red Hat
distributions have shipped agent configurations that block the `guest-file-*`
calls, and SELinux could deny the agent the key files. Either would stop
`srv-fed-01` at the inventory step.

## What is known before Nitro

- The image carries the agent: `image-validate.yml` found `qemu-ga` and its
  unit in the sealed `fedora` image on Nitro (2026-10-04).
- The agent's calls are not blocked by the package default. Fedora's
  `qemu-ga.sysconfig` for `f44` and `rawhide` (package sources,
  `src.fedoraproject.org/rpms/qemu`) only shows a commented example:
  `#QEMU_GA_ARGS=--block-rpcs=guest-file-open,…,guest-exec,guest-exec-status`.
- SELinux: the current Fedora policy sources (`fedora-selinux/selinux-policy`,
  `rawhide`) define no file context for the agent binary and no
  `virt_qemu_ga_t` rules in `virt.te`, `qemu.te`, `virt.fc` or `qemu.fc`. If
  the image matches, the agent runs as an unconfined service and may read the
  public host keys. That is an inference from the sources, to be confirmed on
  the running guest.

## Commands for Nitro

Create the Machine with an explicit network, then run the agent queries from
the host without privilege:

```bash
hyperlabctl machine create server-fedora srv-fed-01 --network-profile dev --resource-profile custom --memory-mb 2048 --vcpus 2 --disk-gib 16
virsh -c qemu:///system qemu-agent-command srv-fed-01 '{"execute":"guest-info"}'
```

`guest-info` lists every RPC with `"enabled": true|false`; the three
`guest-file-*` calls must be enabled. If the inventory step then fails, the
answer is in the guest: `ps -eZ | grep qemu-ga` (the agent's SELinux domain)
and `journalctl -t audit -g qemu-ga` (denials), read with the guest account.

## If it fails

[ADR 0025](../docs/adr/0025-host-key-without-agent-file-reads.md) records the
options; none of them accepts a key from the network.
