// HyperLab dashed frame (V447-C9).
//
// A dashed rectangular outline built from plain rectangles, so it clips and
// scrolls like every other item on every renderer. Used for the
// UNCLASSIFIED provenance marker and the unknown hardware socket.

import QtQuick

Item {
    id: frame

    property color color: "white"
    property real thickness: 1
    property int dash: 3
    property int gap: 2

    readonly property int horizontalCount: Math.max(1, Math.floor((width + gap) / (dash + gap)))
    readonly property int verticalCount: Math.max(1, Math.floor((height + gap) / (dash + gap)))

    Row {
        anchors.left: parent.left
        anchors.top: parent.top
        spacing: frame.gap

        Repeater {
            model: frame.horizontalCount
            delegate: Rectangle { width: frame.dash; height: frame.thickness; color: frame.color }
        }
    }

    Row {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        spacing: frame.gap

        Repeater {
            model: frame.horizontalCount
            delegate: Rectangle { width: frame.dash; height: frame.thickness; color: frame.color }
        }
    }

    Column {
        anchors.left: parent.left
        anchors.top: parent.top
        spacing: frame.gap

        Repeater {
            model: frame.verticalCount
            delegate: Rectangle { width: frame.thickness; height: frame.dash; color: frame.color }
        }
    }

    Column {
        anchors.right: parent.right
        anchors.top: parent.top
        spacing: frame.gap

        Repeater {
            model: frame.verticalCount
            delegate: Rectangle { width: frame.thickness; height: frame.dash; color: frame.color }
        }
    }
}
