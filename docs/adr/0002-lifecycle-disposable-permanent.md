# ADR 0002 - Disposable and permanent lifecycles

## Context

Two workloads with opposite requirements share one image store: a lab VM
that must return to a known state in seconds, and a personal Windows
install whose data must survive a template update.

## Decision

**Disposable** is a qcow2 overlay whose backing file is the immutable
base. Reset is: delete the overlay, recreate it. Nothing else.

**Permanent** is, by default, an independent clone produced with
`qemu-img convert`. No backing file, no chain, no dependency on the base
after creation.

A permanent VM on an overlay is available as an explicit opt-in and
prints what it costs: the base can never be removed or rebased, and the
chain has to be read before every operation.

## Consequences

- Creating a permanent VM is slow (a full copy) and that is the correct
  trade: it buys independence from the template forever after.
- `image remove` can refuse safely, because "is this base referenced"
  is answerable by reading backing chains under `disposable/` only.
- Reset means one thing, on one lifecycle. A reset request against a
  permanent VM is an error, not a destructive surprise.
- Disposable VMs are the ones the garbage collector may touch; permanent
  ones are never collected automatically.
