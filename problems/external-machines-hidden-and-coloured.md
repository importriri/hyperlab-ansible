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

[ADR 0060](../docs/adr/0060-external-machine-visibility.md) records the accepted
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
neutral outline and transparent fill, distinct from HOST. The word is external
only outside a readable registry; a registry Machine without an identity says
unclassified, and an unreadable registry requires membership unknown.
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

A later review found that observation failures could still hide running
domains. `vm list` converted an unavailable domains provider to `[]` and
returned success. Recovery's JSON reader therefore had no failure to record
and its summary claimed zero running. Both CLI output modes now refuse that
unavailable section; a readable empty list remains valid. The regression
drives the real provider failure through the CLI, recovery JSON reader and
model loader, which reports **Running inventory unavailable**.

Waybar also counted only known running states: an unreadable external state
looked like **0/7**, with an OK class. It now shows **?/7** with an error class
and **Running state unknown**, retaining all domain rows and the known total.
The check sends a failed external state read through the provider, renderer
and the pill's configured bridge route.
The older desktop cockpit contract also expected a definite **1/3** with an
unknown fixture state. Its assertion now requires uncertainty and an error
state, plus a known-state control that still requires the complete **1/3**.

The original colour check merged only CSS rules naming `.vm-domain-external`.
An appended `.external-outline` rule could colour group dots and badges DEV
while the check stayed green; that surviving mutation was reproduced. The
contract now asks GTK for effective text, background and border render nodes
on each external identity widget across all appearance palettes, hover and
selection. GTK applies selector specificity, source order and ancestor rules.
The override now fails, as do a border-only override, a HOST text override and
an earlier, more specific selected-hover rule.

The fallback Swaybar still counted lines after a failed `virsh` call had become
an empty string. It could therefore say **VM 0** precisely when the primary
bar was unavailable. It now reads the same raw CLI projection as Waybar;
failure, timeout or malformed input shows **VM ?**. Recovery Overview had a
similar residual false zero: the subtitle reported unavailable while the large
Detected VMs value was zero. That value is now **?** on a domains load error.

The shared fallback read initially inherited the 1.2-second command timeout
used for cheaper bar fields and ran every five seconds. That read builds the
full CLI document, including per-domain XML and state queries plus other
providers. The short deadline risked a permanent **VM ?**, while the frequent
refresh repeated the full inventory even when the fallback bar was hidden.
The VM reader now has an explicit 30-second budget and the same 30-second
refresh interval as Waybar. The contract checks the actual subprocess timeout
and compares the interval with the Waybar configuration. This bounds the wait
and reduces polling; live read latency still needs measurement on Nitro.

The effective GTK style check also initially accepted a palette whose
`hl_text` itself equalled HOST grey: its text and borders still matched that
token. This mutation stayed green before the additional assertion. GTK now
resolves HOST and every domain token in each palette and rejects any equality
with the neutral token. Both HOST and DEV substitutions now turn the contract
red; transparent fill and effective text/border checks remain in place.
The probe also used application-level CSS priority, allowing installed user
theme definitions to mask every fixture palette. It now matches the production
provider's priority above the user theme and checks the resolved neutral colour
against the selected appearance. Reusing the first palette for every iteration
must fail, so a shadowed fixture cannot produce false palette coverage.

Counting only running states also hid paused, in shutdown and pmsuspended
domains. Both shell summaries now append separate managed/external **active
(not running)** counts. The bars show **running+other-active/total**, preserving
the observed states and explaining the extra count. Shut off and crashed are
inactive; unknown still makes the count uncertain. GTK badges preserve the
observed state instead of saying STOPPED. Lifecycle actions are unchanged.

Native external borders used secondary appearance text while recovery used
primary text. They now both use primary text, and the QML contract checks each
border against every provenance colour, HOST included, across all palettes.
Recovery also unnecessarily required exactly one interface for a reviewed
identity. It now accepts any nonempty set of interfaces all on the reviewed
network, as the CLI does; mixed or missing interfaces remain unclassified.

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
