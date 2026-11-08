# ADR 0059 - Refresh resident presentation after desktop deployment

Status: Proposed.

## Context

On 2026-11-03 the Nitro had new QML and recovery Python files on disk but
showed the older versions held by long-running processes. The Quickshell
unit deliberately disables watching to avoid loading a partially copied
tree. The GTK GApplication forwards new invocations to its existing owner;
its theme reload refreshes appearance without loading new Python code.

## Decision

Proposed: reconcile running presentation with installed code from state on
every apply, not from a one-shot change notification. After its copies,
each role runs an ordinary task as the configured desktop user:

- `host_desktop_common`, after the shared QML copies, compares the newest
  installed time of every regular file under `/etc/xdg/quickshell/hyperlab`
  and of `/etc/systemd/user/hyperlab-quickshell.service` with the start time
  of the active shell's main PID. If the shell is older, or the user
  manager reports that the unit needs a daemon reload, it reloads the user
  manager and `try-restart`s only that already active unit.
- `host_desktop_sway`, after the helper copies, compares the recovery
  manager executable with the start time of the process that owns the
  GApplication bus name. If it is older, it invokes the existing `quit`
  action and waits for the owner to leave. The next ordinary open loads the
  installed code.

The installed time is the later of modification and status-change time, so
an atomic replacement that keeps an older modification time still counts.
`features.json` is excluded: `ShellState.qml` already watches it live.
A task reports `changed` only after an actual refresh, so an unchanged
second pass is `changed=0`. Because the decision comes from state, a play
that failed after the copies, a refresh that failed, a tagged run or a
resident that was already stale before this change is corrected by the
next apply. The QML reconciliation carries the same tag as the tagged QML
copy.

Restarting the unit ends every process in its control group. The shell
always runs read-only observers there (workspace and focus watches, the
trust stream, the provenance resolver and status polls), which the new
shell starts again. Before restarting, the script reads the unit's control
group and its descendants and identifies each other process by parent and
argv. Only the exact commands `ShellState.qml` starts, and processes they
started, may be ended. For any other child (a Machine operation bridge,
a launched application still in the unit, a process it cannot read) it
waits up to ten seconds for the child to finish, then refuses: the task
fails with the PIDs, nothing is killed, and the next apply retries.

Use a shared deployment-only script transferred by Ansible, without a new
installed helper, IPC receiver or persistent watcher. Derive the user bus
from the non-root executing UID and validate its runtime directory and
socket before contacting it. An absent session is explicitly reported;
invalid transports and failed refreshes fail the apply. Never activate an
inactive shell or absent recovery application. Check mode sends nothing.

## Ruled out

- Notification-only handlers. A handler is dropped when a later task in the
  play fails, and the next apply finds the copy unchanged and never
  notifies again. That repeats the 2026-11-03 failure silently.
- Quickshell's own file watcher. It would reload part-way through a
  multi-file copy and load mixed versions.
- A new QML IPC receiver for reload. The process that needs its first
  update does not yet contain it.
- `--reload-theme` for the recovery UI. It refreshes the palette of the
  existing interpreter, not its code.
- A visible "installed differs from running" notice in the shell and in
  Diagnostics, without a refresh. It needs new QML state and a new
  installed stamp, and it still leaves the operator to restart by hand.
  It cannot appear in an old resident shell either, which is exactly the
  case to cover. The refusal above already makes a pending refresh visible
  in the apply output, and the restart itself is bounded to the managed
  unit.

## Consequences and evidence

Shell UI state and unsaved forms are lost; the recovery UI closes. A busy
shell makes the apply fail until the operator finishes or closes the busy
child; that failure is deliberate and names the PIDs. An operation that
`privatestack-operation` has already dispatched runs in its own
`systemd-run --user` unit (`hyperlab-operation-<id>`), outside the shell's
control group; its bridge process still in the shell's group counts as
busy until it exits. This refresh has no test of operation rediscovery by
the restarted shell. The GTK `quit` action ends the recovery UI's
process; work it started itself is not inspected by this refresh.

Residual cases: the unit file is copied by `host_desktop_hyprland`, whose
play follows the common role and which by its own contract runs nothing.
A change to the unit alone therefore reaches the running shell at the next
apply, which finds the unit newer than the shell. Covering it in the same
apply would need a playbook change or a refresh task in the inactive
Hyprland component; neither is part of this decision. A wall-clock step between the shell's start and the check
can misjudge age by the size of the step; a large forward step causes at
most one extra refresh. Only `admin_user`'s managed shell and recovery bus
owner are covered; manually launched Quickshell instances are outside this
path. No compositor, session target or Machine lifecycle command is sent.

The contract parses the real tasks, resolves the observer commands from
`ShellState.qml`, exercises timestamps, control-group refusals, transport
refusals and failure paths, and runs isolated Ansible copies with the real
freshness decision: a later failure followed by a retry, a failed refresh
followed by a retry, a unit-only change picked up by the next apply,
already stale residents, check mode and `changed=0` passes. Installed-host behavior and the physical
Nitro/Predator campaign remain open. The deployment-to-user-session bridge
requires acceptance of this proposal; software verification alone is not
hardware acceptance.
