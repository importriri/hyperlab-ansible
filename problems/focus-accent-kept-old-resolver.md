# The host frame stayed grey over a Machine the bar already named

Author: [importriri](https://github.com/importriri).

Status: corrected in source and covered by the focus accent contract. The
physical recheck on `dev-01` is pending.

## Symptom

After the resolver learned to read projected Machines, the host bar named
the `dev-01` Looking Glass window **Dev**, but the window border stayed
neutral and the keyboard did not turn the dev colour.

## Root cause

Two processes ask the same resolver, `tools/surface_provenance.py`, about
the focused window: the bar's stream bridge and `hyperlab-focus-accent`,
which draws the border and the keyboard colour. The bridge was restarted
after the update. The accent service had imported the resolver once, at the
start of the session, from the checkout, and kept answering with the old
code, which could not see Machines.

## Fix

Before each resolution the accent service compares the resolver file's
modification time and size with the one it loaded and reloads it when they
differ. A resolver that fails to load leaves the previous one in place, so a
broken checkout never blanks the trust colours.

## Regression proof

`tests/focus_provenance_accent_contract.py` loads the service against a copy
of the resolver, requires an unchanged file to be kept, a changed file to be
used, and a file that does not parse to leave the last good resolver.
