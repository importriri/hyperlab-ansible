# Three faults the offscreen shell harness surfaced before any guest did

Author: [importriri](https://github.com/importriri).

Status: corrected in source; the runtime contract fails on any of them.

The guest Workspace Shell is first run offscreen: the real QML, a plain Qt 6
`qmlscene`, and Quickshell stand-ins from `tests/quickshell_stubs`. The
harness treats any unexpected line on stderr as a failure. Its first runs
found three faults that would otherwise have reached the guest as warnings in
the shell log or as a broken surface.

## `Theme.palette` shadowed `Item.palette`

`Theme.qml` is an `Item` and declared `property var palette` for the guest
colours. Qt 6 warns that the member overrides `Item.palette`, the Qt Quick
Controls palette every `Item` already has; a control placed inside the theme
would have read the wrong object. The property is now `colours`.

## A wrapped error banner fed its own height

The overview's refused-configuration banner computed its height from the
text's `implicitHeight` while the text was anchored to fill the banner. Wrapped
text recomputes its implicit height from its geometry, so the two formed a
binding loop and Qt reported it on every refusal. The text is now positioned
and sized by width only, and the banner follows it.

## An island's click area anchored outside its parent

`ContextIsland` put a `MouseArea` into the island's content holder and
anchored it to the island's surface, which is not its parent or sibling; Qt
refused the anchor and the click did nothing. `Island` now owns the click
area beside its surface, and an island opts in with `clickable: true`.

## Harness faults on the way

Two faults were in the stand-ins, not the shell, and are recorded because
they look like shell faults when they appear:

- a stand-in module whose `qmldir` declares no type is reported as
  `module "Quickshell.Wayland" is not installed`; the Wayland stand-in now
  declares `WlrLayer`;
- `HyprlandWorkspace.id` cannot be declared on a QML object, because `id` is
  reserved; the Hyprland stand-in uses plain objects for workspaces.

## Regression proof

`tests/guest_workspace_shell_runtime_contract.py` runs six scenarios and fails
on any stderr line it does not expect, including the three warnings above.
