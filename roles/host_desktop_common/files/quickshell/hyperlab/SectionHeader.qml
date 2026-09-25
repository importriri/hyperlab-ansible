// HyperLab section heading (V447-C9.3).
//
// One heading treatment for every grouped region: a tracked label, an
// optional plain-language description beneath it, and an optional trailing
// slot for a count or a control. Sections never restate the page title, so a
// view has exactly one heading and any number of sections.

import QtQuick

Item {
    id: header

    required property var tokens
    required property var theme

    property string label: ""
    property string description: ""
    property alias trailing: trailingRow.data

    implicitHeight: column.implicitHeight
    implicitWidth: column.implicitWidth + trailingRow.implicitWidth

    Column {
        id: column

        anchors.left: parent.left
        anchors.right: trailingRow.left
        anchors.rightMargin: header.tokens.spaceMd
        anchors.verticalCenter: parent.verticalCenter
        spacing: 2

        ShellLabel {
            width: parent.width
            tokens: header.tokens
            role: "label"
            text: header.label
            color: header.theme.textSecondary
            Accessible.role: Accessible.Heading
        }

        ShellLabel {
            width: parent.width
            visible: header.description.length > 0
            tokens: header.tokens
            role: "meta"
            wrapMode: Text.WordWrap
            text: header.description
            color: header.theme.textQuiet
        }
    }

    Row {
        id: trailingRow

        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        spacing: header.tokens.spaceSm
    }
}
