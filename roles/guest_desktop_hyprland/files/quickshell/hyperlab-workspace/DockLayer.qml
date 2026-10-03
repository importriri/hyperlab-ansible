// The bottom layer of one output: the dock, centred. Like the top layer it
// reserves its height and only the dock itself takes input.

import Quickshell
import Quickshell.Wayland
import QtQuick

PanelWindow {
    id: bottom

    required property var theme
    required property var deskState
    required property var surfaces

    property var modelData

    screen: modelData

    anchors {
        bottom: true
        left: true
        right: true
    }

    // Taller than the space it reserves: slot names appear above the dock.
    implicitHeight: theme.dockHeight + theme.gap + 44
    exclusiveZone: theme.dockHeight + theme.gap
    color: "transparent"

    WlrLayershell.namespace: "hyperlab-workspace-dock"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    // Only the dock takes input; the rest of the strip passes clicks on.
    mask: Region { item: dock }

    Dock {
        id: dock

        x: Math.round((bottom.width - width) / 2)
        y: bottom.height - height - bottom.theme.gap + 2
        theme: bottom.theme
        deskState: bottom.deskState
        surfaces: bottom.surfaces
    }
}
