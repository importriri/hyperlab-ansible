# HyperLab keybinding security

Keyboard ownership is a security boundary.

HyperLab deliberately assigns different compositor namespaces to host and
guest systems:

- host Sway and host Hyprland use `SUPER`;
- managed Linux guests use `ALT`;
- Looking Glass retains `RightCtrl` as its transport escape key.

The guest namespace is deliberately different even though Looking Glass
captured-input mode inhibits host shortcuts. Namespace separation remains a
defence-in-depth property for focus transitions, recovery paths and future
transport changes.

## Fullscreen history

On 2026-09-04 several transport-oriented fullscreen bindings were explored,
including F11 and modifier/F11 variants. Those experiments were removed after
the input experiments were closed. The guest source was restored to its public
local fullscreen baseline.

The current separation milestone does not revive those rejected experiments.
It moves the guest local compositor namespace from `SUPER` to `ALT`, therefore
guest fullscreen becomes `Alt+F` while host fullscreen remains `Super+F`.

## Complete cheatsheets

The future HyperLab cheatsheet is generated from the binding model rather than
maintained as an independent handwritten list.

"Complete" is scope-sensitive:

- the host operator view may describe the complete authorized host binding set;
- a guest view contains every effective binding authorized for that guest, but
  no host or hypervisor control-plane information.

Guest exposure is default-deny. Guest-facing artifacts may consume only
`guest-local` and explicitly reviewed `transport-safe` entries. Host-only,
privileged, recovery-sensitive and hypervisor-internal entries are forbidden.

The guest view must not reveal host paths, other-domain inventory, host network
topology, privileged routes, VFIO internals, Ly/session internals or unrelated
trust metadata.

A generated cheatsheet must therefore satisfy both correctness and
information-boundary contracts before it can be installed.
