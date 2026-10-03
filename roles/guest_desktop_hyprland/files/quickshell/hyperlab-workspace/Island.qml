// A floating island: the shell's one container. Glass surface, a hairline
// edge, a lit top edge and a soft shadow, entering from `enterFrom` once
// the shell has started.

import QtQuick

Item {
    id: island

    required property var theme
    property real padding: 10
    property real enterDelay: 0
    property point enterFrom: Qt.point(0, -12)
    property bool entered: false
    property alias surface: body
    // A clickable island reports clicks anywhere on its surface.
    property bool clickable: false

    signal clicked()

    // A highlight sweeps across the island once.
    function shine() {
        if (island.theme.normal > 0)
            sweep.restart();
    }
    default property alias content: holder.data

    implicitWidth: holder.childrenRect.width + padding * 2
    implicitHeight: theme.islandHeight

    opacity: entered ? 1 : 0
    transform: Translate {
        x: island.entered ? 0 : island.enterFrom.x
        y: island.entered ? 0 : island.enterFrom.y

        Behavior on x { NumberAnimation { duration: island.theme.slow; easing.type: Easing.OutCubic } }
        Behavior on y { NumberAnimation { duration: island.theme.slow; easing.type: Easing.OutCubic } }
    }

    Behavior on opacity { NumberAnimation { duration: island.theme.slow; easing.type: Easing.OutCubic } }

    Timer {
        interval: 80 + island.enterDelay
        running: !island.entered
        onTriggered: island.entered = true
    }

    // Shadow: three widening, fading rings beneath the surface.
    Repeater {
        model: 3

        Rectangle {
            required property int index

            anchors.fill: body
            anchors.margins: -(index + 1) * 3
            anchors.topMargin: -(index + 1) * 2
            anchors.bottomMargin: -(index + 1) * 4
            radius: body.radius + (index + 1) * 3
            color: "transparent"
            border.width: 3
            border.color: Qt.rgba(0, 0, 0, 0.16 - index * 0.045)
        }
    }

    Rectangle {
        id: body

        anchors.fill: parent
        radius: island.theme.radius
        color: island.theme.glass
        border.width: 1
        border.color: island.theme.line

        // The lit top edge.
        Rectangle {
            anchors.top: parent.top
            anchors.topMargin: 1
            anchors.horizontalCenter: parent.horizontalCenter
            width: parent.width - parent.radius * 2
            height: 1
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 0.5; color: Qt.rgba(1, 1, 1, 0.09) }
                GradientStop { position: 1; color: "transparent" }
            }
        }
    }

    Item {
        anchors.fill: body
        clip: true

        Rectangle {
            id: sheen

            width: body.width * 0.45
            height: body.height * 3
            y: -body.height
            x: -width
            rotation: 18
            opacity: 0.0
            gradient: Gradient {
                orientation: Gradient.Horizontal
                GradientStop { position: 0; color: "transparent" }
                GradientStop { position: 0.5; color: Qt.rgba(island.theme.accent.r, island.theme.accent.g, island.theme.accent.b, 0.28) }
                GradientStop { position: 1; color: "transparent" }
            }
        }

        SequentialAnimation {
            id: sweep

            PropertyAction { target: sheen; property: "opacity"; value: 1 }
            NumberAnimation {
                target: sheen; property: "x"; from: -sheen.width; to: body.width
                duration: island.theme.slow * 2.2; easing.type: Easing.InOutCubic
            }
            PropertyAction { target: sheen; property: "opacity"; value: 0 }
        }
    }

    onEnteredChanged: {
        if (entered)
            shineDelay.start();
    }

    Timer {
        id: shineDelay

        interval: island.theme.slow
        onTriggered: island.shine()
    }

    MouseArea {
        anchors.fill: body
        enabled: island.clickable
        cursorShape: island.clickable ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: island.clicked()
    }

    Item {
        id: holder

        x: island.padding
        anchors.verticalCenter: parent.verticalCenter
        width: childrenRect.width
        height: childrenRect.height
    }
}
