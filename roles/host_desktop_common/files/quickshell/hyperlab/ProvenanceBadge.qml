// HyperLab focused-surface provenance badge (V447-C9.3).
//
// Provenance of the focused surface is a host resolution, not a guess made
// from a window name. The badge shows an identity only when the reviewed
// resolver named one for the focused surface. A surface the resolver refused
// to name reads "Unresolved" in the warning tone; every other state is quiet
// text with no identity at all.
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

    // Fail closed, and visibly so: a managed-looking surface without valid
    // host provenance is a finding, not an absence.
    readonly property bool unresolved:
        badge.provenance && badge.provenance.state === "unresolved"

    readonly property string statusText:
        badge.provenance && typeof badge.provenance.label === "string"
        && badge.provenance.label.length > 0
        ? badge.provenance.label
        : "Unavailable"

    flat: true

    accessibleName:
        badge.resolved
        ? "Focused surface provenance " + badge.theme.provenanceLabel(badge.identity)
        : "Focused surface provenance " + badge.statusText.toLowerCase()

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
                : (badge.unresolved
                    ? "Unresolved"
                    : "Provenance " + badge.statusText.toLowerCase())
            color:
                badge.resolved
                ? badge.theme.provenanceColor(badge.identity)
                : (badge.unresolved
                    ? badge.theme.semanticStatusColor("warning")
                    : badge.theme.textQuiet)
        }
    ]

    onActivated: badge.detailsRequested()
}
