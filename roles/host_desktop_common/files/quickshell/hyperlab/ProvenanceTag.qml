// HyperLab provenance tag (V447-C9.3).
//
// The marker and its word always travel together, so provenance is never
// colour alone. HOST is neutral control plane, UNCLASSIFIED is the explicit
// absence of an identity, and any identity outside the reviewed set reads as
// Unknown rather than borrowing a colour it has not earned.

import QtQuick

Row {
    id: tag

    required property var tokens
    required property var theme
    required property string identity

    property bool labelled: true
    property string role: "label"

    readonly property string word:
        tag.theme.provenanceLabel(tag.identity)

    readonly property bool known:
        tag.theme.knownProvenance(tag.identity)

    spacing: tag.tokens.spaceSm

    Accessible.role: Accessible.StaticText
    Accessible.name: "Provenance " + tag.word

    ProvenanceMarker {
        anchors.verticalCenter: parent.verticalCenter
        tokens: tag.tokens
        theme: tag.theme
        identity: tag.identity
    }

    ShellLabel {
        anchors.verticalCenter: parent.verticalCenter
        visible: tag.labelled
        tokens: tag.tokens
        role: tag.role
        text: tag.word
        color:
            tag.known
            ? tag.theme.provenanceColor(tag.identity)
            : tag.theme.textSecondary
    }
}
