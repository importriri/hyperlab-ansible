// HyperLab focused-surface provenance badge (V447-C9.3).
//
// Provenance of the focused surface is a host resolution, not a guess made
// from a window name. Until a reviewed focused-provenance resolver publishes
// an identity, this badge reports that the resolution is unavailable and
// shows no identity at all.
//
// This is deliberately not the GPU boot claim: which identity may hold the
// GPU this boot and which identity owns the window in front of you are
// different questions with different answers, and collapsing them is how a
// trust display starts lying.

import QtQuick

ShellControl {
    id: badge

    required property var icons
    required property var provenance

    signal detailsRequested()

    readonly property bool resolved:
        badge.provenance && badge.provenance.available === true

    readonly property string identity:
        badge.resolved ? String(badge.provenance.identity) : ""

    flat: true

    accessibleName:
        badge.resolved
        ? "Focused surface provenance " + badge.theme.provenanceLabel(badge.identity)
        : "Focused surface provenance unavailable"

    content: [
        ProvenanceMarker {
            anchors.verticalCenter: parent.verticalCenter
            visible: badge.resolved
            tokens: badge.tokens
            theme: badge.theme
            identity: badge.identity
        },

        ShellLabel {
            anchors.verticalCenter: parent.verticalCenter
            tokens: badge.tokens
            role: "bar"
            font.weight: badge.resolved ? Font.Medium : Font.Normal
            text:
                badge.resolved
                ? badge.theme.provenanceLabel(badge.identity)
                : "Provenance unavailable"
            color:
                badge.resolved
                ? badge.theme.provenanceColor(badge.identity)
                : badge.theme.textQuiet
        }
    ]

    onActivated: badge.detailsRequested()
}
