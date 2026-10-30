# ADR 0054 - Supervise private Machine diagnostics at the typed bridge

Status: Proposed. The software is built and exercised with synthetic sources;
installed-shell and physical collection remain pending.

## Context

The selected Machine needs the existing private diagnostics collector's actual
archive path and honest source counts. Collection can take several minutes:
its host and guest sources run sequentially with individual timeouts. It is
neither a durable privileged lifecycle operation nor a long-lived connection.
The shell's short capability and dispatch requests cannot supervise it.

`tests/host_operation_integration_contract.py` forbade `subprocess.Popen`
anywhere in the bridge. That text assertion guarded the removal of detached
lifecycle launches. It cannot distinguish an unauthorized lifecycle launch
from a bounded foreground collector whose JSON and private output the bridge
must validate before returning a result.

## Decision proposed

Reuse the collector and action registry. The bridge rechecks product
membership, the checked spec and consistent live managed identity at execution.
It resolves running and shut-off collection through separate fixed registry
routes, using the existing `--host-only` interface for the latter.

Only `collect_diagnostics` supervises a subprocess in the Machine bridge. It
owns the collector's process group, waits at most 660 seconds, and terminates
and reaps it on timeout or interruption. The shell gives the entire request
750 seconds, then allows 5 seconds for cleanup before forcing bridge exit.
An immutable request id and Machine bind the result, with one collection in
flight and separate runners for capability, lifecycle and connections.

A saved result requires valid JSON for that Machine and scope and an actual
new, private archive. Only the path, scope and counts cross into presentation;
source contents and stderr do not. Missing sources make the result partial.
The archive stays local, and redaction does not clear it for sharing.

Keep managed lifecycle in the durable operation runner. Replace the blanket
text assertion with executed lifecycle entrypoints that trap subprocess
launches or direct execution, plus an AST check restricting subprocess
supervision to `collect_diagnostics`. The diagnostics contracts separately
exercise the real registry, collector, output validation and production QML
handlers with inert external commands. Mutating lifecycle back to a direct
spawn must still fail before any external process can run.

## Consequences

No new source, privilege, guest-agent RPC, SSH policy or sharing service is
introduced. Capability answers remain advisory. The host session is still
trusted; guest diagnostic text supplies no identity or trust claim.

The software tests and mutations do not close the Nitro/Predator gates.
The combined roadmap checkbox stays open until installed collection has
been observed on hardware.
