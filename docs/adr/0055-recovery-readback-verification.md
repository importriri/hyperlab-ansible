# ADR 0055 - Verify recovery readbacks against authority and allocation

Status: Proposed.

## Context

The 2026-11-02 Nitro capture exposed an inverted GPU ladder and overlapping
Networks tiles in the GTK recovery Control Center. The M11 visual contract
required the exact implementations causing those defects:

- a literal GPU tuple placing Clean and Dev at 0, Services at 1 and Lab at 3;
- `Gtk.Fixed` for a canvas whose tile rows were 114 pixels apart, while the
  production CSS allocated each tile 154 pixels high in the regression case.

Those requirements were wrong. The GPU tuple contradicts the existing
`gpu_trust_levels` authority and visual trust contract; the fixed-canvas
assertion proves neither the intended graph/dock presentation nor disjoint
tile rectangles. Keeping either literal would preserve a known defect.
This decision changes verification and presentation, not the GPU handoff
policy recorded in ADR 0022 or any network or privilege boundary.

The initial allocation harness also required an undeclared Xvfb executable.
Nested verification stopped at that prerequisite even though GTK was
installed. Requiring a separate X server was unnecessary for these widget
and geometry checks: GTK's bundled Broadway server allocates the same
widgets without a physical session. The display prerequisite changes;
the parity and non-overlap requirements remain intact.

## Decision

Proposed: replace those two implementation requirements with executable
contracts, keeping the existing M11 requirements for the full-width Networks
surface, segment dock and inspector visibility.

- Execute `TrustProvider` and the CLI trust renderer with controlled inputs,
  and compare the recovery GPU rungs, Networks dock and Create inspector
  against their ranks. A changed provider ladder must change every readback;
  missing or invalid input must never create fallback ranks. Services remains
  outside the ladder. Owner highlighting uses the effective GPU profile.
- Allocate production Networks widgets with production CSS on a private
  Broadway display using the server bundled with GTK 4. Require all five
  segment rectangles to be disjoint at the tested viewport sizes and with
  taller content. Use measured grid rows instead of
  fixed coordinates; keep the existing scroller and selected detail dock.
- Have the M11 contract invoke both checks, so its standalone entrypoint
  retains GPU and Networks coverage. Neither check may be skipped when its
  runtime dependency is missing. Catalogue and execute regression mutations.

## Consequences

The old visual implementation is no longer mandatory. The intended
readbacks and geometry have stronger, executable evidence. Verification
requires GTK introspection and `gtk4-broadwayd`, shipped with Arch's existing
`gtk4` desktop dependency, as well as the existing Python tools. Hosted CI
installs the equivalent GTK tools and bindings. The allocation entrypoint
also runs with Xvfb absent from PATH: an undeclared X server dependency must
not return. Both Broadway sockets use a private temporary runtime directory,
without a TCP listener or browser. Missing tools, failed startup and worker
failures remain failures. The tests use isolated displays and inert data;
they do not accept physical Nitro placement or identify the installed
Machine bridge failure.

## Implementation status

Built and software-verified by `tests/recovery_gpu_ladder_contract.py`,
`tests/recovery_network_layout_contract.py` and their M11 entrypoint.
Reversing the ranks or restoring the fixed canvas makes the respective
contract fail; restoring the sources makes it pass. Nitro visual acceptance
and the operator's decision on this proposal remain open.
