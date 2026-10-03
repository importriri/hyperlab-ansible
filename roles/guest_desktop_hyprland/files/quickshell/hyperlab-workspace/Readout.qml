// One status readout: a quiet label and its value.

import QtQuick

Row {
    id: readout

    required property var theme
    property string label: ""
    property string value: ""
    property color valueColor: theme.textSoft

    spacing: 6

    UiText {
        anchors.verticalCenter: parent.verticalCenter
        theme: readout.theme
        mono: true
        text: readout.label
        color: readout.theme.textMuted
        font.pixelSize: 11
        font.letterSpacing: 1.2
    }

    UiText {
        anchors.verticalCenter: parent.verticalCenter
        theme: readout.theme
        mono: true
        text: readout.value
        color: readout.valueColor
        font.pixelSize: 13
    }
}
