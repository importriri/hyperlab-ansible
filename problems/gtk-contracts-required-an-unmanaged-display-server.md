# Recovery GTK contracts required an unmanaged display server

## Observation

The full verification battery failed in the nested lab after a successful,
idempotent host reconciliation. The GPU ladder and Networks allocation
contracts, including their M11 entrypoint, stopped with "Xvfb is required
for recovery layout allocation".

## Cause and fix

The new checks started a private X server, but Xvfb was neither a managed
desktop dependency nor part of the verification toolchain. Its presence in
one development environment hid the missing prerequisite. The hosted CI
toolchain also omitted the GTK introspection bindings these checks import.

The shared runner now starts `gtk4-broadwayd`, bundled with the existing
Arch `gtk4` dependency ([package files](https://archlinux.org/packages/extra/x86_64/gtk4/files/)).
GTK's [Broadway backend](https://docs.gtk.org/gtk4/broadway.html) allocates the
same production widgets without a browser. The display and HTTP sockets
stay in a private temporary runtime directory; no TCP listener or physical
desktop session is needed. The server stays alive until the worker exits,
then is terminated and reaped. Missing tools and failed startup still fail,
and the worker's exit status is returned unchanged.

The hosted workflow declares GTK's tools, typelib and Python bindings;
the contributor setup lists their Arch and Ubuntu packages.

## Regression proof and remaining gate

The Networks entrypoint supplies a PATH containing only `gtk4-broadwayd`
and invalid inherited X11 and Wayland displays. Before the runner repair,
this reproduced the Xvfb assertion; afterwards all real allocation checks
passed. Restoring the Xvfb runner makes it fail again. Restoring the old
fixed-coordinate Networks builder still detects overlapping rectangles
under Broadway, and reversing the GPU order still fails CLI parity.

The nested verification and physical Nitro checks must still be rerun on
the repaired tree. This display change adds no hardware evidence.
