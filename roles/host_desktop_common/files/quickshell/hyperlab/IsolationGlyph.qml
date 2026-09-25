// HyperLab product symbol (V447-C9.3).
//
// One geometry family for the whole product: a split circular isolation
// boundary, a containment ring inside it, and a contained core at the
// centre. The split is the point — an isolation boundary that can be opened
// and closed is what HyperLab exists to operate.
//
// The mark is monochrome and carries no provenance, no state and no trust
// claim, so it is drawn from one stroke colour and one core colour and never
// from an identity palette. It survives from 16 units in the rail to a
// wallpaper-scale relief because every measurement is a fraction of `size`.

import QtQuick
import QtQuick.Shapes

Item {
    id: glyph

    property int size: 18
    property color stroke: "white"
    property color core: glyph.stroke
    property real strokeScale: 1.0

    // Degrees of the outer boundary removed at each side to form the split.
    readonly property real splitAngle: 16

    readonly property real strokeWidth:
        Math.max(1, glyph.size / 11) * glyph.strokeScale

    implicitWidth: glyph.size
    implicitHeight: glyph.size

    width: glyph.size
    height: glyph.size

    Accessible.ignored: true

    Shape {
        anchors.fill: parent
        antialiasing: true

        // Outer isolation boundary, upper arc.
        ShapePath {
            strokeColor: glyph.stroke
            strokeWidth: glyph.strokeWidth
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap

            PathAngleArc {
                centerX: glyph.size / 2
                centerY: glyph.size / 2
                radiusX: glyph.size / 2 - glyph.strokeWidth
                radiusY: glyph.size / 2 - glyph.strokeWidth
                startAngle: 180 + glyph.splitAngle
                sweepAngle: 180 - glyph.splitAngle * 2
            }
        }

        // Outer isolation boundary, lower arc.
        ShapePath {
            strokeColor: glyph.stroke
            strokeWidth: glyph.strokeWidth
            fillColor: "transparent"
            capStyle: ShapePath.RoundCap

            PathAngleArc {
                centerX: glyph.size / 2
                centerY: glyph.size / 2
                radiusX: glyph.size / 2 - glyph.strokeWidth
                radiusY: glyph.size / 2 - glyph.strokeWidth
                startAngle: glyph.splitAngle
                sweepAngle: 180 - glyph.splitAngle * 2
            }
        }

        // Containment ring: the closed boundary the core actually sits in.
        ShapePath {
            strokeColor: glyph.stroke
            strokeWidth: Math.max(1, glyph.strokeWidth * 0.7)
            fillColor: "transparent"

            PathAngleArc {
                centerX: glyph.size / 2
                centerY: glyph.size / 2
                radiusX: glyph.size * 0.29
                radiusY: glyph.size * 0.29
                startAngle: 0
                sweepAngle: 360
            }
        }
    }

    // Contained core.
    Rectangle {
        anchors.centerIn: parent
        width: Math.max(2, Math.round(glyph.size * 0.16))
        height: width
        radius: width / 2
        color: glyph.core
        antialiasing: true
    }
}
