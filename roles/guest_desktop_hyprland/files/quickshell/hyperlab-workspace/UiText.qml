// Text in the shell's voice: IBM Plex, theme colours, no wrapping surprises.

import QtQuick

Text {
    required property var theme
    property bool mono: false

    color: theme.text
    font.family: mono ? theme.mono : theme.sans
    font.pixelSize: mono ? 12 : 14
    elide: Text.ElideRight
    verticalAlignment: Text.AlignVCenter
    textFormat: Text.PlainText
}
