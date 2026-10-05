// HyperLab fullscreen frame (ADR 0039).
//
// A fullscreen window covers the rail and loses its border, so nothing
// host-drawn would contradict whatever it shows, including a fake host
// desktop. While the focused window is fullscreen and the host has not
// resolved it as its own, this ring is drawn around its output on the
// overlay layer, above every window, in the provenance colour the host
// resolved; an unresolved surface gets the warning colour. It takes no input
// and reserves no space. The guest never draws or controls it.

import Quickshell
import Quickshell.Wayland
import QtQuick

PanelWindow {
    id: frame

    required property var tokens
    required property var theme
    required property var shellState

    property var modelData

    screen: modelData

    readonly property var state: frame.shellState.fullscreenFrame
    readonly property string output: frame.screen ? String(frame.screen.name) : ""
    // The focused window's output when known; every output otherwise.
    readonly property bool here:
        frame.shellState.focusedOutput.length === 0
        || frame.shellState.focusedOutput === frame.output

    visible: frame.state.visible && frame.here

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }

    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "hyperlab-fullscreen-frame"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    // No input region: the ring is seen, never clicked.
    mask: Region {}

    Rectangle {
        objectName: "fullscreen-frame-ring"
        anchors.fill: parent
        color: "transparent"
        border.width: frame.tokens.fullscreenRing
        border.color: frame.state.resolved
            ? frame.theme.provenanceColor(frame.state.identity)
            : frame.theme.semanticStatusColor("warn")
    }
}
