// HyperLab product symbol, geometry B (ADR 0056).
// Two filled annulus segments with vertical cuts, a containment ring and a
// contained core. The gaps are above and below the core. Below 33 units the
// ring is omitted and the core enlarged to keep the mark legible.
// Monochrome presentation only: the mark carries no state or trust claim.

import QtQuick
import QtQuick.Shapes

Item {
    id: glyph

    property int size: 18
    property color stroke: "white"
    property color core: glyph.stroke
    property real strokeScale: 1.0

    readonly property real radiusRatio: 0.46
    readonly property real arcInnerRatio: 0.685
    readonly property real cutRatio: 0.41
    readonly property real ringRadiusRatio: 0.555
    readonly property real ringStrokeRatio: 0.057
    readonly property real coreRadiusRatio: 0.413
    readonly property real smallCoreRadiusRatio: 0.435
    readonly property int smallThreshold: 33

    readonly property bool small: glyph.size < glyph.smallThreshold
    readonly property real outerRadius: glyph.size * glyph.radiusRatio
    readonly property real cutOffset: glyph.outerRadius * glyph.cutRatio
    // Scale the filled boundary's thickness inward, keeping its outside and
    // vertical cuts fixed. At extreme widths the inner arc meets the cut.
    readonly property real innerRadius: Math.max(glyph.cutOffset,
        glyph.outerRadius * (1 - (1 - glyph.arcInnerRatio) * glyph.strokeScale))
    readonly property real outerY: Math.sqrt(
        glyph.outerRadius * glyph.outerRadius - glyph.cutOffset * glyph.cutOffset)
    readonly property real innerY: Math.sqrt(
        glyph.innerRadius * glyph.innerRadius - glyph.cutOffset * glyph.cutOffset)
    readonly property real strokeWidth:
        Math.max(1, glyph.outerRadius * glyph.ringStrokeRatio * glyph.strokeScale)
    readonly property real coreRadius: glyph.outerRadius
        * (glyph.small ? glyph.smallCoreRadiusRatio : glyph.coreRadiusRatio)

    implicitWidth: glyph.size
    implicitHeight: glyph.size
    width: glyph.size
    height: glyph.size
    Accessible.ignored: true

    Shape {
        anchors.fill: parent
        antialiasing: true

        // Left boundary: circular outside and inside, joined vertically.
        ShapePath {
            strokeColor: "transparent"
            strokeWidth: -1
            fillColor: glyph.stroke
            startX: glyph.size / 2 - glyph.cutOffset
            startY: glyph.size / 2 - glyph.outerY

            PathArc {
                x: glyph.size / 2 - glyph.cutOffset
                y: glyph.size / 2 + glyph.outerY
                radiusX: glyph.outerRadius
                radiusY: glyph.outerRadius
                direction: PathArc.Counterclockwise
            }
            PathLine {
                x: glyph.size / 2 - glyph.cutOffset
                y: glyph.size / 2 + glyph.innerY
            }
            PathArc {
                x: glyph.size / 2 - glyph.cutOffset
                y: glyph.size / 2 - glyph.innerY
                radiusX: glyph.innerRadius
                radiusY: glyph.innerRadius
                direction: PathArc.Clockwise
            }
            PathLine {
                x: glyph.size / 2 - glyph.cutOffset
                y: glyph.size / 2 - glyph.outerY
            }
        }

        // Right boundary, mirrored around the centre.
        ShapePath {
            strokeColor: "transparent"
            strokeWidth: -1
            fillColor: glyph.stroke
            startX: glyph.size / 2 + glyph.cutOffset
            startY: glyph.size / 2 - glyph.outerY

            PathArc {
                x: glyph.size / 2 + glyph.cutOffset
                y: glyph.size / 2 + glyph.outerY
                radiusX: glyph.outerRadius
                radiusY: glyph.outerRadius
                direction: PathArc.Clockwise
            }
            PathLine {
                x: glyph.size / 2 + glyph.cutOffset
                y: glyph.size / 2 + glyph.innerY
            }
            PathArc {
                x: glyph.size / 2 + glyph.cutOffset
                y: glyph.size / 2 - glyph.innerY
                radiusX: glyph.innerRadius
                radiusY: glyph.innerRadius
                direction: PathArc.Counterclockwise
            }
            PathLine {
                x: glyph.size / 2 + glyph.cutOffset
                y: glyph.size / 2 - glyph.outerY
            }
        }

        // Containment ring, omitted in the small variant.
        ShapePath {
            strokeColor: glyph.small ? "transparent" : glyph.stroke
            strokeWidth: glyph.strokeWidth
            fillColor: "transparent"

            PathAngleArc {
                centerX: glyph.size / 2
                centerY: glyph.size / 2
                radiusX: glyph.outerRadius * glyph.ringRadiusRatio
                radiusY: glyph.outerRadius * glyph.ringRadiusRatio
                startAngle: 0
                sweepAngle: 360
            }
        }

        // Contained core.
        ShapePath {
            strokeColor: "transparent"
            strokeWidth: -1
            fillColor: glyph.core

            PathAngleArc {
                centerX: glyph.size / 2
                centerY: glyph.size / 2
                radiusX: glyph.coreRadius
                radiusY: glyph.coreRadius
                startAngle: 0
                sweepAngle: 360
            }
        }
    }
}
