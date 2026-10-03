pragma Singleton
import QtQuick
import Quickshell

// Workspaces are plain objects: `id` cannot be declared on a QML object.
QtObject {
    property var focusedWorkspace: ({ "id": 11 })
    property var focusedMonitor: ({ "name": "HEADLESS-0" })
    property QtObject workspaces: QtObject { property var values: [] }

    signal rawEvent(var event)

    function refreshWorkspaces() {}

    function dispatch(request) {
        QsHarness.record(["hyprland-dispatch", request]);
    }
}
