// A small bar trace of recent samples (0-100), newest on the right.

import QtQuick

Row {
    id: spark

    required property var theme
    property var samples: []
    property int bars: 24
    property real barHeight: 16

    spacing: 1
    height: barHeight

    Repeater {
        model: spark.bars

        Rectangle {
            required property int index

            readonly property int offset: spark.bars - spark.samples.length
            readonly property real sample:
                index >= offset ? spark.samples[index - offset] : 0

            anchors.bottom: parent.bottom
            width: 2
            radius: 1
            height: Math.max(2, spark.barHeight * sample / 100)
            color: spark.theme.accent
            opacity: index >= offset ? 0.35 + 0.65 * (index - offset + 1) / Math.max(1, spark.samples.length) : 0.12

            Behavior on height { NumberAnimation { duration: spark.theme.normal; easing.type: Easing.OutCubic } }
        }
    }
}
