import Quickshell
import QtQuick
import QtQuick.Layouts

PanelWindow {
    id: root

    property var modelData

    screen: modelData

    anchors {
        top: true
        left: true
        right: true
    }

    implicitHeight: 37
    exclusiveZone: 37

    // Phase 2A is intentionally non-interactive. HyperLab does not ship fake
    // controls while the existing Waybar/GTK surfaces remain authoritative.
    color: "#0b0f14"

    Rectangle {
        anchors.fill: parent
        color: "#0b0f14"

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: "#25303a"
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            spacing: 10

            Text {
                text: "HYPERLAB"
                color: "#e6edf3"
                font.pixelSize: 13
                font.bold: true
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 16
                color: "#35404a"
            }

            Text {
                text: "shared shell · staged"
                color: "#8b949e"
                font.pixelSize: 11
            }

            Item {
                Layout.fillWidth: true
            }

            Text {
                text: "Hyprland · Sway"
                color: "#8b949e"
                font.pixelSize: 11
            }
        }
    }
}
