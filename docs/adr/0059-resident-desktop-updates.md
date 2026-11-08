# ADR 0059 - Refresh resident presentation after desktop deployment

Status: Proposed.

## Context

On 2026-11-03 the Nitro had new QML and recovery Python files on disk but
showed the older versions held by long-running processes. The Quickshell
unit deliberately disables watching to avoid loading a partially copied
tree. The GTK GApplication forwards new invocations to its existing owner;
its theme reload refreshes appearance without loading new Python code.

## Decision

Proposed: make changed code notify deferred Ansible handlers that execute
as the configured desktop user, after the play finishes its copies. Shared
QML changes try-restart only the already active `hyperlab-quickshell.service`.
Recovery Python changes invoke the existing GApplication quit action and
wait for its bus owner to disappear. The next ordinary recovery open loads
the installed code. Unrelated helper changes do not refresh either surface.
Keep the single helper-copy loop and gate its handler on that loop's
registered result for the Python manager, preserving the executable-copy
deployment invariant while distinguishing changes to unrelated helpers.

Use a shared deployment-only script transferred by Ansible, without a new
installed helper, IPC receiver or persistent watcher. Derive the user bus
from the non-root executing UID and validate its runtime directory and
socket before contacting it. An absent session is explicitly reported;
invalid transports and failed refreshes fail the apply. Never activate an
inactive shell or absent recovery application. Check mode sends nothing;
unchanged copies do not notify handlers.

Keep source watching disabled. A restart after the copies uses the existing
managed-service boundary and works with older resident code. A new QML IPC
receiver would itself be unavailable in the process that needs its first
update. A theme reload cannot replace the resident GTK interpreter's code.

## Consequences and evidence

Shell UI state and unsaved forms are lost; the recovery UI closes. Shell
child transports can be interrupted, so desktop updates belong between
interactive operations. Durable operations retain their existing separate
runner. No compositor, session target or Machine lifecycle command is sent.
Only `admin_user`'s managed shell and recovery bus owner are covered;
manually launched Quickshell instances are outside this refresh path.

The contract parses real role notifications and handler arguments,
exercises transport refusals and failure paths, and runs isolated Ansible
copies twice to verify deferred coalescing and the unchanged second pass.
Installed-host behavior and the physical Nitro/Predator campaign remain
open. The deployment-to-user-session bridge requires acceptance of this
proposal; software verification alone is not hardware acceptance.
