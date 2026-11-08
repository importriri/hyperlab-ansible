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
from state on every apply. After the copies, a task run as the desktop user
compares the newest installed shell file and the unit file with the start
time of the active shell's main process, and restarts only an active,
older shell. A second task compares the recovery manager executable with
the start time of the GApplication bus owner and uses its existing quit
action only when that owner is older. Either task reports `changed` only
after an actual refresh, so an unchanged pass stays `changed=0`, and a
failed earlier apply or an already stale resident is corrected next time.

The same review found that the restart ends every process in the unit's
control group, and the shell always runs watcher children there. The
refresh therefore ends only the read-only observers that `ShellState.qml`
starts (and their own helpers). Any other child makes it wait briefly and
then refuse with the PIDs, killing nothing. No compositor reload or
Machine operation is requested. Both tasks work with the older resident
versions because they use existing control routes.

The proposed deployment boundary and UI-state consequences are in
[ADR 0059](../docs/adr/0059-resident-desktop-updates.md). The structural and
behavioral contract is `tests/shell_reload_after_apply_contract.py`;
mutations are recorded in `tests/MUTATIONS.md`. Software checks cover a
later failure and retry, a failed refresh and retry, a unit-only change
picked up by the next apply,
already stale residents, check mode, inactive surfaces, busy control
groups, redirected transports and an unchanged second apply. Physical
acceptance still requires a changed symbol appearing after a host apply
without an operator restart, then an unchanged pass with no refresh, and a
recovery manager open that displays the newly installed code.
