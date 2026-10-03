// The top layer of one output: the context island on the left and the
// status island on the right. The layer reserves its height so windows
// never slide under the islands, and only the islands take input.

import Quickshell
import Quickshell.Wayland
import QtQuick

PanelWindow {
    id: top

    required property var theme
    required property var deskState
    required property var stats
    required property var surfaces

    property var modelData

    screen: modelData

    anchors {
        top: true
        left: true
        right: true
    }

    implicitHeight: theme.gap + theme.islandHeight
    exclusiveZone: theme.gap + theme.islandHeight
    color: "transparent"

    WlrLayershell.namespace: "hyperlab-workspace-top"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    mask: Region {
        item: contextIsland

        Region { item: statusIsland }
    }

    ContextIsland {
        id: contextIsland

        x: top.theme.gap
        y: top.theme.gap
        theme: top.theme
        deskState: top.deskState
        surfaces: top.surfaces
    }

    StatusIsland {
        id: statusIsland

        x: top.width - width - top.theme.gap
        y: top.theme.gap
        theme: top.theme
        stats: top.stats
    }
}
