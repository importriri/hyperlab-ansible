# ADR 0026 - Derive a Golden Image offline from a sealed base

## Context

[ADR 0015](0015-golden-image-capture.md) captures a Golden Image from a
domain an operator built and used. The upstream Debian 13 genericcloud image
lacks QEMU Guest Agent
([`../../problems/sealed-image-claimed-guest-agent.md`](../../problems/sealed-image-claimed-guest-agent.md)),
and booting it as a candidate does not help: with no agent there is no
trusted way to pin its SSH host key, so it cannot be reached safely to
install anything, and a key accepted from the network is never an option.
Installing at every first boot would make the running Machine differ from
the sealed image and fail offline on `lab`.

## Decision

The Workbench gains a second way in: **derive**, which never boots anything.

- The derived image's manifest names its base and a reviewed package list in
  a `derive` section (`base`, `install`); package names are validated by the
  schema. The manifest is a placeholder until the derived image is sealed.
- `workbench-derive.yml` copies the base out of the store as a flat qcow2,
  after checking the base is sealed and its digest still matches its
  manifest. The base is only read.
- `virt-customize --install` installs the list inside the libguestfs
  appliance, with the appliance's own network. apt verifies the packages
  against the archive keys already inside the sealed base; nothing is
  trusted from the host or the guest network.
- The copy then goes through the Workbench's generalization and leftover
  scan, extended for apt and dpkg residues (package caches, apt lists, apt
  and dpkg logs), and the derived image must carry the agent: its binary and
  unit, and an activation (a systemd wants link or a udev rule).
- The result is staged with a rendered manifest; the existing local import,
  validation (including the guest agent check) and commit seal it, as for a
  capture.

## Consequences

- An upstream image can gain the integration HyperLab needs without a
  candidate VM, an SSH connection or a first-boot install.
- The derived image is a new Golden Image with its own digest; the base keeps
  its own receipt and is never modified.
- The package list is policy: changing it is a reviewed manifest change and a
  new derived image.
- The first boot of a Machine from it is also the first boot of that image;
  the Machine's own provisioning proves the agent works.
