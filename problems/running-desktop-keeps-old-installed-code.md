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

Changed QML now notifies a deferred handler that try-restarts only the
active shell service as the desktop user. Changed recovery Python notifies
a separate handler that uses its existing quit action and waits for the
resident bus owner to leave. The next manager open loads the new file.
The helper-copy loop stays intact; its registered per-file change results
gate the GTK handler so unrelated helper changes cannot close the UI.
Both source headers change with this correction, so its first deployment
also notifies already stale residents whose installed files were current.
No compositor reload or Machine operation is requested. The handlers work
with the older resident versions because they use existing control routes.

The proposed deployment boundary and UI-state consequences are in
[ADR 0059](../docs/adr/0059-resident-desktop-updates.md). The structural and
behavioral contract is `tests/shell_reload_after_apply_contract.py`;
mutations are recorded in `tests/MUTATIONS.md`. Software checks cover
changed-only dispatch, an unchanged second apply, check mode, inactive
surfaces, redirected transports and failed refreshes. Physical acceptance
still requires a changed symbol appearing after a host apply without an
operator restart, then an unchanged pass with no refresh, and a recovery
manager open that displays the newly installed code.
