// HyperLab policy cell (V447-C9).
//
// One rung of the GPU handoff ladder: its provenance marker, its name and
// its rung number. Four equal cells form a policy diagram, not a slider;
// the cell carrying the host's boot claim is bracketed and labelled, and no
// cell ever implies that it is currently selectable.

import QtQuick

Item {
    id: cell

    required property var tokens
    required property var theme
    required property string identity
    required property int rung

    property bool claimed: false
    property bool compact: false
    property bool countKnown: true
    property int machineCount: 0

    readonly property color tone: cell.theme.provenanceColor(cell.identity)

    Accessible.role: Accessible.StaticText
    Accessible.name:
        cell.theme.provenanceLabel(cell.identity) + " rung " + cell.rung

    implicitHeight: body.height + bracket.height + cell.tokens.spaceXs

    // Boot claim bracket.
    Item {
        id: bracket

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        height: cell.tokens.fontLabel + 8
        visible: cell.claimed

        ShellLabel {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.top: parent.top
            tokens: cell.tokens
            role: "label"
            text: "Boot claim"
            color: cell.theme.textSecondary
        }

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: cell.theme.boundaryStrong
        }

        Rectangle { anchors.left: parent.left; anchors.bottom: parent.bottom; width: 1; height: 4; color: cell.theme.boundaryStrong }
        Rectangle { anchors.right: parent.right; anchors.bottom: parent.bottom; width: 1; height: 4; color: cell.theme.boundaryStrong }
    }

    Rectangle {
        id: body

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: bracket.visible ? bracket.bottom : parent.top
        anchors.topMargin: bracket.visible ? cell.tokens.spaceXs : bracket.height + cell.tokens.spaceXs
        height:
            cell.compact
            ? cell.tokens.policyCellHeightCompact
            : cell.tokens.policyCellHeight
        radius: cell.tokens.radiusCard
        color: cell.theme.raised
        border.width: cell.claimed ? 2 : 1
        border.color: cell.claimed ? cell.theme.boundaryStrong : cell.theme.boundary

        Column {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.margins: cell.tokens.spaceSm
            spacing: 1

            Row {
                spacing: cell.tokens.spaceXs + 2

                ProvenanceMarker {
                    anchors.verticalCenter: parent.verticalCenter
                    tokens: cell.tokens
                    theme: cell.theme
                    identity: cell.identity
                }

                ShellLabel {
                    anchors.verticalCenter: parent.verticalCenter
                    tokens: cell.tokens
                    role: "label"
                    text: cell.theme.provenanceLabel(cell.identity)
                    color: cell.tone
                }
            }

            Row {
                spacing: cell.tokens.spaceXs

                ShellLabel {
                    anchors.baseline: rungLabel.baseline
                    tokens: cell.tokens
                    role: "meta"
                    text: "rung"
                    color: cell.theme.textQuiet
                }

                ShellLabel {
                    id: rungLabel
                    tokens: cell.tokens
                    role: "value"
                    text: String(cell.rung)
                    color: cell.theme.textPrimary
                }

            }

            // A count is only shown when the inventory is actually known.
            // "no machines" is a fact, not a default.
            ShellLabel {
                visible: !cell.compact
                tokens: cell.tokens
                role: "meta"
                text: {
                    if (!cell.countKnown)
                        return "count unknown";

                    return cell.machineCount > 0
                        ? cell.machineCount
                            + (cell.machineCount === 1 ? " machine" : " machines")
                        : "no machines";
                }
                color: cell.countKnown && cell.machineCount > 0
                    ? cell.theme.textSecondary
                    : cell.theme.textQuiet
            }
        }
    }
}
