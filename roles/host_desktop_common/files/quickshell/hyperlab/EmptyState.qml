// HyperLab empty, unavailable and loading state (V447-C9.3).
//
// A region with nothing in it must say which nothing it is. An empty
// inventory, an inventory that could not be read, a filter that matched
// nothing and a first observation that has not arrived are four different
// facts, and collapsing them is how a failure starts looking healthy.
//
//   empty        the host answered and there is nothing
//   filtered     the host answered and the current filter hides everything
//   loading      no observation has arrived yet
//   unavailable  the source did not answer
//
// Only `unavailable` carries a status tone; the rest stay quiet.

import QtQuick

Item {
    id: empty

    required property var tokens
    required property var theme

    // empty | filtered | loading | unavailable
    property string kind: "empty"
    property string title: ""
    property string description: ""

    readonly property bool unavailable: empty.kind === "unavailable"

    implicitHeight: column.implicitHeight + empty.tokens.spaceXl * 2
    implicitWidth: column.implicitWidth

    Accessible.role: Accessible.StaticText
    Accessible.name: empty.title + ". " + empty.description

    Column {
        id: column

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: empty.tokens.spaceSm

        ShellLabel {
            width: parent.width
            tokens: empty.tokens
            role: "section"
            text: empty.title
            color:
                empty.unavailable
                ? empty.theme.semanticStatusColor("warn")
                : empty.theme.textPrimary
        }

        ShellLabel {
            width: parent.width
            visible: empty.description.length > 0
            tokens: empty.tokens
            role: "body"
            wrapMode: Text.WordWrap
            text: empty.description
            color: empty.theme.textSecondary
        }
    }
}
