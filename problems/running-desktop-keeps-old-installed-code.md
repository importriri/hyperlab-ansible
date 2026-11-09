# Running desktop keeps code from before the last apply

## Observation

On the Nitro on 2026-11-03, host applies installed new shell files in
`/etc/xdg/quickshell/hyperlab/`, including geometry B in `IsolationGlyph.qml`
at 06:49. The bar and idle desktop still drew the older symbol. The
`qs -c hyperlab` process in `hyperlab-quickshell.service` had started on
2026-10-24, and its journal showed no reload since then. Restarting that
user service made the installed symbol visible.

The GTK recovery Control Center also kept old code: a resident
`privatestack-hyperlab-domains --reload-theme` started on 2026-10-26 by
`privatestack-theme cycle` served subsequent manager opens with the obsolete
GPU ladder, despite the executable on disk having been replaced. This could
make a physical check silently exercise a previous version.

## Cause

The Quickshell unit explicitly sets `QS_DISABLE_FILE_WATCHER=1`. Upstream
documents that this [disables hot reloading](https://quickshell.org/docs/v0.3.0/guide/advanced/).
It prevents an intermediate reload during the role's recursive multi-file
copy, but the role had no deferred refresh notification. Ansible's copy
uses atomic replacement per file; that does not make the directory update
atomic. There is no evidence here of a watcher losing an atomic rename:
watching was deliberately disabled.

The GTK single-instance application holds itself warm and routes commands
to its existing GApplication owner. `--reload-theme` calls `reload_theme()`
on cached windows. It does not execute the newly installed Python file in
the primary process. The existing Sway session helper replaces that owner
on a compositor reload, but an ordinary apply need not reload Sway and the
preferred compositor has its own session path.

## Fix and verification

A first fix notified deferred handlers from the changed copies. Review
showed that it could repeat the failure: Ansible runs notified handlers at
the end of the play, so a later failing task drops them, and the next apply
finds the copies unchanged and never notifies again. The fix now decides
from state on every apply, with content-generation checkpoints bound to
boot-relative process identities. It never reconstructs an old start date
from today's realtime offset: a forward clock correction could hide an
update indefinitely, while a backward step could repeatedly restart it.
A failed refresh does not advance the checkpoint, so unchanged retries
still find the installed generation pending.

The shell's provenance bridge uses `exec` to become the checkout's Python
resolver. Matching only the bridge argv falsely marked this permanent
observer busy. The check now validates the resolver's exact path, flags,
repository, proc-root, registry and parent. Every original observer command,
including workspace and focus watches, is exercised too.

A cgroup sample followed by a restart also had a launch race: an action or
application could appear after inspection and be killed by shutdown. The
refresh now reloads the manager first, pauses the pinned shell process and
confirms every thread stopped before inspecting the cgroup and descendants.
Unknown children cause a bounded refusal and the shell resumes, killing
nothing. Otherwise the still-paused main process receives a pinned
`SIGKILL`; its existing on-failure service policy starts a new shell and
cleans up the read-only observers. No normal restart job can resume the
old shell between inspection and termination.

Finally, the Hyprland component copies the service unit after the common
role. Reconciling only in the common role left unit-only changes pending
until an unchanged second apply. A final play in `v1-host.yml` now checks
after that unit copy, while Hyprland remains staging-only. The topology
contract permits exactly that final task and continues to refuse arbitrary
inline tasks and component launches. The immediate second pass is inert.

The proposed boundary and UI-state consequences are in
[ADR 0061](../docs/adr/0061-resident-desktop-updates.md). The contract is
`tests/shell_reload_after_apply_contract.py`; mutations are recorded in
`tests/MUTATIONS.md`. Software checks include both clock-step directions,
failed unchanged retries, a real inert launcher queued after inspection,
busy-child survival, exact observer identities, unit-only deployment and
an immediate `changed=0` pass. They send no compositor reload or Machine
operation. Physical acceptance still requires a changed symbol appearing
after a host apply without an operator restart, a recovery manager open
showing the installed code, and an unchanged apply with no refresh.
