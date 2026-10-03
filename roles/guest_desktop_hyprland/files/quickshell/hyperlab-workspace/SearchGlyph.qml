// Magnifier glyph, drawn so the shell needs no icon font.

import QtQuick
import QtQuick.Shapes

Item {
    id: glyph

    required property var theme
    property real size: 16
    property color colour: theme.textSoft

    implicitWidth: size
    implicitHeight: size

    Rectangle {
        x: glyph.size * 0.12
        y: glyph.size * 0.12
        width: glyph.size * 0.6
        height: width
        radius: width / 2
        color: "transparent"
        border.width: 2
        border.color: glyph.colour
    }

    Shape {
        anchors.fill: parent
        preferredRendererType: Shape.CurveRenderer

        ShapePath {
            strokeColor: glyph.colour
            strokeWidth: 2
            capStyle: ShapePath.RoundCap
            startX: glyph.size * 0.64
            startY: glyph.size * 0.64
            PathLine { x: glyph.size * 0.9; y: glyph.size * 0.9 }
        }
    }
}
