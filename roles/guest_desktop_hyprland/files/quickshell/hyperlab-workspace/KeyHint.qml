// A key chord as the shell prints it: quiet, monospaced, never a button.

import QtQuick

Rectangle {
    id: hint

    required property var theme
    property string keys: ""

    implicitWidth: label.implicitWidth + 12
    implicitHeight: 20
    radius: 5
    color: "transparent"
    border.width: 1
    border.color: theme.line

    UiText {
        id: label

        anchors.centerIn: parent
        theme: hint.theme
        mono: true
        text: hint.keys
        color: hint.theme.textMuted
        font.pixelSize: 11
    }
}
