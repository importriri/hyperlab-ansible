# External domains disappeared or borrowed DEV colour

Author: [importriri](https://github.com/importriri).

Status: corrected in source, software-verified. Installed Nitro and Predator
acceptance remains open.

## Symptom

On 2026-11-02 the CLI listed seven domains, with `hl-lab-host` running.
Native Machines showed three stopped product Machines, and Session claimed
zero running. Recovery showed the external domain as DEV.

## Cause

The native product registry and raw libvirt observations had separate views:
only Diagnostics exposed non-product domains. Running counts consulted only
the product projection. The GTK classifier used attachment and defaulted an
unknown or absent network to dev, without consulting a reviewed spec.

## Correction

[ADR 0059](../docs/adr/0059-external-machine-visibility.md) records the accepted
operator decision to show every domain in Machines, without adoption. Native
Not managed rows remain read-only and explicitly external. Raw libvirt state
supplies the total and split running counts on Machines, Session, confirmation
consequences and Diagnostics. Both surfaces read the registry-backed
`machine inventory` for membership; orphaned `product_managed` metadata
cannot move a domain into the product group. Invalid or duplicate inventories become
unavailable, and stale counts are labelled as observations. A domain with an
unreadable state makes the running summary unknown; its recovery badge says
UNKNOWN, never STOPPED.

A failed registry read initially cleared the product rows and treated every
remaining raw domain as external. This hid the uncertainty behind a less
trusted but still false lifecycle, including permanent product Machines.
Both surfaces now use **Observed domains · membership unavailable** and
**membership unknown** metadata until the registry can establish membership;
recovery detail lifecycle is **unknown**. Native rows remain neutral and
read-only, and Diagnostics makes the same distinction. A readable empty
registry retains creation guidance even when external domains are present;
the guidance mentions the lower group only when domains exist.

Recovery classification requires a unique spec and agreement with the observed
managed identity, trust profile and interfaces. An unclassified row has a
neutral outline, transparent fill and the external label, distinct from HOST.
The native read-only group stays neutral throughout.

A review of the first correction found four more places with the same defect:

- The sway Waybar VM pill read the product inventory, whose text counts only
  registry Machines: **VM 0/3** while `hl-lab-host` ran, **VM 0/0** on a fresh
  registry. It now reads the raw observation through the bridge and counts
  every domain. The CLI contract used to accept the pill because its last
  word, `vms`, is a CLI field name; it now resolves each pill through the real
  bridge, which routes `vms` to the product inventory.
- Recovery Networks counted a segment's machines with the identity classifier.
  Once unspecced domains became external, `arch-dev`, attached to DEV, vanished
  from every segment. Attachment is now counted from observed interfaces and
  listed separately from identity.
- A registry Machine with drifting provenance was labelled **external** in
  recovery tiles, the drawer badge and detail. It is now **unclassified**.
- A domain outside the registry with a leftover generated spec kept that
  spec's colour in recovery. Only registry Machines can now receive a colour,
  as in the native shell.

## Is the recovery Shut down action intended?

Undecided. What exists: the recovery manager sends an external running
domain's **Shut down** to `_vm_action("vm.stop", domain)`, and the registry
resolves `vm.stop` to graceful libvirt shutdown; managed lifecycle uses its
separate `vm.managed-shutdown` route. The code shows that the button exists,
not that offering it on a domain such as the `hl-lab-host` test bed was
decided. It is existing behaviour, kept unchanged; its intent awaits the
operator's decision. The native Not managed group offers no such action. No
lifecycle operation was performed to verify this change.

## Regression proof

`tests/external_machine_visibility_contract.py` executes production QML in
the existing offscreen harness and real GTK builders on a private Broadway
display, using the same seven-domain fixture. It checks names, grouping,
counts, neutral unfilled external identity, native absence of actions and
preservation of recovery Shut down, plus duplicate, unavailable and stale
inputs and absent/ambiguous/drifting specs. It also checks unknown membership
on headings, rows and recovery detail lifecycles, the external group header's
neutral identity, all three session confirmation consequences and creation
guidance with an empty registry. The fixture is minimal libvirt facts; the
real domains provider, `vm list` and `waybar --field vms` build every row on a
fake host. The same contract runs the Waybar pill's configured argv through
the real bridge and checks recovery segment attachment, unclassified product
wording, generated specs and partial or stale totals. Mutations are in
[`tests/MUTATIONS.md`](../tests/MUTATIONS.md).

The display-free shell structure fixtures also reuse the production Model's
product membership and running-summary readers. Their drawer assertion names
both counts explicitly; adding a new read to the manager cannot leave its
fixture model behind while the real-widget contract passes.
