// HyperLab machine card (V447-C9.3).
//
// A machine is a contained environment resting on the host, so it is drawn
// as one bounded card: name first, provenance second, state third, the
// allocation it was given fourth, and its relationship to the passthrough
// GPU on the bottom row with the socket at the lower right.
//
// The card is a representation, not a claim: no preview, no image and
// nothing that implies isolation has been independently verified. Every
// value is the host inventory projection — memory and vCPU are labelled
// allocation, never consumption — and a value the host did not publish says
// Unknown instead of guessing None.
//
// Selecting a card opens the machine's pane. Selection never starts a
// machine, and no operation is reachable from the card itself.

import QtQuick

ShellCard {
    id: module

    required property var icons
    required property var machine

    property bool compactCard: false

    readonly property string relation:
        String(module.machine.gpu_relation)

    readonly property bool hasSocket:
        module.relation === "held"
        || module.relation === "configured"
        || module.relation === "unknown"

    readonly property string hardwareText: {
        switch (module.relation) {
        case "held":
            return "Holds the GPU";
        case "configured":
            return "Passthrough configured";
        case "unknown":
            return "Passthrough unknown";
        default:
            return "No passthrough";
        }
    }

    readonly property string memoryText: {
        const value = module.machine.memory_mb;

        if (typeof value !== "number")
            return "Unknown";

        if (value >= 1024) {
            return (value / 1024).toFixed(value % 1024 === 0 ? 0 : 1)
                + " GiB";
        }

        return value + " MiB";
    }

    readonly property string vcpuText:
        typeof module.machine.vcpus === "number"
        ? String(module.machine.vcpus)
        : "Unknown"

    // An unread domain has unknown networks; a domain with no interface
    // really has none. They are never the same sentence.
    readonly property string networkText: {
        if (module.machine.networks === null
            || module.machine.networks === undefined)
            return "Unknown";

        if (module.machine.network)
            return String(module.machine.network);

        return "None";
    }

    height: module.tokens.cardHeight
    padding: module.tokens.cardPadding
    interactive: true
    recessed: true

    accessibleName:
        String(module.machine.name)
        + ", " + module.osText
        + ", " + module.theme.provenanceLabel(module.machine.provenance)
        + ", " + module.icons.machineStateWord(module.machine.state)

    // The operating system, from the host's image manifest: a guest cannot
    // rename itself here. An unknown system says so.
    readonly property string osText:
        typeof module.machine.os === "string" && module.machine.os.length > 0
        ? module.machine.os
        : "OS unknown"

    // 1. Name, with the operating system on the same line.
    ShellLabel {
        id: nameLabel

        anchors.left: parent.left
        anchors.right: osLabel.left
        anchors.rightMargin: module.tokens.spaceSm
        anchors.top: parent.top
        tokens: module.tokens
        role: "title"
        text: String(module.machine.name)
        color: module.theme.textPrimary
    }

    ShellLabel {
        id: osLabel

        anchors.right: parent.right
        anchors.baseline: nameLabel.baseline
        tokens: module.tokens
        role: "meta"
        text: module.osText
        color: module.theme.textQuiet
    }

    // 2. Provenance and 3. state on one line.
    ProvenanceTag {
        id: provenanceRow

        anchors.left: parent.left
        anchors.top: nameLabel.bottom
        anchors.topMargin: module.tokens.spaceSm
        tokens: module.tokens
        theme: module.theme
        identity: String(module.machine.provenance)
    }

    StateChip {
        anchors.right: parent.right
        anchors.verticalCenter: provenanceRow.verticalCenter
        tokens: module.tokens
        theme: module.theme
        icons: module.icons
        state: String(module.machine.state)
    }

    // 4. Allocation. Labelled allocation, because it is what the machine was
    // given, not what it is using.
    Grid {
        id: allocation

        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: provenanceRow.bottom
        anchors.topMargin: module.tokens.spaceMd

        columns: 3
        columnSpacing: module.tokens.spaceXl
        rowSpacing: module.tokens.spaceXs

        Column {
            spacing: 1

            ShellLabel {
                tokens: module.tokens
                role: "meta"
                text: "Memory"
                color: module.theme.textQuiet
            }

            ShellLabel {
                tokens: module.tokens
                role: "mono"
                text: module.memoryText
                color: module.theme.textPrimary
            }
        }

        Column {
            spacing: 1

            ShellLabel {
                tokens: module.tokens
                role: "meta"
                text: "vCPU"
                color: module.theme.textQuiet
            }

            ShellLabel {
                tokens: module.tokens
                role: "mono"
                text: module.vcpuText
                color: module.theme.textPrimary
            }
        }

        Column {
            spacing: 1

            ShellLabel {
                tokens: module.tokens
                role: "meta"
                text: "Network"
                color: module.theme.textQuiet
            }

            ShellLabel {
                tokens: module.tokens
                role: "mono"
                text: module.networkText
                color: module.theme.textPrimary
            }
        }
    }

    // 5. Hardware relationship and socket.
    Row {
        anchors.left: parent.left
        anchors.bottom: parent.bottom
        spacing: module.tokens.spaceSm

        ShellIcon {
            anchors.verticalCenter: parent.verticalCenter
            tokens: module.tokens
            text: module.icons.gpu
            color:
                module.hasSocket
                ? module.theme.textSecondary
                : module.theme.textQuiet
        }

        ShellLabel {
            anchors.verticalCenter: parent.verticalCenter
            tokens: module.tokens
            role: "meta"
            text: module.hardwareText
            color:
                module.hasSocket
                ? module.theme.textPrimary
                : module.theme.textQuiet
        }
    }

    HardwareSocket {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        visible: module.hasSocket
        tokens: module.tokens
        theme: module.theme
        relation: module.relation
    }
}
