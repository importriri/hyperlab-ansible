# ADR 0061 - Refresh resident presentation after desktop deployment

Status: Proposed.

## Context

On 2026-11-03 the Nitro had new QML and recovery Python files on disk but
showed older versions held by long-running processes. Quickshell's unit
intentionally disables watching during multi-file deployment. The GTK
GApplication forwards new invocations to its resident owner; theme reload
changes appearance without loading new Python code.

## Decision

Proposed: reconcile presentation from state on every apply as the configured
desktop user. `host_desktop_common` checks after its QML and observer copies,
`host_desktop_sway` checks after its recovery helper copies, and `v1-host.yml`
checks the shell again after the Hyprland component's final service-unit
copy. The Hyprland role continues to stage files and runs nothing. The
final check covers a unit-only change during its installing apply; an
unchanged second apply dispatches no refresh. The QML checks carry the
copy's `hyperlab_provenance` tag. Check mode dispatches nothing.

Freshness uses SHA-256 over sorted source paths and contents, including the
installed shell unit and every regular file under the shell root except
live-watched `features.json`. It also covers every executable in
`RESIDENT_OBSERVERS`, the validated `/etc/hyperlabctl/checkout` pointer and
that checkout's `tools/surface_provenance.py` resolver. The common-role
check follows its last observer copy; the final v1 check also follows the
Sway status bridge and checkout pointer copies. Changing only an observer
therefore refreshes the shell and its resident readers during that apply.
The GTK generation covers its executable.

Freshness does not compare file dates with reconstructed process dates: the
current realtime-minus-boottime offset is not the offset when an old
process started. A forward clock step can hide stale code indefinitely;
a backward step can cause repeated refreshes. Content generations and
boot-relative process identities avoid both errors, including unchanged
retries after a failed apply.

Each surface has a private, mode-0600, user-owned checkpoint in the validated
user runtime directory. It records the generation, kernel boot ID, a
boot-relative tick boundary and, for the shell, the successfully refreshed
PID and its start ticks. A resident is current only for that generation
and boot, with either that exact identity or start ticks strictly after
the boundary. A missing checkpoint means one conservative refresh of an
active resident, even if it already runs the installed code. Checkpoints
live in `/run/user/UID`, so this can recur on the first apply after every
login that recreates that directory (normally after the last logout), and
after every reboot. That apply reports `changed=1` and loses open shell
surfaces, selection and unsaved forms, or closes a resident recovery UI,
even when no source file changed. An absent GTK owner establishes a boundary
without starting it; an ordinary later open loads the installed code.
Checkpoints are locked against concurrent refreshes and reject redirected, hard-linked,
public, oversized, duplicated or malformed input. They are updated only
after success or an observed absent GTK owner. Failed refreshes leave the
previous generation pending; concurrent source changes cause refusal.

A shell refresh uses the existing `Restart=on-failure` policy without a
whole-unit restart job:

1. Reload the user's service definitions and recheck the same active main
   PID, cgroup and effective restart policy.
2. Wait up to ten seconds for unknown, unreadable or foreign cgroup children
   to finish while the shell continues running and showing current host
   trust and provenance. Only its exact read-only observer commands and
   their own descendants may remain; otherwise refuse with the busy PIDs.
3. Open a PID file descriptor, validate the process start ticks and send
   `SIGSTOP`. Inspect thread states once; a previously stopped shell or
   any thread not yet stopped is refused. Inspect the cgroup and its
   descendants once while the shell cannot launch anything. Any busy child
   appearing since the live inspection causes immediate refusal and resume.
   There is no sleep, deadline polling or idle wait during the pause.
4. Send `SIGKILL` through that same descriptor without resuming the shell.
   The existing service policy restarts it and cleans up its observers.
   Wait for an active, different process identity before saving success.
   On a refusal or exception before termination, resume the pinned shell.

