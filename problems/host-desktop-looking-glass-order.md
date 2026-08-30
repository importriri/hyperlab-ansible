# Looking Glass host integration depended on the desktop landing first

Author: [importriri](https://github.com/importriri).

## Symptom

A host that had previously been assembled partly by hand could make the Looking
Glass role appear independent from the desktop role. A clean pipeline exposed
that assumption: the integration expected desktop/session resources that were
not yet guaranteed to exist.

## What was wrong

Looking Glass on this host is not only a package and kvmfr device.

The repository also owns compositor integration, client configuration, session
behavior and user-facing launch paths. Those contracts belong on top of the
managed desktop/session baseline. Treating the desktop as optional made role
ordering depend on historical machine state.

## Fix

Make the desktop stage a prerequisite of Looking Glass host integration.

The clean-build contract is now the authority. A machine that happens to carry
leftover manual configuration must not be used to justify a weaker dependency
graph.

This ordering also keeps file-manager, media, Wayland and session tooling in one
desktop baseline before Looking Glass adds its own compositor-facing behavior.

## Regression proof

Rebuilding the host through the repository reproduced the earlier manually
prepared baseline once desktop reconciliation ran before Looking Glass.

The dependency is kept explicit so an ArchISO-to-lab rebuild cannot succeed only
because a test laptop already contained session configuration from an older
manual setup.
