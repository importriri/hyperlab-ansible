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
Known active states other than running (including paused, in shutdown and
pmsuspended) appear as a separate **active (not running)** count, split by
membership when the registry is readable. Only **shut off** and **crashed**
are considered inactive; **unknown** still makes the running summary unknown.
This preserves the meaning of running without implying that a paused guest
has stopped. Presentation counts do not change lifecycle action eligibility.
If registry membership is unavailable, both surfaces show the known raw domains
under **Observed domains · membership unavailable**, with **membership unknown**
on the rows and lifecycle **unknown** in recovery details. The native rows stay
read-only. The total reports membership unavailable. Missing registry input
cannot establish that a domain is external, even if its raw metadata says so.
When the registry becomes readable, the ordinary groups and lifecycles return.
A readable empty registry still shows the first-Machine creation guidance,
alongside Not managed when raw domains exist.

The defined total covers every domain only when the raw observation answered.
Otherwise Machines and Diagnostics name the product part and say the rest is
unavailable (**3 managed · other domains unavailable**). A stale registry read
keeps its own **last observed** age beside that count.

The Waybar VM pill reads the same raw observation (`hyperlabctl waybar --field
vms` through the bridge) and shows running/total over every domain, with each
name and state in its tooltip. The bar has no registry membership, so it does
not split the count; the split lives in the shell views that read the registry.
The product inventory's own `running/total` text counts registry Machines only
and is no longer what the bar shows.
An unknown runtime state changes the pill to **?/total** with an error state
and **Running state unknown** in its tooltip; every observed row and the known
total remain available. `vm list`, in text and JSON modes, refuses an unavailable
domains provider instead of returning a successful empty list. The recovery
JSON reader carries that refusal into **Running inventory unavailable**.
Its Overview also shows **? Detected VMs** when the domains read fails;
**0 Detected VMs** is reserved for a readable empty inventory.
With other active states the pill shows **running+other-active/total** (for
example **0+1/7**) and explains **1 active (not running)** in the tooltip,
alongside every observed state. An unknown state still takes precedence.
The automatic Swaybar fallback reads this same raw CLI payload once per
30-second refresh, matching the Waybar VM pill, and uses the same count,
including **?/total**. Its explicit 30-second command timeout allows for a
full document build rather than the short timeout for other bar fields.
A failed command, timeout or malformed response shows **VM ?**, never
**VM 0**. Installed read latency remains an operator measurement.

## External visual state — Proposed

The [visual trust contract](../visual-trust-contract.md) called both host-native
and unclassified identities neutral but did not distinguish their shapes.
Proposed: an unclassified machine uses a neutral outline, transparent fill and
the appropriate membership word beside it, as defined below. Use primary
appearance text for the outline (`textPrimary` in the native shell,
`hl_text` in recovery), never a trust-domain token or the HOST grey identity.
The native read-only group conservatively uses this state for all non-product rows. When registry
membership is unknown, its neutral outline remains, but **membership unknown**
replaces the external label: less trust does not justify a false lifecycle.
For the same reason a registry Machine whose identity does not resolve is
labelled **unclassified**, never external: the word **external** is reserved
for domains a readable registry places outside the product.

A recovery domain receives a domain colour only when the registry lists it as
a product Machine, one unique spec names it, its observed managed identity and
trust profile agree with that spec's network profile, and every observed
interface belongs to that network. An absent, duplicate or drifting spec does
not grant an identity; multiple interfaces on that same network are allowed,
matching the CLI's `network_identity` rule. A mismatched or empty interface list
does not establish an identity or fall back to dev. A domain outside the
registry is always external in both surfaces, even with a matching spec:
`compose list` also returns host-local `vm-specs/.generated/` files (withdrawn Machines, Workbench candidates), and
nothing marks those as reviewed.
GPU gates and network attachment alone cannot classify a machine.

The CLI still reports a GPU-gate fallback for unmanaged domains: the domains
provider returns the `gpu_domain_profiles` entry as `trust_profile`, and
`waybar --field vms` publishes it as `provenance`. The shell surfaces ignore
both for any domain outside the registry; the native shell overwrites the
incoming provenance with `unclassified`. Changing the provider is a separate
decision.

Segment attachment is not identity. The recovery Networks page counts every
domain whose observed interfaces include a segment's network and lists them in
the segment detail; a domain without that segment's identity keeps the neutral
outline and its own word (**external** or **unclassified**).

## Evidence and limits

`tests/external_machine_visibility_contract.py` executes the real native QML
and recovery GTK builders with one fixture of three stopped product Machines,
one running external domain and three stopped legacy domains. It checks all
seven names, separate groups (including the recovery group header), counts,
session confirmation consequences, external identity and native read-only rows,
plus failed/duplicate/stale inputs, unknown membership and lifecycle, empty
registry creation guidance and missing/duplicate/drifting/generated specs.
The fixture holds minimal libvirt facts; the rows each surface receives are
built by the real domains provider, `vm list` and `waybar --field vms` on a
fake host. The Waybar pill is run through the real bridge with its configured
argv, and segment attachment is checked on the recovery Networks page.
Provider failure is also exercised through `vm list`, the recovery JSON reader
and its model loader. An unreadable external state passes through the real
provider, renderer and configured Waybar pill. GTK resolves the effective
background, border and text styles for external markers, including group dots,
drawer badges and network-member badges, across each appearance palette and
normal, hover and selected states. This includes selector specificity and
source order, rather than merging rules with a particular class name.
The resolved neutral token must also differ from HOST and every domain
identity token in every GTK palette. The fallback check asserts its actual
subprocess budget and compares its refresh interval with Waybar's configuration;
it does not measure live inventory latency.
The GTK probe uses the production provider priority above the user theme and
checks the resolved neutral against the selected appearance, so installed
theme CSS cannot mask the fixture palettes.
The earlier desktop cockpit contract expected **1/3** even with an unknown
fixture state, pinning a partial observation as a complete count. It now
requires **?/3** and an error state, alongside a **1/3** control when every
state is known; its inventory and provenance assertions remain in place.
The software check does not establish installed-shell behaviour, compositor
placement or hardware acceptance. Nitro and Predator checks remain open.
