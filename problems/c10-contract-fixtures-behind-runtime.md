# C10 runtime hardening left three discovered contracts behind

Author: [importriri](https://github.com/importriri).

Status: corrected; the complete discovered suite is green.

## Symptom

The focused C10 gate list passed, but the complete discovered contract run
(`tests/*_contract.py`, as CI runs it) failed in three places:

```text
c10_machine_cli_product_inventory_contract  matching managed runtime was not adopted
guest_contract                              Windows Looking Glass requires explicit windows mode
docs_contract                               orphaned top-level document: docs/c10-machine-factory-contract.md
```

## Root cause

Each failure was a fixture or a document that predated a deliberate C10
change, not a regression in the runtime code:

1. The GPU-policy observability repair made product runtime matching require
   the observed root policy state (`gpu_policy_state`). The inventory contract's
   synthetic runtime row predated that field, so it modelled a row the real
   domains provider can no longer emit.
2. C10 made Windows Looking Glass require `looking_glass_mode: windows`. The
   checked-in fixtures were migrated, but the VFIO fixture written by
   `guest_contract.py` still relied on the old implicit mode.
3. The C10 contract document had no inbound link, which the documentation
   contract treats as an orphan.

## Fix

The synthetic runtime row now mirrors `providers/domains.py`, including the
policy state it reports for product, legacy-static and unconfigured domains.
The guest contract fixture states the explicit Windows mode. The README links
the C10 contract.

The production matching rule was not relaxed to make the old fixture pass.

## Lesson

A milestone gate list is a starting point, not the proof. The complete
discovered suite is what CI runs, and it is the suite that has to be green
before a freeze.
