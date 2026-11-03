# A display title rename left workspace focus looking for the old name

Status: corrected in source and covered by isolated compositor fixtures.
Installed compositor behavior on Nitro and Predator remains pending.

## Symptom

With workspace titles changed to Sfere, requesting an already-open workspace
could no longer bring it forward. Both compositor fixtures reported
`workspace window not found`.

## Root cause

The compositor adapter selected a window by the calling shell's process id
and a fixed title prefix. The QML title changed, but the prefix still named
the previous product. The ordinary shell presentation tests replace the
action transport, so they did not execute that selector.

## Fix

Only the focus route reads the deployed product file used by QML and builds
its title prefix from that value. It does not depend on the CLI checkout. The process id check, exactly-one
match requirement and validated compositor window identifier remain intact.
A missing, redirected or invalid product file refuses focus without dispatch.

## Regression proof

`tests/host_compositor_adapter_behaviour_contract.py` uses the shared name
for its window fixtures and exercises the real adapter on both backends.
`tests/product_display_name_contract.py` includes those focus scenarios and
refusal when the deployed input cannot be read, even with a stale CLI checkout. Restoring the old prefix fails the
new-name focus cases, while restoring the dynamic prefix passes. A similarly
titled window owned by another process still cannot be focused.
