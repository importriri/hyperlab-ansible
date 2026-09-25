// HyperLab provenance marker (V447-C9.3).
//
// The 8px mark that identifies provenance everywhere in the shell: a filled
// square in the fixed identity colour for a reviewed identity, and a neutral
// dashed outline for UNCLASSIFIED so it can never be mistaken for HOST or
// for any identity. Markers are shapes, not icons, and they never carry
// state.
//
// A marker is never presented alone: ProvenanceTag pairs it with its word,
// so provenance is legible without relying on colour vision.

import QtQuick

Item {
    id: marker

    required property var tokens
    required property var theme
    required property string identity

    readonly property bool known:
        marker.theme.knownProvenance(marker.identity)

    readonly property color tone:
        marker.known
        ? marker.theme.provenanceColor(marker.identity)
        : marker.theme.textSecondary

    implicitWidth: marker.tokens.markerSize
    implicitHeight: marker.tokens.markerSize

    Accessible.ignored: true

    Rectangle {
        anchors.fill: parent
        visible: marker.known
        radius: 1.5
        color: marker.tone
    }

    DashedFrame {
        anchors.fill: parent
        visible: !marker.known
        color: marker.tone
        thickness: 1
        dash: 2
        gap: 1
    }
}
