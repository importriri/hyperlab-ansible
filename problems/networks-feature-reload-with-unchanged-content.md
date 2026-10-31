# A successful feature reload must reapply unchanged content

The native Networks feature document is a watched root-owned input. Its file
notification handler clears enablement before reloading, so an unreadable
replacement cannot keep an old opt-in enabled. That also means a successful
read must restore the flag even when the document contains the same bytes.

Handling only `textChanged` left that second transition uncovered. In the
executed fixture, the file notification disabled the page, then `loaded`
arrived without `textChanged`: the valid true document stayed disabled.
This was found and corrected before physical acceptance of the page.

## Fix

`ShellState.qml` applies the feature document on every successful `loaded`
signal and disables it on `loadFailed`. The file notification still clears
cached enablement before requesting the reload. The parser accepts only the
single literal boolean, so a successful read cannot enable malformed,
duplicate-key or nonboolean content. No shell restart or network action is
needed.

## Regression proof

`tests/host_quickshell_runtime_contract.py` retains the production FileView
handlers with inert file transport. The disabled-page scenario loads true,
sends a file notification, requires disabled, then sends only `loaded` with
the same content and requires enabled again. Reverting to the text-change
handler fails with "successful unchanged feature reload did not restore
enablement"; restoring the load handler passes. Missing and unreadable files
still disable the page. These are software fixtures; installed watcher
delivery and physical navigation remain acceptance checks.

The workspace/theme contract now checks the exact names of the watched
FileViews: keyboard layout, reduced motion and this feature document.
It preserves the session appearance restriction: the theme file remains
unwatched. Removing either required watcher or adding a theme watcher fails.
