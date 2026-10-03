# HyperLab machine templates

This directory contains reviewed product Templates / Presets.

The product hierarchy is:

    Golden Image -> Template -> Machine

A Template is checked-in product policy. It is not a running VM and does not
carry runtime observations.

## Published Templates

| Template | Golden Image | Machines it offers |
| --- | --- | --- |
| [`workstation-dev`](workstation-dev.yml) | `arch-dev-20261003` | permanent, VFIO, dev network, GPU class `dev`, Linux Looking Glass |

`workstation-dev` offers only VFIO Machines: its image carries the
NVIDIA-only session of the workstation it was captured from. Disposable
Machines are not offered until a disposable Machine really discards its
writable layer on shutdown. Creating a Machine from it:
[`../docs/first-machine.md`](../docs/first-machine.md).

Checked-in VM specs remain development and hardware fixtures.

runtime       user-created Machine records outside Git

User-created Machine records belong to the user-owned host-side runtime registry, not to
this directory and not to vm-specs/.generated.

## GPU handoff policy

`network_profile` and `gpu_handoff_profile` are separate authorities.

`network_profile` defines the Machine's network identity and therefore its
managed provenance / presentation identity.

`gpu_handoff_profile` is only a reviewed host hardware contamination class for
the existing monotonic GPU handoff policy. It does not rename or reclassify the
Machine's network identity.

For example, a future GPU-accelerated service workload may remain
`network_profile: services` while requesting `gpu_handoff_profile: dev` when
that combination is explicitly allowed by its reviewed Template.

The privileged provisioning path must materialize that requested GPU handoff
policy into the root-owned hook configuration before the Machine may own the
GPU. The user-owned Machine registry is never sufficient authority by itself.

## VM-spec projection

A product Machine may be projected into `vm-specs/.generated/` only as a
derived compatibility adapter for the existing guest planners, Ansible
transactions and libvirt lifecycle.

The generated VM spec is not persistent Machine authority. The Machine record
outside Git remains authoritative for product intent, Template version and
Golden Image digest. The derived adapter carries the pinned Golden Image digest
so a previously generated spec cannot silently follow a later reseal of the
same image identifier.

For VFIO Machines, successful projection is not sufficient authorization to
start the domain. The requested `gpu_handoff_profile` must also be reconciled
through the reviewed privileged host policy before the root-owned qemu hook may
permit GPU ownership.

## Privileged GPU policy materialization

Checked-in hardware fixtures continue to use the reviewed static
`/etc/gpu-handoff/domains` map.

A C10 Machine-derived VFIO spec carries the `managed-machine` tag and an
explicit `gpu_handoff_profile`. During a privileged guest lifecycle operation,
HyperLab materializes that exact request as a root-owned 0644 entry below
`/etc/gpu-handoff/domains.d/`.

The qemu hook merges the static fixture map and this root-owned managed-Machine
surface before applying the monotonic GPU contamination ladder. Duplicate domain
identities, redirected policy files and unknown handoff profiles fail closed.

The user-owned Machine registry and the derived VM spec never write this policy
directly and are not sufficient authorization for physical GPU ownership.

Runtime diagnostics preserve that distinction. `gpu_handoff_profile` is the
requested value carried by managed libvirt metadata, while
`gpu_trust_profile` is published for a product Machine only after the
root-owned `domains.d/<machine>.conf` surface has been observed as safe and
consistent. Missing, unsafe or mismatched root policy fails closed in product
runtime matching and is reported as configuration drift.

## Product Machine inventory

`hyperlabctl machine list` reads only persistent C10 Machine records.
`hyperlabctl machine inventory` overlays matching host-observed runtime facts
onto that product registry.

A libvirt domain does not become a product Machine merely because it exists.
Checked-in fixtures such as `arch-dev-vfio`, and external or otherwise
unregistered domains, remain visible through Diagnostics/raw inventory but are
excluded from the normal Machines workspace.

On a first install with no persistent Machine records, the product inventory is
valid and empty even if fixture domains already exist in libvirt.

Persistent Machine intent never claims observed runtime state or provenance.
Until a matching managed runtime domain is observed, a Machine is presented as
not created, runtime unavailable, or configuration drift with unclassified
provenance.

`hyperlabctl machine create` creates persistent intent only. It does not define
or start a VM. `hyperlabctl machine project` writes the derived legacy VM-spec
adapter as a separate explicit step.
