# ADR 0052 - A host without GPU passthrough, chosen by name

Status: proposed.

## Context

The host playbooks select a hardware profile from `host_profiles`, by name
or with `host_profile: auto`, which picks the one profile whose VFIO PCI IDs
are all present. Every profile today names a GPU to pass through, and
`foundation.yml` stops at `hardware_probe` on a computer that matches none:
"Automatic host selection found 0 complete matches". That refusal is right
on a real host.

The nested lab host (ADR 0046) has no GPU and no passed-through device, yet
it is where the host roles are to be tested with root: the network domains,
the guest isolation, the security plane. And `hyperlabctl doctor --hardware`
(ADR 0050) already treats a computer with one GPU as one that runs Machines
without a GPU of their own.

## Options

**A. A named profile without GPU passthrough, selected only explicitly
(recommended).** `no-gpu-passthrough` declares `gpu_passthrough: false`
and no VFIO IDs. It is selected only by name (`host_profile:
no-gpu-passthrough`); `auto` never considers it. With it, `hardware_probe`
records the profile with `gpu_passthrough: false` and no GPU addresses,
and `vfio_boot` and `gpu_handoff` are skipped, visibly, without stamping
their bricks: anything that needs them refuses later. The other host roles
run.

**B. A playbook for the lab only, without `hardware_probe`.** Nothing
changes for real hosts, but the lab would then test a path no real host
takes, and the brick guards that read the probe's facts would need
exceptions.

**C. Let `auto` fall back to no passthrough when nothing matches.**
Rejected: a real host with an unknown GPU would come up quietly without
its GPU instead of stopping at the refusal that asks for a reviewed
profile.

## Recommendation

A, with these rules held by a test:

- `auto` considers only profiles that pass a GPU through. An empty set of
  VFIO IDs is contained in every host's PCI IDs, so a profile without IDs
  would otherwise match every computer: such a profile must declare
  `gpu_passthrough: false`, and `auto` skips it.
- On the Nitro's PCI IDs, `auto` still selects `nitro-3060`, and on a
  computer without a known GPU it still fails with "0 complete matches".
- Selected by name, `no-gpu-passthrough` publishes `gpu_passthrough:
  false`; a profile that passes a GPU through but whose devices are absent
  is still refused.

## What this does not cover

- VFIO, Looking Glass and the GPU handoff in the lab: there is nothing to
  pass through.
- The boot entries of `vfio_boot`, including the AppArmor entry of ADR
  0037, and `measured_boot`, which both read the VFIO IDs: they are not
  rendered on such a host. Entries without `vfio-pci.ids` would be a later
  change.
- Real hosts with one GPU: the profile works there too, but nothing here is
  tested on one.

## Hardware test

In the lab host: `foundation.yml -e host_profile=no-gpu-passthrough` runs
`base`, `kvm_host`, `network_domains` and `lab_isolation`, and shows
`vfio_boot` and `gpu_handoff` skipped. `/etc/privatestack/hardware-profile.yml`
says `gpu_passthrough: false`, and a VFIO Machine is refused. Without the
variable, `foundation.yml` still stops at "0 complete matches". On Nitro,
`auto` still selects `nitro-3060`.
