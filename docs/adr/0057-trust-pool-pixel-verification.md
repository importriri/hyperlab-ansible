# ADR 0057 - Verify trust pool pixels across rendering runtimes

Status: Proposed.

## Context

The trust pool renderer promises stable output for a given Qt release. Its
contract instead required PNG and manifest byte equality across every
runtime. Arch's committed Qt 6.11.2 output and Ubuntu 26.04 CI do not share
a pinned encoding stack. Re-encoding the same pixels at a different zlib
compression level, with a correct manifest hash, reproduced a false failure.
Compressed-file equality was therefore the wrong cross-runtime requirement.

Source restrictions and a few material samples also let an arithmetic corner
mark pass after regeneration. Separate geometry constants in the pool test
did not link the wallpaper to the product symbol defined in ADR 0056.

## Decision

Proposed: replace cross-runtime compressed byte equality with exact decoded
RGB pixel equality for every pixel of all twelve opaque captures. There is
no channel tolerance. Keep SHA-256 pinning of committed files, independently
validate temporary output hashes and `--print-hashes`, and compare the
parsed manifest policy with only those encoding-specific hashes removed.
The documented byte reference remains Qt 6.11.2; it is not a CI prerequisite.

Check all negative-space pixels against the documented near-black ground
range plus grain and rounding, leaving a one-pixel antialiasing margin around
the core, ring and vertically cut arcs. Retain source restrictions and
material probes. Link the pool ratios directly to the product renderer's
numerical QML properties, which its existing contract pins to ADR 0056.

## Evidence and consequences

The complete contract passes with Qt 6.11.2 on Arch and Ubuntu 26.04's
Qt 6.10.2 packages inside an unprivileged Ubuntu Base namespace restricted to
two CPUs. Twelve renders took 79.7 s and 78.8 s respectively; the Ubuntu
contract took 111.92 s overall. Its regeneration subprocess budget is 600 s,
more than seven times either measured render duration, while the renderer
retains its existing 120 s per-image limit. This is local runtime evidence,
not a hosted workflow run or a physical display acceptance.

Compression-only changes are accepted when hashes are updated. A one-pixel
change must still fail, including when its SHA-256 is updated. A regenerated
corner mark, filled geometry gap, transparent capture, stale manifest hash
or product-only geometry change must fail. These mutations are catalogued
in `tests/MUTATIONS.md`. Renderer, artwork, deployment and trust authority
remain unchanged. The operator still decides acceptance of this proposal.
