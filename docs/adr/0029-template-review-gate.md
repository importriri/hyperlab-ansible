# ADR 0029 - The Template review gate

Status: accepted. Implements the milestone 4 item "Template review gate". The
class table is read from the roadmap's Template tables; the operator may
change it, and a change is a reviewed edit of one table.

## Context

A Template decides what its Machines may be: the networks they may live on,
whether they get the GPU and with which handoff class, whether they are
permanent or disposable, and whether Looking Glass presents them. Until now
nothing stopped a Template from offering a combination its purpose forbids:
a server with the GPU, a workstation on the `clean` network, a gaming
Template whose Machines could be created both where the store accounts live
and where modded games run. The factory checked each Machine against its
Template, and the ceiling rule ([ADR 0022](0022-network-trust-and-gpu-policy.md))
against its network, but the Template itself was trusted.

## Decision

Every Template names a `class`, and one table in
`tools/hyperlabctl/hyperlabctl/machine_factory.py` (`TEMPLATE_CLASSES`) bounds
what each class may offer:

| Class | Networks | Devices | GPU profiles | Lifecycles | Looking Glass |
|---|---|---|---|---|---|
| server | dev, services, lab | standard | none | both | no |
| workstation | dev | standard, VFIO | any, under the ceiling | both | yes |
| gaming | exactly one of clean, dirty, lab | standard, VFIO | any, under the ceiling | both | yes |
| services | services | standard, VFIO | its own review | both | no |
| disposable | dirty, lab | standard | none | disposable only | no |

On top of the table, a Template may not offer a GPU handoff profile that
none of its networks allows under the ceiling rule; which network and
profile a Machine gets is checked again when the Machine is made. A
services network has no rung, so a services Template's GPU profiles are its
own review, as ADR 0022 records.

The factory applies the gate when it loads the catalogue, and fails the
catalogue closed on a Template outside its class, as for any invalid
Template. The repository's schema validator applies the same function, so a
Template outside its class cannot be committed with a green CI. A Template's
class must match its id (`server-`, `workstation-`, `gaming-`, `svc-`,
`browser-`).

## Consequences

- A gaming Template has one network: store accounts in `gaming-clean` never
  share a Template, and so never a Machine, with modded or offline games.
- Adding a class, or widening one, is one edit of the table, reviewed with
  the reason; the contract `tests/template_review_gate_contract.py` and the
  schema mutations fix what each class refuses today.
- The per-Machine checks stay: they are the second line behind the gate.
