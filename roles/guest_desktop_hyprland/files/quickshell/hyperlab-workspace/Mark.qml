// The workstation mark: a diamond holding a core. It pulses once when the
// Desk changes, the only motion the identity ever makes.

import QtQuick
import QtQuick.Shapes

Item {
    id: mark

    required property var theme
    property real size: 22

    implicitWidth: size
    implicitHeight: size

    function pulse() {
        if (mark.theme.normal > 0)
            pulseAnimation.restart();
    }

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: mark.theme.accent
            strokeWidth: 1.6
            fillColor: "transparent"
            joinStyle: ShapePath.RoundJoin

            startX: mark.size / 2
            startY: mark.size * 0.125
            PathLine { x: mark.size * 0.875; y: mark.size / 2 }
            PathLine { x: mark.size / 2; y: mark.size * 0.875 }
            PathLine { x: mark.size * 0.125; y: mark.size / 2 }
            PathLine { x: mark.size / 2; y: mark.size * 0.125 }
        }
    }

    Rectangle {
        id: core

        anchors.centerIn: parent
        width: mark.size * 0.27
        height: width
        radius: width / 2
        color: "transparent"
        border.width: 1.6
        border.color: mark.theme.accent
    }

    Rectangle {
        id: halo

        anchors.centerIn: parent
        width: core.width
        height: width
        radius: width / 2
        color: "transparent"
        border.width: 1
        border.color: mark.theme.accent
        opacity: 0
    }

    ParallelAnimation {
        id: pulseAnimation

        NumberAnimation {
            target: halo; property: "width"
            from: core.width; to: mark.size * 1.4
            duration: mark.theme.slow * 1.6; easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: halo; property: "opacity"
            from: 0.9; to: 0
            duration: mark.theme.slow * 1.6; easing.type: Easing.OutCubic
        }
        SequentialAnimation {
            NumberAnimation {
                target: core; property: "scale"; to: 1.35
                duration: mark.theme.fast; easing.type: Easing.OutCubic
            }
            NumberAnimation {
                target: core; property: "scale"; to: 1
                duration: mark.theme.normal; easing.type: Easing.OutBack
            }
        }
    }
}
