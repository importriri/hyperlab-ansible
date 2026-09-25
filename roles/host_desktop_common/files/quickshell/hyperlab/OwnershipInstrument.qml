// HyperLab isolation and GPU instrument (V447-C9.3).
//
// A bounded reading of ownership with four unmistakably distinct regions:
// the HOST control plane, the GPU facts (current owner, boot claim,
// observation), the four-rung handoff policy CLEAN 3 · DEV 2 · DIRTY 1 ·
// LAB 0, and SERVICES in its own compartment because it sits outside the
// GPU ladder entirely. HOST is never a rung; SERVICES has no connector.
//
// Each field is populated only from its own authoritative bridge field. A
// retained boot claim is not a current attachment; an unknown owner says
// unknown; and "nobody holds it" is a different sentence from "the host
// could not tell us". Colour identifies provenance; it grants no
// permissions, and the instrument is a reading, never an actuator.

import QtQuick

Column {
    id: instrument

    required property var tokens
    required property var theme
    required property var icons
    required property var shellState

    property bool horizontal: false

    readonly property var claim: instrument.shellState.trustClaim

    // Only a current, valid observation may say "No claim this boot". Any
    // other state names itself and, if a claim was seen before, keeps it
    // visible with that qualifier rather than dropping the restriction.
    readonly property string claimState: instrument.shellState.trustClaimState
    readonly property bool claimCurrent: instrument.claimState === "ok"
    readonly property bool claimRetained:
        !instrument.claimCurrent && instrument.claim.claimed === true

    readonly property string claimQualifier: {
        switch (instrument.claimState) {
        case "loading":
            return "Not yet observed";
        case "stale":
            return "Stale reading";
        default:
            return "Claim source unavailable";
        }
    }
    readonly property var ownership: instrument.shellState.gpuOwnership

    readonly property bool inventoryKnown:
        instrument.shellState.machinesAvailable

    readonly property var rungs: [
        { identity: "clean", rung: 3 },
        { identity: "dev", rung: 2 },
        { identity: "dirty", rung: 1 },
        { identity: "lab", rung: 0 }
    ]

    readonly property bool ownerKnown: instrument.ownership.known === true

    readonly property bool ownerHeld:
        instrument.ownerKnown
        && String(instrument.ownership.owner).length > 0

    readonly property string ownerText:
        instrument.ownerKnown
        ? (instrument.ownerHeld
            ? String(instrument.ownership.owner)
            : "No current owner")
        : "Unknown"

    readonly property string observedText:
        instrument.shellState.observedText(
            instrument.shellState.gpuObservedAt
        )

    // The ladder brackets a rung only for a current observation; a retained
    // claim is carried by the qualified Boot claim row instead.
    function heldBy(identity) {
        return instrument.claimCurrent
            && instrument.claim.claimed === true
            && instrument.claim.identity === identity;
    }

    spacing: instrument.tokens.spaceMd

    // A. HOST control plane.
    Column {
        width: parent.width
        spacing: instrument.tokens.spaceSm

        Row {
            width: parent.width
            spacing: instrument.tokens.spaceSm

            ProvenanceTag {
                anchors.verticalCenter: parent.verticalCenter
                tokens: instrument.tokens
                theme: instrument.theme
                identity: "host"
            }

            ShellLabel {
                anchors.verticalCenter: parent.verticalCenter
                tokens: instrument.tokens
                role: "meta"
                text: "Control plane · above the ladder, never a rung"
                color: instrument.theme.textPrimary
            }
        }
    }

    ShellDivider {
        width: parent.width
        vertical: false
        tokens: instrument.tokens
        theme: instrument.theme
    }

    // B. GPU facts, each from its own field.
    Grid {
        id: facts

        width: parent.width
        columns: instrument.horizontal ? 2 : 2
        columnSpacing: instrument.tokens.spaceMd
        rowSpacing: instrument.tokens.spaceXs
        verticalItemAlignment: Grid.AlignVCenter

        ShellLabel {
            tokens: instrument.tokens
            role: "meta"
            text: "Current owner"
            color: instrument.theme.textQuiet
            width: 118
        }

        ShellLabel {
            tokens: instrument.tokens
            role: "mono"
            text: instrument.ownerText
            color:
                instrument.ownerKnown
                ? instrument.theme.textPrimary
                : instrument.theme.semanticStatusColor("warn")
            width: Math.max(0, facts.width - 118 - facts.columnSpacing)
        }

        ShellLabel {
            tokens: instrument.tokens
            role: "meta"
            text: "Boot claim"
            color: instrument.theme.textQuiet
            width: 118
        }

        Row {
            id: claimRow

            width: Math.max(0, facts.width - 118 - facts.columnSpacing)
            spacing: instrument.tokens.spaceXs

            ShellLabel {
                id: claimIdentity

                anchors.verticalCenter: parent.verticalCenter
                visible: instrument.claim.claimed === true
                tokens: instrument.tokens
                role: "label"
                text:
                    instrument.claim.claimed === true
                    ? instrument.theme.provenanceLabel(
                        instrument.claim.identity
                      )
                    : ""
                color:
                    instrument.claim.claimed === true
                    ? instrument.theme.provenanceColor(
                        instrument.claim.identity
                      )
                    : instrument.theme.textPrimary
            }

            ShellLabel {
                anchors.verticalCenter: parent.verticalCenter
                objectName: "boot-claim-text"
                width:
                    Math.max(
                        0,
                        claimRow.width
                        - (claimIdentity.visible
                            ? claimIdentity.implicitWidth + claimRow.spacing
                            : 0)
                    )
                wrapMode: Text.WordWrap
                tokens: instrument.tokens
                role: "mono"
                text: {
                    if (instrument.claimCurrent)
                        return instrument.claim.claimed === true
                            ? "· rung " + instrument.claim.level + " until reboot"
                            : "No claim this boot";

                    if (instrument.claimRetained)
                        return "· rung " + instrument.claim.level
                            + " last seen · " + instrument.claimQualifier;

                    return "Unknown · " + instrument.claimQualifier;
                }
                color:
                    instrument.claimCurrent
                    ? instrument.theme.textPrimary
                    : instrument.theme.semanticStatusColor("warn")
            }
        }

        ShellLabel {
            tokens: instrument.tokens
            role: "meta"
            text: "Observed"
            color: instrument.theme.textQuiet
            width: 118
        }

        ShellLabel {
            tokens: instrument.tokens
            role: "mono"
            text:
                instrument.observedText
                + "  ·  every "
                + instrument.shellState.slowPollSeconds + " s"
            color: instrument.theme.textSecondary
        }
    }

    ShellDivider {
        width: parent.width
        vertical: false
        tokens: instrument.tokens
        theme: instrument.theme
    }

    // C. Four-rung policy instrument.
    Column {
        width: parent.width
        spacing: instrument.tokens.spaceSm

        ShellLabel {
            tokens: instrument.tokens
            role: "label"
            text: "GPU handoff ladder"
            color: instrument.theme.textSecondary
        }

        Row {
            id: cells

            width: parent.width
            spacing: instrument.tokens.policyCellGap

            readonly property int cellWidth:
                Math.floor((width - instrument.tokens.policyCellGap * 3) / 4)

            Repeater {
                model: instrument.rungs

                delegate: PolicyCell {
                    required property var modelData

                    width: cells.cellWidth
                    tokens: instrument.tokens
                    theme: instrument.theme
                    identity: modelData.identity
                    rung: modelData.rung
                    claimed: instrument.heldBy(modelData.identity)
                    compact: instrument.horizontal
                    countKnown: instrument.inventoryKnown
                    machineCount:
                        instrument.inventoryKnown
                        ? instrument.shellState.machinesWithProvenance(
                            modelData.identity
                          )
                        : 0
                }
            }
        }
    }

    // D. SERVICES, its own compartment, no connector.
    Rectangle {
        width: parent.width
        height: servicesRow.implicitHeight + instrument.tokens.spaceMd * 2
        radius: instrument.tokens.radiusCard
        color: instrument.theme.mix(
            instrument.theme.text,
            instrument.theme.raised,
            0.03
        )
        border.width: instrument.tokens.borderSize
        border.color: instrument.theme.boundary

        Row {
            id: servicesRow

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.margins: instrument.tokens.spaceMd
            spacing: instrument.tokens.spaceSm

            ProvenanceTag {
                anchors.verticalCenter: parent.verticalCenter
                tokens: instrument.tokens
                theme: instrument.theme
                identity: "services"
            }

            ShellLabel {
                anchors.verticalCenter: parent.verticalCenter
                tokens: instrument.tokens
                role: "meta"
                text: "Outside the GPU ladder"
                color: instrument.theme.textPrimary
            }

            ShellLabel {
                anchors.verticalCenter: parent.verticalCenter
                tokens: instrument.tokens
                role: "meta"
                text:
                    instrument.inventoryKnown
                    ? "· "
                        + instrument.shellState.machinesWithProvenance("services")
                        + (instrument.shellState.machinesWithProvenance("services") === 1
                            ? " machine"
                            : " machines")
                    : "· machine count unknown"
                color: instrument.theme.textQuiet
            }
        }
    }

    ShellLabel {
        width: parent.width
        tokens: instrument.tokens
        role: "meta"
        wrapMode: Text.WordWrap
        text: "Provenance labels do not grant permissions."
        color: instrument.theme.textQuiet
    }
}
