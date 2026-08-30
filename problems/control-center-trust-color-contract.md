# Control Center geometry test required trust colors in the manager

Author: [importriri](https://github.com/importriri).

## Symptom

`tests/mockup_geometry_contract.py` failed before the Nitro Control Panel landing
with:

```text
immutable domain color missing: #72f2a5
```

The Control Center manager intentionally no longer carries those literal colors.

## Root cause

The trust palette was separated from presentation-theme colors, but the geometry
test still treated the Python manager as the source of truth for semantic trust
colors. That assertion became stale when the manager started consuming the
shared runtime palette instead of duplicating semantic values.

## Fix

The geometry contract now validates the canonical trust mapping where ownership
actually lives: every GTK theme palette must publish the same `hl_dom_*` values,
and every domain cube must retain its matching semantic color.

The manager is intentionally not required to duplicate those literals.

## Regression proof

The geometry test must fail when any theme-specific `hl_dom_*` mapping or domain
cube drifts from the canonical clean/dev/services/dirty/lab colors, while a
manager that contains no literal trust colors remains valid.
