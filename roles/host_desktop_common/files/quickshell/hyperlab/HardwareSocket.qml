// HyperLab hardware socket (V447-C9).
//
// The signature ownership indicator: a small rectangular socket at the
// lower-right of a machine enclosure. Outlined means passthrough is
// configured; filled means the host reports the GPU held by this machine;
// dashed means the relationship is unknown. A machine with no relationship
// shows no socket at all. The socket is a reading, never a control.

import QtQuick

Item {
    id: socket

    required property var tokens
    required property var theme

    // configured | held | unknown
    property string relation: "configured"

    implicitWidth: socket.tokens.socketWidth
    implicitHeight: socket.tokens.socketHeight

    Rectangle {
        anchors.fill: parent
        visible: socket.relation !== "unknown"
        radius: 2
        color: socket.relation === "held" ? socket.theme.textSecondary : "transparent"
        border.width: 1
        border.color: socket.relation === "held" ? socket.theme.textSecondary : socket.theme.boundaryStrong

        // Contact pins along the lower edge.
        Row {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom
            anchors.bottomMargin: 3
            spacing: 3

            Repeater {
                model: 4

                delegate: Rectangle {
                    width: 3
                    height: 4
                    radius: 0.5
                    color: socket.relation === "held" ? socket.theme.raised : socket.theme.boundaryStrong
                }
            }
        }
    }

    DashedFrame {
        anchors.fill: parent
        visible: socket.relation === "unknown"
        color: socket.theme.boundaryStrong
        thickness: 1
        dash: 3
        gap: 2
    }
}
