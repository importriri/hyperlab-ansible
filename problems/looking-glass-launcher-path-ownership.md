# Looking Glass Control Center launch depended on PATH resolution

Author: [importriri](https://github.com/importriri).

Status: candidate fix; Nitro runtime button proof pending.

## Symptom

Every Control Center Looking Glass surface correctly converged on the
`vm.looking-glass` action, and the action registry correctly resolved that to
`hyperlabctl open looking-glass <domain>`.

The final opener still built its argv with the bare executable name
`looking-glass-client`.

On the validated Nitro host that name currently resolves to
`/usr/local/bin/looking-glass-client`, which is the client built from the pinned
Looking Glass checkout with the reviewed captured-input compatibility patch.
The launcher contract itself did not guarantee that result, however.

## Root cause

The opener delegated the final executable choice to PATH. That was convenient
while the client was installed under `/usr/local/bin`, but it left the graphical
launch surface dependent on session PATH ordering. A distro package, user-local
wrapper or future environment change could therefore select a different client
without changing the Control Center or action registry.

This was a launch-ownership ambiguity, not evidence that the validated Nitro
runtime had already opened the wrong executable.

## Fix

`hyperlabctl open looking-glass` now names
`/usr/local/bin/looking-glass-client` explicitly. The existing `_executable`
guard therefore validates that exact executable before `os.execv` replaces the
CLI process.

The toolbar, quick button, inspector button and primary VM action remain
unchanged. They continue to converge on `vm.looking-glass`, so executable
ownership stays centralized rather than being duplicated across GUI surfaces.

A structural contract now pins the complete chain:

Control Center -> `vm.looking-glass` -> action registry ->
`hyperlabctl open looking-glass` -> `/usr/local/bin/looking-glass-client`.

## Regression gate

The HyperLab CLI component suite and repository verifier must pass. On the Nitro
hardware, opening Looking Glass from the Control Center must produce a process
whose `/proc/<pid>/exe` resolves to `/usr/local/bin/looking-glass-client`.
The running executable hash must match the installed managed client.
