// HyperLab Machines workspace (V447-C9.3).
//
// The inventory and the machine an operator is working on, in one page. The
// inventory is grouped by host-resolved provenance — the grouping the older
// product got right — with a count per group, an explicit Unclassified group
// last, and no decorative wall of identical tiles.
//
// Every fact is the host inventory projection. Empty, filtered and
// unavailable are three different states with three different sentences, and
// an unavailable inventory never looks like an empty one. Selecting a card
// opens the machine's pane; selection never starts anything.
//
// Large inventories stay reachable: the list layout is virtualized and
// becomes the default past the point where a grid stops being readable.

import QtQuick

Item {
    id: stage

    required property var tokens
    required property var theme
    required property var icons
    required property var shellState
    required property var machineActions
    required property var shellSurfaces

    property string query: ""
    property string layoutMode: "auto"
    property string stateFilter: "all"

    readonly property int total: stage.shellState.machines.length

    // Past this a grid stops being an inventory and starts being wallpaper.
    readonly property int denseThreshold: 60

    readonly property string layout:
        stage.layoutMode !== "auto"
        ? stage.layoutMode
        : (stage.total > stage.denseThreshold ? "list" : "grid")

    readonly property string selectedId:
        stage.shellSurfaces.selectedMachineId

    readonly property bool hasSelection: stage.selectedId.length > 0

    readonly property var machine:
        stage.shellState.machineById(stage.selectedId)

    readonly property bool wide:
        stage.width >= stage.tokens.breakpointMedium

    // Narrow outputs show one region at a time: the pane replaces the
    // inventory and an explicit Back returns to it.
    readonly property bool paneOnly: stage.hasSelection && !stage.wide

    readonly property int paneWidth:
        stage.width >= stage.tokens.breakpointWide
        ? stage.tokens.contextPaneWide
        : stage.tokens.contextPaneCompact

    readonly property var filtered: {
        const needle = stage.query.trim().toLowerCase();
        const out = [];

        for (let index = 0; index < stage.shellState.machines.length; index++) {
            const row = stage.shellState.machines[index];
            const running = String(row.state) === "running";

            if (stage.stateFilter === "running" && !running)
                continue;

            if (stage.stateFilter === "stopped" && running)
                continue;

            if (needle.length > 0) {
                const haystack =
                    String(row.name).toLowerCase()
                    + " " + String(row.provenance).toLowerCase()
                    + " " + String(row.state).toLowerCase();

                if (haystack.indexOf(needle) < 0)
                    continue;
            }

            out.push(row);
        }

        return out;
    }

    readonly property var groups: {
        const out = [];

        for (
            let order = 0;
            order < stage.shellState.provenanceOrder.length;
            order++
        ) {
            const identity = stage.shellState.provenanceOrder[order];
            const rows = [];

            for (let index = 0; index < stage.filtered.length; index++) {
                if (String(stage.filtered[index].provenance) === identity)
                    rows.push(stage.filtered[index]);
            }

            if (rows.length > 0)
                out.push({ "identity": identity, "machines": rows });
        }

        return out;
    }

    readonly property string inventoryState:
        stage.shellState.sourceState(
            stage.shellState.machinesSourceState,
            stage.shellState.machinesObservedAt
        )

    readonly property bool inventoryAvailable:
        stage.shellState.machinesAvailable

    // Capabilities belong to the selected machine and the generation it was
    // resolved against; a new selection or a new snapshot re-asks the bridge.
    function refreshCapabilities() {
        if (!stage.hasSelection) {
            stage.machineActions.clearCapabilities();
            return;
        }

        stage.machineActions.probe(
            stage.selectedId,
            stage.shellState.machinesGeneration
        );
    }

    Connections {
        target: stage.shellSurfaces

        function onSelectedMachineIdChanged() {
            stage.refreshCapabilities();
        }
    }

    Connections {
        target: stage.shellState

        // The inventory changed underneath the answer: ask again. An
        // identical poll does not change the generation, so an unchanged
        // machine is not re-probed every 30 seconds.
        function onMachinesGenerationChanged() {
            if (
                stage.hasSelection
                && stage.shellState.capabilityRequest.generation
                    !== stage.shellState.machinesGeneration
            ) {
                stage.refreshCapabilities();
            }
        }
    }

    Row {
        anchors.fill: parent
        spacing: 0

        WorkspaceFrame {
            id: frame

            visible: !stage.paneOnly
            width:
                stage.hasSelection && stage.wide
                ? parent.width - stage.paneWidth - 1
                : parent.width
            height: parent.height

            tokens: stage.tokens
            theme: stage.theme

            title: "Machines"

            subtitle:
                stage.inventoryAvailable
                ? (
                    stage.inventoryState === "stale"
                    ? stage.total + " defined · "
                        + stage.shellState.machinesRunning
                        + " running · last observed "
                        + stage.shellState.observedAge(
                            stage.shellState.machinesObservedAt
                        )
                    : stage.total + " defined · "
                        + stage.shellState.machinesRunning + " running"
                  )
                : "Inventory unavailable"

            subtitleClass:
                stage.inventoryAvailable
                ? (stage.inventoryState === "stale" ? "warn" : "")
                : "warn"

            trailing: [
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: frame.width > 640
                    width: Math.min(240, frame.width / 3)
                    height: stage.tokens.controlHeightLarge
                    radius: stage.tokens.radiusControl
                    color: stage.theme.raised
                    border.width:
                        searchInput.activeFocus
                        ? stage.tokens.focusOutline
                        : stage.tokens.borderSize
                    border.color:
                        searchInput.activeFocus
                        ? stage.theme.focusRing
                        : stage.theme.boundary

                    Row {
                        anchors.fill: parent
                        anchors.leftMargin: stage.tokens.spaceMd
                        anchors.rightMargin: stage.tokens.spaceMd
                        spacing: stage.tokens.spaceSm

                        ShellIcon {
                            anchors.verticalCenter: parent.verticalCenter
                            tokens: stage.tokens
                            text: stage.icons.search
                            color: stage.theme.textSecondary
                        }

                        TextInput {
                            id: searchInput

                            anchors.verticalCenter: parent.verticalCenter
                            width:
                                parent.width
                                - stage.tokens.iconBar
                                - stage.tokens.spaceSm

                            font.family: stage.tokens.fontSans
                            font.pixelSize: stage.tokens.fontBody
                            color: stage.theme.textPrimary
                            selectionColor: stage.theme.fillSelected
                            selectedTextColor: stage.theme.textPrimary
                            clip: true

                            Accessible.role: Accessible.EditableText
                            Accessible.name: "Filter machines"

                            onTextChanged: stage.query = text

                            ShellLabel {
                                anchors.verticalCenter: parent.verticalCenter
                                visible: searchInput.text.length === 0
                                tokens: stage.tokens
                                role: "body"
                                text: "Filter"
                                color: stage.theme.textQuiet
                            }
                        }
                    }
                },

                ShellControl {
                    anchors.verticalCenter: parent.verticalCenter
                    height: stage.tokens.controlHeightLarge
                    tokens: stage.tokens
                    theme: stage.theme
                    flat: true
                    accessibleName:
                        stage.layout === "grid"
                        ? "Switch to list layout"
                        : "Switch to grid layout"

                    content: [
                        ShellIcon {
                            anchors.verticalCenter: parent.verticalCenter
                            tokens: stage.tokens
                            text:
                                stage.layout === "grid"
                                ? stage.icons.list
                                : stage.icons.grid
                            color: stage.theme.textSecondary
                        }
                    ]

                    onActivated:
                        stage.layoutMode =
                            stage.layout === "grid" ? "list" : "grid"
                }
            ]

            Column {
                width: frame.bodyWidth
                spacing: stage.tokens.spaceLg

                // Unavailable and empty are different sentences, and a filter
                // that hides everything is a third.
                EmptyState {
                    width: parent.width
                    visible: !stage.inventoryAvailable
                    tokens: stage.tokens
                    theme: stage.theme
                    kind: "unavailable"
                    title: "Machine inventory cannot be read"
                    description:
                        "The host inventory source did not answer. "
                        + "Diagnostics has the observation detail."
                }

                EmptyState {
                    width: parent.width
                    visible: stage.inventoryAvailable && stage.total === 0
                    tokens: stage.tokens
                    theme: stage.theme
                    kind: "empty"
                    title: "No Machines yet"
                    description:
                        "Create a Machine from a reviewed Template. "
                        + "Fixture and external libvirt domains stay in Diagnostics."
                }

                EmptyState {
                    width: parent.width
                    visible:
                        stage.inventoryAvailable
                        && stage.total > 0
                        && stage.filtered.length === 0
                    tokens: stage.tokens
                    theme: stage.theme
                    kind: "filtered"
                    title: "No machine matches this filter"
                    description:
                        "Clear the filter to see all "
                        + stage.total + " machines."
                }

                // Grouped grid.
                Repeater {
                    model:
                        stage.layout === "grid" && stage.filtered.length > 0
                        ? stage.groups
                        : []

                    delegate: Column {
                        required property var modelData

                        width: frame.bodyWidth
                        spacing: stage.tokens.spaceMd

                        SectionHeader {
                            width: parent.width
                            tokens: stage.tokens
                            theme: stage.theme
                            label: stage.theme.provenanceLabel(
                                modelData.identity
                            )

                            trailing: [
                                ShellLabel {
                                    anchors.verticalCenter: parent.verticalCenter
                                    tokens: stage.tokens
                                    role: "mono"
                                    text: String(modelData.machines.length)
                                    color: stage.theme.textSecondary
                                }
                            ]
                        }

                        Flow {
                            width: parent.width
                            spacing: stage.tokens.cardGap

                            Repeater {
                                model: modelData.machines

                                delegate: MachineModule {
                                    required property var modelData

                                    width: stage.cardWidth(frame.bodyWidth)
                                    tokens: stage.tokens
                                    theme: stage.theme
                                    icons: stage.icons
                                    machine: modelData
                                    selected:
                                        String(modelData.name)
                                        === stage.selectedId

                                    onActivated:
                                        stage.shellSurfaces.selectMachine(
                                            String(modelData.name),
                                            stage.shellState.machinesGeneration,
                                            false
                                        )
                                }
                            }
                        }

                        ShellDivider {
                            width: parent.width
                            vertical: false
                            tokens: stage.tokens
                            theme: stage.theme
                        }
                    }
                }

                // Virtualized list. Every machine stays reachable regardless
                // of how many there are.
                ListView {
                    width: parent.width
                    visible: stage.layout === "list" && stage.filtered.length > 0
                    height:
                        visible
                        ? Math.min(
                            stage.filtered.length * stage.tokens.listRowHeight,
                            Math.max(
                                stage.tokens.listRowHeight,
                                stage.height - stage.tokens.workspaceHeaderHeight
                                    - stage.tokens.spaceSection
                            )
                          )
                        : 0

                    model: stage.filtered
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds
                    cacheBuffer: stage.tokens.listRowHeight * 4

                    delegate: Item {
                        required property var modelData

                        width: ListView.view.width
                        height: stage.tokens.listRowHeight

                        MachineListRow {
                            anchors.fill: parent
                            anchors.bottomMargin: 1
                            tokens: stage.tokens
                            theme: stage.theme
                            icons: stage.icons
                            machine: modelData
                            selected:
                                String(modelData.name) === stage.selectedId

                            onActivated:
                                stage.shellSurfaces.selectMachine(
                                    String(modelData.name),
                                    stage.shellState.machinesGeneration,
                                    false
                                )
                        }
                    }
                }

                ShellLabel {
                    width: parent.width
                    visible:
                        stage.inventoryAvailable
                        && !stage.hasSelection
                        && stage.filtered.length > 0
                    tokens: stage.tokens
                    role: "meta"
                    text: "Select a machine to see its connections and power controls."
                    color: stage.theme.textQuiet
                }
            }
        }

        Rectangle {
            visible: stage.hasSelection && stage.wide
            width: visible ? 1 : 0
            height: parent.height
            color: stage.theme.hairline
        }

        MachineContextPane {
            visible: stage.hasSelection
            width: stage.paneOnly ? parent.width : stage.paneWidth
            height: parent.height

            tokens: stage.tokens
            theme: stage.theme
            icons: stage.icons
            shellState: stage.shellState
            machineActions: stage.machineActions
            shellSurfaces: stage.shellSurfaces
            machine: stage.machine
            showBack: stage.paneOnly
        }
    }

    // Cards stay inside the reviewed 300-420 range and fill the row evenly
    // rather than leaving a ragged trailing gap.
    function cardWidth(available) {
        const gap = stage.tokens.cardGap;
        const columns = Math.max(
            1,
            Math.floor((available + gap) / (stage.tokens.cardMinWidth + gap))
        );

        return Math.min(
            stage.tokens.cardMaxWidth,
            Math.floor((available - gap * (columns - 1)) / columns)
        );
    }
}
