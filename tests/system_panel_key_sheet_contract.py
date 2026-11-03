#!/usr/bin/env python3
"""The system panel opens the existing searchable host key sheet."""
from __future__ import annotations

import shutil

import host_quickshell_runtime_contract as runtime

SCENARIO = '''
            sharedSurfaces.toggleSystemPanel("@@OUTPUT@@");
            const entry = find(@@PANEL@@, "system-host-keys");
            check(entry !== null && entry.visible && entry.enabled,
                  "system panel has no available host key sheet entry");
            const sheetComponent = Qt.createComponent("HostKeys.qml");
            check(sheetComponent.status === Component.Ready, "HostKeys failed to load");
            const sheet = sheetComponent.createObject(window);
            const sheetRows = sheet.groups.reduce((rows, group) => rows.concat(group.keys), []);
            const keys = sheetRows.filter(row => row.does === "This key sheet");
            check(keys.length === 1 && entry !== null
                  && entry.value.replace(/\\s/g, "") === keys[0].keys.replace(/\\s/g, ""),
                  "system panel advertises a different key-sheet chord than HostKeys");
            sheet.destroy();
            if (entry !== null) entry.activated();
            check(!sharedSurfaces.systemPanelOpen && @@LAUNCHER@@.open && @@LAUNCHER@@.keysMode,
                  "system panel did not open the existing key sheet");
            check(sharedSurfaces.ownsTransient("launcher", "@@OUTPUT@@"),
                  "panel key sheet moved to another output");
            check(@@LAUNCHER@@.results.filter(row => row.kind === "key").length >= 20,
                  "panel key sheet did not list HostKeys");
            check(sharedActions.invoked.length === 0,
                  "panel key sheet dispatched a host command");
'''


def main() -> int:
    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    assert runner, "Qt 6 qmlscene is required for system panel activation"
    directory = runtime.stage()
    try:
        for width, height in ((1920, 1080), (800, 600)):
            for output, panel, launcher in (("eDP-1", "systemPanel", "launcher"),
                                            ("HDMI-A-1", "systemPanelExternal", "launcherExternal")):
                body = (SCENARIO.replace("@@OUTPUT@@", output).replace("@@PANEL@@", panel)
                        .replace("@@LAUNCHER@@", launcher))
                source, messages = runtime.scenario_source(width, height, runtime.machines(4), body)
                runtime.run(runner, directory, "system-panel-keys-" + output, source, messages)
    finally:
        shutil.rmtree(directory)
    print("System panel key sheet contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
