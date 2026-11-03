# Recovery Networks tiles overlapped

## Observation

During the 2026-11-02 read-only Nitro capture, the GTK recovery Control
Center's Networks section (`--section policies`) drew Services over Clean.

## Cause and fix

The network canvas used `Gtk.Fixed` positions with 114 pixels between rows.
The shared CSS imposed a 138-pixel minimum tile height, with padding and
borders in addition. A real GTK allocation with that CSS measured each of
those tiles at 154 pixels high: Clean started at y=18 and Services at y=132.
Their rectangles therefore overlapped by 40 pixels.

A two-column `Gtk.Grid` now allocates each row from the measured heights of
its children. It preserves segment selection and the detail dock, and the
existing scroller accommodates taller content. There is no fixed tile height
or row coordinate to contradict the CSS or a larger text size.

The M11 contract previously required this defective implementation. Proposed
[ADR 0055](../docs/adr/0055-recovery-readback-verification.md) explains why
those literal requirements are replaced by the executable checks below.

## Regression proof and remaining gate

`tests/recovery_network_layout_contract.py` builds the production widgets
with production CSS in a private X server, allocates requested viewports of
760×560, 1000×760 and 500×560, and repeats with additional multiline tile
content. Every pair of segment rectangles must be disjoint. Restoring the
old builder reproduces the measured overlap and fails the contract.

The contract proves GTK allocation, not compositor placement on the Nitro.
Open Networks there and check all five segments and the selected detail.
