// HyperLab selected machine (V447-C9.3).
//
// One machine, in the order an operator decides things:
//
//   identity   name, provenance, state, how fresh the observation is
//   Connect    which transport to use, and why one is unavailable
//   Power      start, graceful shutdown, guest reboot
//   Advanced   the operations that do not ask the guest first
//   Details    what the host published, with Unknown where it published
//              nothing
//   Activity   what recent operations actually reported
//
// Availability is never guessed. The reviewed machine bridge answers what
// this machine supports right now and why it does not support the rest, and
// that answer is shown verbatim on the disabled control.
//
// The pane holds a backend identifier, not a copied machine, so a refreshed
// inventory resolves it again and a removed machine becomes "No longer
// available" instead of a stale object with live-looking buttons.

import QtQuick

Item {
    id: pane

    required property var tokens
    required property var theme
    required property var icons
    required property var shellState
    required property var shellSurfaces
    required property var machineActions
    required property var machine

    property bool showBack: false

    readonly property string identifier:
        pane.shellSurfaces.selectedMachineId

    readonly property bool present: pane.machine !== null

    readonly property string stateWord:
        pane.present
        ? pane.icons.machineStateWord(pane.machine.state)
        : "Unknown"

    // The bridge's answer, as ShellState observed and validated it.
    readonly property var capabilities: pane.shellState.machineCapabilities

    readonly property bool capabilitiesReady:
        pane.capabilities.state === "ok"
        && pane.capabilities.machine === pane.identifier

    readonly property bool capabilitiesUnavailable:
        pane.capabilities.state === "unavailable"
        && pane.capabilities.machine === pane.identifier

    readonly property var operation:
        pane.shellState.latestOperationFor(pane.identifier)

    // Presentation never decides availability; ShellState applies the
    // bridge's answer and the currency of every fact it depends on.
    function capability(verb) {
        return pane.shellState.capabilityFor(pane.identifier, verb);
    }

    // Every operation goes through the same request. Destructive ones stop
    // at the shared confirmation, which captures this exact target.
    function request(verb) {
        if (!pane.present)
            return;

        const entry = pane.capability(verb);

        if (!entry.available)
            return;

        if (!pane.machineActions.destructive(verb)) {
            pane.machineActions.invoke(verb, pane.identifier);
            return;
        }

        pane.shellSurfaces.requestConfirmation({
            "kind": "machine",
            "actionId": verb,
            "targetId": pane.identifier,
            "targetName": pane.identifier,
            "title": pane.machineActions.labelFor(verb) + " this machine?",
            "consequence":
                "Force stop cuts power to the guest without asking it to "
                + "shut down. Unsaved guest data is lost, and a VFIO guest "
                + "may need its devices re-attached.",
            "confirmLabel": pane.machineActions.labelFor(verb),
            "requiresName": true,
            "generation": pane.shellState.machinesGeneration
        });
    }

    Rectangle {
        anchors.fill: parent
        color: pane.theme.mantle
    }

    FocusFollow {
        flickable: viewport
    }

    Flickable {
        id: viewport

        anchors.fill: parent
        contentWidth: width
        contentHeight: column.implicitHeight + pane.tokens.spaceXl * 2
        interactive: contentHeight > height
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        Column {
            id: column

            x: pane.tokens.spaceXl
            y: pane.tokens.spaceXl
            width: viewport.width - pane.tokens.spaceXl * 2
            spacing: pane.tokens.spaceLg

            // Header.
            Row {
                width: parent.width
                spacing: pane.tokens.spaceSm

                ShellControl {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: pane.showBack
                    tokens: pane.tokens
                    theme: pane.theme
                    flat: true
                    accessibleName: "Back to the inventory"

                    content: [
                        ShellIcon {
                            anchors.verticalCenter: parent.verticalCenter
                            tokens: pane.tokens
                            text: pane.icons.back
                            color: pane.theme.textSecondary
                        }
                    ]

                    onActivated: pane.shellSurfaces.clearMachineSelection()
                }

                ShellLabel {
                    anchors.verticalCenter: parent.verticalCenter
                    width:
                        parent.width
                        - (pane.showBack ? pane.tokens.controlHeight * 2 : 0)
                        - pane.tokens.controlHeight
                        - pane.tokens.spaceSm * 3
                    tokens: pane.tokens
                    role: "label"
                    text: "Machine"
                    color: pane.theme.textSecondary
                }

                ShellControl {
                    anchors.verticalCenter: parent.verticalCenter
                    tokens: pane.tokens
                    theme: pane.theme
                    flat: true
                    accessibleName: "Close this machine"

                    content: [
                        ShellIcon {
                            anchors.verticalCenter: parent.verticalCenter
                            tokens: pane.tokens
                            text: pane.icons.close
                            color: pane.theme.textSecondary
                        }
                    ]

                    onActivated: pane.shellSurfaces.clearMachineSelection()
                }
            }

            // Identity. The name survives even when the machine does not, so
            // an operator can see which machine disappeared.
            ShellLabel {
                width: parent.width
                tokens: pane.tokens
                role: "heading"
                wrapMode: Text.WrapAnywhere
                text: pane.identifier
                color: pane.theme.textPrimary
            }

            ShellLabel {
                width: parent.width
                visible: !pane.present
                tokens: pane.tokens
                role: "body"
                wrapMode: Text.WordWrap
                text:
                    "No longer available. This machine is not in the current "
                    + "inventory, so no operation can be offered for it."
                color: pane.theme.semanticStatusColor("warn")
            }

            Row {
                width: parent.width
                visible: pane.present
                spacing: pane.tokens.spaceLg

                ProvenanceTag {
                    anchors.verticalCenter: parent.verticalCenter
                    tokens: pane.tokens
                    theme: pane.theme
                    identity:
                        pane.present
                        ? String(pane.machine.provenance)
                        : "unclassified"
                }

                StateChip {
                    anchors.verticalCenter: parent.verticalCenter
                    tokens: pane.tokens
                    theme: pane.theme
                    icons: pane.icons
                    state: pane.present ? String(pane.machine.state) : ""
                }
            }

            ShellLabel {
                width: parent.width
                visible: pane.present
                tokens: pane.tokens
                role: "meta"
                text:
                    "Observed "
                    + pane.shellState.observedText(
                        pane.shellState.machinesObservedAt
                    )
                    + " · "
                    + pane.shellState.observedAge(
                        pane.shellState.machinesObservedAt
                    )
                color: pane.theme.textQuiet
            }

            ShellDivider {
                width: parent.width
                vertical: false
                tokens: pane.tokens
                theme: pane.theme
            }

            // Connect.
            SectionHeader {
                width: parent.width
                visible: pane.present
                tokens: pane.tokens
                theme: pane.theme
                label: "Connect"
                description:
                    pane.capabilitiesReady
                    ? "Transports this machine currently supports"
                    : (
                        pane.capabilitiesUnavailable
                        ? "The machine bridge did not answer"
                        : "Checking what this machine supports"
                      )
            }

            Column {
                width: parent.width
                visible: pane.present
                spacing: 2

                Repeater {
                    model: pane.machineActions.connectVerbs

                    delegate: PanelRow {
                        required property var modelData

                        readonly property var entry: pane.capability(modelData)

                        width: parent.width
                        tokens: pane.tokens
                        theme: pane.theme
                        glyph:
                            modelData === "console"
                            ? pane.icons.consoleTransport
                            : pane.icons.connect
                        readonly property bool connected:
                            pane.machineActions.connectionActive(
                                pane.identifier,
                                modelData
                            )

                        title: pane.machineActions.labelFor(modelData)
                        interactive: true
                        enabled: entry.available && !connected
                        disabledReason:
                            connected ? "Already open" : entry.reason
                        hint: connected ? "open now" : "open"

                        onActivated: pane.request(modelData)
                    }
                }
            }

            ShellDivider {
                width: parent.width
                visible: pane.present
                vertical: false
                tokens: pane.tokens
                theme: pane.theme
            }

            // Power.
            SectionHeader {
                width: parent.width
                visible: pane.present
                tokens: pane.tokens
                theme: pane.theme
                label: "Power"
                description: "Lifecycle the guest is asked to cooperate with"
            }

            Column {
                width: parent.width
                visible: pane.present
                spacing: 2

                Repeater {
                    model: pane.machineActions.powerVerbs

                    delegate: PanelRow {
                        required property var modelData

                        readonly property var entry: pane.capability(modelData)

                        width: parent.width
                        tokens: pane.tokens
                        theme: pane.theme
                        glyph: pane.icons.power
                        title: pane.machineActions.labelFor(modelData)
                        interactive: true
                        enabled: entry.available
                        busy: pane.machineActions.busy
                        disabledReason: entry.reason
                        hint: "run"

                        onActivated: pane.request(modelData)
                    }
                }
            }

            // Advanced. Kept separate, because these do not ask the guest.
            SectionHeader {
                width: parent.width
                visible: pane.present
                tokens: pane.tokens
                theme: pane.theme
                label: "Advanced"
                description: "Operations the guest cannot negotiate"
            }

            Column {
                width: parent.width
                visible: pane.present
                spacing: 2

                Repeater {
                    model: pane.machineActions.advancedVerbs

                    delegate: PanelRow {
                        required property var modelData

                        readonly property var entry: pane.capability(modelData)

                        width: parent.width
                        tokens: pane.tokens
                        theme: pane.theme
                        glyph: pane.icons.warning
                        title: pane.machineActions.labelFor(modelData)
                        tone: "danger"
                        interactive: true
                        enabled: entry.available
                        busy: pane.machineActions.busy
                        disabledReason: entry.reason
                        hint: "confirmation required"

                        onActivated: pane.request(modelData)
                    }
                }
            }

            ShellDivider {
                width: parent.width
                visible: pane.present
                vertical: false
                tokens: pane.tokens
                theme: pane.theme
            }

            // Details.
            SectionHeader {
                width: parent.width
                visible: pane.present
                tokens: pane.tokens
                theme: pane.theme
                label: "Details"
            }

            Grid {
                id: details

                // Labels take a fixed column; values get the rest and wrap,
                // so a long network list or name never runs out of the pane.
                readonly property real labelWidth: 88
                readonly property real valueWidth:
                    Math.max(0, details.width - details.labelWidth - details.columnSpacing)

                width: parent.width
                visible: pane.present
                columns: 2
                columnSpacing: pane.tokens.spaceMd
                rowSpacing: pane.tokens.spaceSm

                ShellLabel { width: details.labelWidth; tokens: pane.tokens; role: "meta"; text: "Managed"; color: pane.theme.textQuiet }
                ShellLabel {
                    width: details.valueWidth
                    wrapMode: Text.WordWrap
                    tokens: pane.tokens
                    role: "body"
                    text: {
                        if (!pane.present)
                            return "";

                        if (pane.machine.managed === true)
                            return "HyperLab spec";

                        return pane.machine.managed === false
                            ? "External domain"
                            : "Unknown";
                    }
                    color: pane.theme.textPrimary
                }

                ShellLabel { width: details.labelWidth; tokens: pane.tokens; role: "meta"; text: "Lifecycle"; color: pane.theme.textQuiet }
                ShellLabel {
                    width: details.valueWidth
                    wrapMode: Text.WordWrap
                    tokens: pane.tokens
                    role: "body"
                    text:
                        pane.present && pane.machine.lifecycle
                        ? String(pane.machine.lifecycle)
                        : "Unknown"
                    color: pane.theme.textPrimary
                }

                ShellLabel { width: details.labelWidth; tokens: pane.tokens; role: "meta"; text: "Memory"; color: pane.theme.textQuiet }
                ShellLabel {
                    width: details.valueWidth
                    wrapMode: Text.WrapAnywhere
                    tokens: pane.tokens
                    role: "mono"
                    text:
                        pane.present && typeof pane.machine.memory_mb === "number"
                        ? pane.machine.memory_mb + " MiB allocated"
                        : "Unknown"
                    color: pane.theme.textPrimary
                }

                ShellLabel { width: details.labelWidth; tokens: pane.tokens; role: "meta"; text: "vCPU"; color: pane.theme.textQuiet }
                ShellLabel {
                    width: details.valueWidth
                    wrapMode: Text.WrapAnywhere
                    tokens: pane.tokens
                    role: "mono"
                    text:
                        pane.present && typeof pane.machine.vcpus === "number"
                        ? pane.machine.vcpus + " allocated"
                        : "Unknown"
                    color: pane.theme.textPrimary
                }

                ShellLabel { width: details.labelWidth; tokens: pane.tokens; role: "meta"; text: "Networks"; color: pane.theme.textQuiet }
                ShellLabel {
                    width: details.valueWidth
                    wrapMode: Text.WrapAnywhere
                    tokens: pane.tokens
                    role: "mono"
                    text: {
                        if (!pane.present)
                            return "";

                        const networks = pane.machine.networks;

                        if (networks === null || networks === undefined)
                            return "Unknown";

                        return networks.length > 0
                            ? networks.join(", ")
                            : "None";
                    }
                    color: pane.theme.textPrimary
                }

                ShellLabel { width: details.labelWidth; tokens: pane.tokens; role: "meta"; text: "GPU"; color: pane.theme.textQuiet }
                ShellLabel {
                    width: details.valueWidth
                    wrapMode: Text.WordWrap
                    tokens: pane.tokens
                    role: "body"
                    text: pane.present ? String(pane.machine.gpu) : ""
                    color: pane.theme.textPrimary
                }
            }

            ShellLabel {
                width: parent.width
                visible:
                    pane.present
                    && pane.machine.blocked !== null
                    && pane.machine.blocked !== undefined
                tokens: pane.tokens
                role: "meta"
                wrapMode: Text.WordWrap
                text:
                    pane.present && pane.machine.blocked
                    ? "Cannot start: the host reports "
                        + pane.machine.blocked.short_mb
                        + " MiB short of this allocation."
                    : ""
                color: pane.theme.semanticStatusColor("warn")
            }

            ShellDivider {
                width: parent.width
                visible: pane.operation !== null
                vertical: false
                tokens: pane.tokens
                theme: pane.theme
            }

            // Activity. What the bridge actually reported, never what the
            // interface hoped it would report.
            SectionHeader {
                width: parent.width
                visible: pane.operation !== null
                tokens: pane.tokens
                theme: pane.theme
                label: "Activity"
            }

            ActionFeedback {
                width: parent.width
                visible: pane.operation !== null
                tokens: pane.tokens
                theme: pane.theme
                record: pane.operation
            }

            ShellLabel {
                width: parent.width
                visible:
                    pane.present
                    && typeof pane.machine.managed === "boolean"
                tokens: pane.tokens
                role: "meta"
                wrapMode: Text.WordWrap
                text:
                    pane.present && pane.machine.managed === true
                    ? "Power operations for this machine run its HyperLab spec in a separate operation window."
                    : "Power operations for this external machine go directly to the host."
                color: pane.theme.textQuiet
            }
        }
    }
}
