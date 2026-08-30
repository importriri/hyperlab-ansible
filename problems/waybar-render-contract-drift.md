# Waybar render contracts drifted away from the visible shell

Author: [importriri](https://github.com/importriri).

Status: resolved by semantic render contracts.

## Symptom

Desktop shell changes removed or rerouted visible Waybar elements while older
render checks still depended on positional result indexes, hidden compatibility
modules or one optional module ordering.

A static gate could therefore protect an implementation detail that the visible
bar no longer used, or fail when an unrelated rendered file changed position.

## What changed

The shell cleanup removed retired Cava and other dead Waybar paths instead of
keeping hidden modules alive only to satisfy old tests.

The render gate now checks the semantic contract: required module namespaces,
resolved click routes, allowed state classes and the relationship between the
Waybar action and `hyperlabctl`.

Optional ordering is not treated as identity. The visible shell can evolve
without shifting a numeric `slurp` result index becoming a false regression.

## Regression rule

A render test must name the behavior it protects.

For Waybar that means verifying the mounted modules, their routes and their
policy boundary. It must not require dead configuration solely because a
historical test once indexed it.

Runtime visibility remains a separate Nitro gate. A semantically correct JSON
render is not proof that the bar is actually visible after Sway reload.
