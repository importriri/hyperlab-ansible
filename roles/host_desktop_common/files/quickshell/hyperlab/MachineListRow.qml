// HyperLab machine list row (V447-C9.3).
//
// The dense alternative to the card grid, used when an inventory is large
// enough that a grid stops being readable. It carries the same facts in the
// same order — name, provenance, state, allocation, GPU relationship — so
// switching layout changes density and nothing else.

import QtQuick

Rectangle {
    id: row

    required property var tokens
    required property var theme
    required property var icons
    required property var machine

    property bool selected: false

    signal activated()

    readonly property string relation:
        String(row.machine.gpu_relation)

    readonly property string memoryText:
        typeof row.machine.memory_mb === "number"
        ? (row.machine.memory_mb >= 1024
            ? (row.machine.memory_mb / 1024).toFixed(
                row.machine.memory_mb % 1024 === 0 ? 0 : 1
              ) + " GiB"
            : row.machine.memory_mb + " MiB")
        : "Unknown"

    radius: row.tokens.radiusControl

    color:
        row.selected
        ? row.theme.fillSelected
        : (
            press.pressed
            ? row.theme.fillPressed
            : (hover.hovered ? row.theme.fillHover : "transparent")
        )

    border.width:
        row.activeFocus || row.selected ? row.tokens.focusOutline : 0
    border.color:
        row.activeFocus ? row.theme.focusRing : row.theme.boundaryStrong

    activeFocusOnTab: true

    Accessible.role: Accessible.Button
    Accessible.name:
        String(row.machine.name)
        + ", " + row.theme.provenanceLabel(row.machine.provenance)
        + ", " + row.icons.machineStateWord(row.machine.state)
    Accessible.onPressAction: row.activated()

    Behavior on color {
        ColorAnimation {
            duration: row.tokens.motionHover
        }
    }

    Row {
        anchors.left: parent.left
        anchors.right: gpuRelation.left
        anchors.leftMargin: row.tokens.spaceMd
        anchors.rightMargin: row.tokens.spaceMd
        anchors.verticalCenter: parent.verticalCenter
        spacing: row.tokens.spaceLg

        ProvenanceMarker {
            anchors.verticalCenter: parent.verticalCenter
            tokens: row.tokens
            theme: row.theme
            identity: String(row.machine.provenance)
        }

        ShellLabel {
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(120, row.width * 0.28)
            tokens: row.tokens
            role: "body"
            font.weight: Font.Medium
            text: String(row.machine.name)
            color: row.theme.textPrimary
        }

        // From the host's image manifest, never from the guest.
        ShellLabel {
            anchors.verticalCenter: parent.verticalCenter
            width: Math.max(90, row.width * 0.14)
            tokens: row.tokens
            role: "meta"
            text:
                typeof row.machine.os === "string" && row.machine.os.length > 0
                ? row.machine.os
                : "OS unknown"
            color: row.theme.textQuiet
        }

        StateChip {
            anchors.verticalCenter: parent.verticalCenter
            tokens: row.tokens
            theme: row.theme
            icons: row.icons
            state: String(row.machine.state)
        }

        ShellLabel {
            anchors.verticalCenter: parent.verticalCenter
            tokens: row.tokens
            role: "mono"
            text: row.memoryText
            color: row.theme.textSecondary
        }
    }

    ShellLabel {
        id: gpuRelation

        anchors.right: parent.right
        anchors.rightMargin: row.tokens.spaceMd
        anchors.verticalCenter: parent.verticalCenter
        tokens: row.tokens
        role: "meta"
        text:
            row.relation === "held"
            ? "Holds the GPU"
            : (row.relation === "unknown" ? "Passthrough unknown" : "")
        color: row.theme.textQuiet
    }

    HoverHandler {
        id: hover
        cursorShape: Qt.PointingHandCursor
    }

    TapHandler {
        id: press
        onTapped: row.activated()
    }

    Keys.onPressed: event => {
        if (
            event.key === Qt.Key_Return
            || event.key === Qt.Key_Enter
            || event.key === Qt.Key_Space
        ) {
            row.activated();
            event.accepted = true;
        }
    }
}
