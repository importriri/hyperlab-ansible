// Where am I: the workstation mark, then Desk / Project. Clicking it opens
// the Desks overview.

import QtQuick

Island {
    id: context

    required property var deskState
    required property var surfaces

    padding: 12
    enterFrom: Qt.point(-18, 0)

    readonly property var place: deskState.place

    Connections {
        target: context.deskState
        function onDeskEntered(desk) { mark.pulse(); }
    }

    clickable: true
    onClicked: context.surfaces.toggleOverview()

    Row {
        spacing: 10

        Mark {
            id: mark

            anchors.verticalCenter: parent.verticalCenter
            theme: context.theme
        }

        UiText {
            anchors.verticalCenter: parent.verticalCenter
            theme: context.theme
            mono: true
            text: "WORKSTATION"
            color: context.theme.textMuted
            font.letterSpacing: 1.7
        }

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: 1
            height: 18
            color: context.theme.lineStrong
        }

        SwapText {
            anchors.verticalCenter: parent.verticalCenter
            theme: context.theme
            value: context.place.deskName || "Workstation"
            font.weight: Font.DemiBold
        }

        UiText {
            anchors.verticalCenter: parent.verticalCenter
            theme: context.theme
            text: "/"
            color: context.theme.textMuted
        }

        SwapText {
            anchors.verticalCenter: parent.verticalCenter
            theme: context.theme
            value: context.place.label
            color: context.theme.textSoft
            width: Math.min(implicitWidth, 280)
        }
    }
}
