// HyperLab product identity (V447-C9.3).
//
// The mark is the product symbol: a split circular isolation boundary
// containing a core. Beside it sits the wordmark, and where there is room,
// the "Platform" subtitle. One geometry family carries the identity from the
// 18-unit rail mark to the wallpaper relief, so the product is recognisable
// at every size without a second logo.
//
// The mark is the product entry point. An ordinary click opens the command
// surface; the alternate buttons are documented shortcuts to Diagnostics and
// the Control Center, never the only way to reach them. Presentation only:
// it emits intent and never runs anything.

import QtQuick

Item {
    id: identity

    required property var tokens
    required property var theme

    property bool wordmarkVisible: true
    property bool subtitleVisible: false

    signal launcherRequested()
    signal diagnosticsRequested()
    signal controlCenterRequested()

    implicitWidth: row.implicitWidth + identity.tokens.spaceSm * 2
    implicitHeight: identity.tokens.controlHeight

    activeFocusOnTab: true

    Accessible.role: Accessible.Button
    Accessible.name: "HyperLab Platform"
    Accessible.description: "Open the HyperLab command surface"
    Accessible.onPressAction: identity.launcherRequested()

    Rectangle {
        anchors.fill: parent
        radius: identity.tokens.radiusControl
        color: hover.hovered ? identity.theme.fillHover : "transparent"
        border.width:
            identity.activeFocus ? identity.tokens.focusOutline : 0
        border.color: identity.theme.focusRing

        Behavior on color {
            ColorAnimation {
                duration: identity.tokens.motionHover
            }
        }
    }

    Row {
        id: row

        anchors.centerIn: parent
        spacing: identity.tokens.spaceSm

        IsolationGlyph {
            anchors.verticalCenter: parent.verticalCenter
            size: identity.tokens.brandMark
            stroke: identity.theme.textPrimary
            core: identity.theme.textPrimary
        }

        Column {
            anchors.verticalCenter: parent.verticalCenter
            visible: identity.wordmarkVisible
            spacing: 0

            ShellLabel {
                tokens: identity.tokens
                role: "bar"
                font.weight: Font.DemiBold
                text: "HyperLab"
                color: identity.theme.textPrimary
            }

            ShellLabel {
                visible: identity.subtitleVisible
                tokens: identity.tokens
                role: "label"
                font.pixelSize: identity.tokens.fontLabel - 2
                text: "Platform"
                color: identity.theme.textQuiet
            }
        }
    }

    HoverHandler {
        id: hover
        cursorShape: Qt.PointingHandCursor
    }

    TapHandler {
        acceptedButtons:
            Qt.LeftButton
            | Qt.RightButton
            | Qt.MiddleButton

        onTapped: (eventPoint, button) => {
            if (button === Qt.RightButton) {
                identity.diagnosticsRequested();
            } else if (button === Qt.MiddleButton) {
                identity.controlCenterRequested();
            } else {
                identity.launcherRequested();
            }
        }
    }

    Keys.onPressed: event => {
        if (
            event.key === Qt.Key_Return
            || event.key === Qt.Key_Enter
            || event.key === Qt.Key_Space
        ) {
            identity.launcherRequested();
            event.accepted = true;
        }
    }
}
