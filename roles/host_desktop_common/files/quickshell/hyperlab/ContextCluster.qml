// HyperLab session context (V447-C9.3).
//
// The rail centre answers two questions: what time is it, and what am I
// looking at. The clock is geometrically centred while there is room for it;
// the context sits to its left and elides before anything else moves.
//
// Context is the compositor's own name for the focused host surface. It is
// host metadata about a host process and it is presented as such: it is
// never a provenance claim, and it is never the GPU trust tooltip wearing a
// different label.

import QtQuick

Item {
    id: cluster

    required property var tokens
    required property var theme
    required property string context
    required property var clock

    // Display centre in parent coordinates and the room to the left of the
    // clock that the context label may use.
    property real centerX: 0
    property int maximumContextWidth: 360
    property bool dateVisible: true

    // Below this the centred clock cannot hold its place without colliding
    // with the side regions, so the rail stops pretending and left-aligns it
    // against the reserved centre.
    property bool centeredClock: true

    // Keep the compositor's raw focused-surface identity in ShellState and
    // Diagnostics, but do not expose Quickshell's implementation app-id as
    // product-facing session context.
    readonly property string presentedContext:
        cluster.context === "org.quickshell" ? "" : cluster.context

    readonly property bool contextVisible:
        cluster.presentedContext.length > 0
        && cluster.maximumContextWidth > 80

    implicitHeight: cluster.tokens.controlHeight
    width: parent ? parent.width : 0

    Row {
        id: clockRow

        x:
            cluster.centeredClock
            ? Math.round(cluster.centerX - width / 2)
            : Math.round(cluster.centerX - width / 2)
        anchors.verticalCenter: parent.verticalCenter
        spacing: cluster.tokens.spaceSm

        Accessible.role: Accessible.StaticText
        Accessible.name:
            Qt.formatDateTime(cluster.clock.date, "HH:mm dddd d MMMM")

        ShellLabel {
            id: centeredClock

            anchors.verticalCenter: parent.verticalCenter
            tokens: cluster.tokens
            role: "bar"
            font.weight: Font.DemiBold

            text: Qt.formatDateTime(
                cluster.clock.date,
                "HH:mm"
            )

            color: cluster.theme.textPrimary
        }

        ShellLabel {
            anchors.verticalCenter: parent.verticalCenter
            visible: cluster.dateVisible
            tokens: cluster.tokens
            role: "bar"
            font.weight: Font.Normal

            text: Qt.formatDateTime(
                cluster.clock.date,
                "ddd d MMM"
            )

            color: cluster.theme.textSecondary
        }
    }

    Row {
        anchors.right: clockRow.left
        anchors.rightMargin: cluster.tokens.spaceMd
        anchors.verticalCenter: parent.verticalCenter
        spacing: cluster.tokens.spaceMd
        visible: cluster.contextVisible

        ShellLabel {
            anchors.verticalCenter: parent.verticalCenter
            tokens: cluster.tokens
            role: "bar"
            font.weight: Font.Normal

            width:
                Math.min(
                    implicitWidth,
                    cluster.maximumContextWidth
                )

            text: cluster.presentedContext
            color: cluster.theme.textSecondary

            Accessible.role: Accessible.StaticText
            Accessible.name:
                "Focused surface " + cluster.presentedContext
        }

        ShellDivider {
            anchors.verticalCenter: parent.verticalCenter
            tokens: cluster.tokens
            theme: cluster.theme
        }
    }
}
