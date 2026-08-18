# A Nitro Sense real run found the target DKMS state already satisfied

Author: [importriri](https://github.com/importriri).

Status: open investigation.

## Symptom

The first observed real apply after selecting AN515-55 overlay version
`6b45d4439e68` completed with `changed=0`.

Build-probe, DKMS source preparation, build/install and platform-driver
transition tasks were skipped because the role considered the target state
already satisfied.

A read-only audit immediately afterward confirmed that the target state really
was present:

```text
DKMS: 6b45d4439e68 installed
stamp patch: 1a53b4709330ae86dcae16f2efd55ce9468e2cd2d850b48d0f6902641457a778
fan: 100,100
battery limiter: 1
```

## What is known

The role did not falsely report the old module as the new one. The installed
DKMS version, build stamp, loaded module path and runtime settings all agreed on
the target identity.

What remains unknown is which earlier real operation completed that transition.
The immediately preceding work included build probes, check-mode runs and
manual source validation, but those are not supposed to install the target
runtime state.

## Why it remains open

Reconstructing provenance from an internally consistent end state would require
guessing unless an earlier command or log proves where the real transition
occurred.

The incident is kept open rather than assigning an unsupported cause.

## Required proof before closure

Closure needs evidence that identifies the operation which installed
`6b45d4439e68`, or a reproducible path showing that a supposedly non-mutating
operation can perform that installation.

Until then, future version-bump campaigns should record DKMS status, build stamp
and loaded module path immediately before and immediately after every real
apply. Check mode must remain non-mutating.

## Later lifecycle evidence

The `2026-08-18` acceptance campaign removed the complete managed replacement,
proved `acer_wmi`, and then rebuilt and installed `6b45d4439e68` from the pinned
source and overlay. The reinstall reported `ok=113`, `changed=32`, `failed=0`;
an immediate second run reported `ok=91`, `changed=0`, `failed=0`.

That closes the operational rollback/reinstall and idempotence gate for the
reviewed candidate. It does not identify the earlier command that produced the
already-satisfied state, and it does not substitute for a future managed
version-to-version transition. The historical provenance question therefore
remains open without blocking the now-observed clean removal and reconstruction
path.
