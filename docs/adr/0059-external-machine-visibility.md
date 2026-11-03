# ADR 0059 - Show every domain without granting it trust

Status: Proposed (external visual state only; population decision accepted below).

## Context

On 2026-11-02 a running external domain was absent from native Machines and
Session counted zero running Machines. The recovery surface listed it in DEV
because an unknown network fell back to dev. Visibility, product membership
and trust classification had become the same decision in presentation.

## Machines population — Accepted, operator decision

The operator decided on 2026-11-02 that Machines must show every libvirt
domain, including fixtures and external domains, in both surfaces. This
amends the product-only presentation in
[C10](../c10-machine-factory-contract.md#managed-fixture-and-external-domains-are-different-populations)
and the presentation consequence of [ADR 0021](0021-product-lifecycle.md).
It does not change the Machine registry or implicitly adopt anything.

Product Machines retain their inventory and operations. Other domains appear
in a separate **Not managed** group with lifecycle **external**. In the native
shell those rows are read-only, with no selection into the operational pane,
start, shutdown or console. Existing reviewed GTK recovery actions remain.

Raw libvirt observations own the total running count. Machines, Session,
confirmation consequences and Diagnostics distinguish managed running from
external running. Both surfaces read `machine inventory` for registry membership and raw
libvirt observations for running state. A stale `product_managed` metadata
flag never makes an orphaned domain a product Machine. Neither count grants
trust. A failed raw observation says unavailable; a stale one says Last
observed. If any domain's runtime state is unknown, the running summary says
Running state unknown rather than counting that domain as stopped.
If registry membership is unavailable, both surfaces show the known raw domains
under **Observed domains · membership unavailable**, with **membership unknown**
on the rows and lifecycle **unknown** in recovery details. The native rows stay
read-only. The total reports membership unavailable. Missing registry input
cannot establish that a domain is external, even if its raw metadata says so.
When the registry becomes readable, the ordinary groups and lifecycles return.
A readable empty registry still shows the first-Machine creation guidance,
alongside Not managed when raw domains exist.

## External visual state — Proposed

The [visual trust contract](../visual-trust-contract.md) called both host-native
and unclassified identities neutral but did not distinguish their shapes.
Proposed: an unclassified machine uses a neutral outline, transparent fill and
the literal word **external** beside it. Use appearance text for the outline,
never a trust-domain token or the HOST grey identity. The native read-only
group conservatively uses this state for all non-product rows. When registry
membership is unknown, its neutral outline remains, but **membership unknown**
replaces the external label: less trust does not justify a false lifecycle.

A recovery domain receives a domain colour only when one unique reviewed spec
names it, its observed managed identity and trust profile agree with that
spec's network profile, and every observed interface belongs to that network.
An absent, duplicate or drifting spec does not fall back to dev. A reviewed
fixture may keep its verified domain colour in the Not managed group; that
colour establishes neither product membership nor a product lifecycle.
GPU gates and network attachment alone cannot classify a machine.

## Evidence and limits

`tests/external_machine_visibility_contract.py` executes the real native QML
and recovery GTK builders with one fixture of three stopped product Machines,
one running external domain and three stopped legacy domains. It checks all
seven names, separate groups (including the recovery group header), counts,
session confirmation consequences, external identity and native read-only rows,
plus failed/duplicate/stale inputs, unknown membership and lifecycle, empty
registry creation guidance and missing/duplicate/drifting specs.
The software check does not establish installed-shell behaviour, compositor
placement or hardware acceptance. Nitro and Predator checks remain open.