This closes the launch race between inspection and termination. A normal
restart job sends `SIGCONT` during shutdown, which would reopen that race.
`SIGKILL` cannot execute QML or a shutdown handler. These signal semantics
are described by [Linux signal(7)](https://man7.org/linux/man-pages/man7/signal.7.html)
and [systemd.kill](https://github.com/systemd/systemd/blob/main/man/systemd.kill.xml).
A PID descriptor avoids signalling a reused PID.

The observer list equals the commands in `ShellState.qml`. This includes
the adapter's fixed `product-identity` read added with the display name:
it reads deployed cosmetic identity without contacting a compositor. The
exact-list equality check remains unchanged. The provenance bridge replaces
itself with `/usr/bin/python3 -I -B` and the checkout's
`tools/surface_provenance.py`. Accept that post-exec form only with the
exact resolver path, repository, proc-root, stream and per-user registry
arguments from an unredirected, single-line checkout pointer. It must still
be a child of the shell or of an accepted observer. Arbitrary Python
commands remain busy. Workspace and focus watches are exercised too.

For GTK, query the existing GApplication owner without activation. An
unknown or stale owner receives the existing `quit` action, with a bounded
wait until the bus name is unowned. The next normal open loads new code.
The user bus is derived from the executing non-root UID, with ownership,
mode and socket validation; absence is an explicit no-session result.
Invalid transports, failed commands and deadlines fail the apply.

## Ruled out

- Notification-only handlers: a later failed task drops them, and unchanged
  copies on retry never notify again.
- Quickshell's watcher: it can reload an incomplete multi-file copy.
- A new QML reload receiver or notice-only state in Diagnostics: the old
  resident needing its first update cannot contain either receiver or
  notice. A notice also leaves manual intervention necessary.
- GTK `--reload-theme`: it keeps the old interpreter code.
- Age comparisons using the current wall-clock offset: clock corrections
  can hide updates or destroy idempotence.
- Another cgroup sample before `try-restart`: a shell can launch a child
  after any unsynchronized sample. Freezing only until a graceful restart
  is insufficient because shutdown resumes the main process.
- `KillMode=process`: it would change normal session cleanup and leave
  unowned observer processes. Session lifecycle remains unchanged.

## Consequences and evidence

Open surfaces, selection and unsaved forms are lost; GTK closes. The shell
keeps running during the bounded idle wait. The pause contains only the
thread and cgroup inspections and the final signal, normally milliseconds;
if stopping is incomplete, resume immediately and retry on a later apply.
This replaces the former paused idle wait and stopped-thread polling.
The successful replacement is deliberately abrupt, and its journal records
a signal failure followed by the existing automatic restart. If the refresh
script itself is forcibly killed while the shell is stopped, its cleanup
cannot run; the operator must resume that shell before retrying. External
session/service manipulation during this short critical section is not
coordinated by this mechanism. These remain physical acceptance concerns.

An operation already dispatched by `privatestack-operation` runs in its own
`hyperlab-operation-<id>` user unit. An operation bridge still in the
shell's cgroup counts as busy. Operation rediscovery is not verified here.
The GTK quit action ends its process; its children are not inspected. Only
`admin_user`'s managed shell and recovery owner are covered. No compositor,
session target or Machine lifecycle command is sent.

The topology contract previously required every v1 entry to be an import;
that approximation prevented a final deployment boundary. It now permits
exactly the reviewed reconciliation play in exactly its final-desktop
position. Arbitrary inline tasks, changed commands, extra roles and
component launches remain refused. Role and import uniqueness checks stay.

The contract exercises real observer argv, all-thread pausing, a real inert
launcher with a queued post-inspection launch, immediate late-child refusal,
zero sleeps or monotonic waits while paused, busy-child survival,
checkpoint refusals, both clock-step directions and failed unchanged
retries. Generation checks cover every observer executable and the checkout
resolver. Isolated Ansible copies cover adapter-only and unit-only deployment
followed immediately by `changed=0`, later failures, refresh failures, stale
residents, unrelated helpers and check mode. Software verification does not
establish installed Nitro or Predator behavior. Acceptance remains open.
