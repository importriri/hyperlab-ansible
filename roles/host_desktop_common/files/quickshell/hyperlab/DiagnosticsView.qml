// HyperLab Diagnostics (V447-C9.3).
//
// A read-only workspace ordered by the questions an operator actually asks:
//
//   Overview    what is not answering, and when was each fact observed
//   Isolation   who holds the GPU, what claim survives this boot, and what
//               the handoff policy is
//   Inventory   whether the machine inventory is trustworthy right now
//   Session     what the host knows about the focused surface and the
//               compositor
//
// Nothing here mutates anything, and nothing here is a shortcut into an
// operation. Unknown, absent, stale, unavailable and failed are five
// different words and keep five different meanings: a polling snapshot is
// never labelled live truth, and an unread source is never a healthy zero.

import QtQuick

Item {
    id: view

    required property var tokens
    required property var theme
    required property var icons
    required property var shellState
    required property var shellSurfaces

    readonly property var sections: [
        { "id": "overview", "label": "Overview" },
        { "id": "isolation", "label": "Isolation and GPU" },
        { "id": "inventory", "label": "Inventory" },
        { "id": "session", "label": "Session" }
    ]

    readonly property string section: view.shellSurfaces.subpage

    readonly property int degraded: view.shellState.degradedSources.length

    function stateWord(value) {
        switch (String(value)) {
        case "ok":
            return "Reporting";
        case "loading":
            return "Not yet observed";
        case "stale":
            return "Stale";
        default:
            return "Not answering";
        }
    }

    function stateClass(value) {
        switch (String(value)) {
        case "ok":
            return "ok";
        case "loading":
            return "";
        case "stale":
            return "warn";
        default:
            return "bad";
        }
    }

    WorkspaceFrame {
        id: frame

        anchors.fill: parent
        tokens: view.tokens
        theme: view.theme

        title: "Diagnostics"
        subtitle:
            view.degraded === 0
            ? "Every reviewed source is reporting"
            : (
                view.degraded === 1
                ? "1 source is not reporting"
                : view.degraded + " sources are not reporting"
              )
        subtitleClass: view.degraded === 0 ? "" : "warn"

        sections: view.sections
        currentSection: view.section
        maxContentWidth: 1040

        onSectionRequested: identifier => {
            view.shellSurfaces.openSubpage(identifier);
        }

        Column {
            width: frame.bodyWidth
            spacing: view.tokens.spaceLg

            // ------------------------------------------------ Overview

            SectionHeader {
                width: parent.width
                visible: view.section === "overview"
                tokens: view.tokens
                theme: view.theme
                label: "Source health"
                description:
                    "Each reviewed source, what it last said, and when. "
                    + "Slow sources are polled every "
                    + view.shellState.slowPollSeconds + " seconds."
            }

            ShellCard {
                width: parent.width
                visible: view.section === "overview"
                tokens: view.tokens
                theme: view.theme

                Column {
                    id: healthRows

                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: 2

                    Repeater {
                        model: view.shellState.sourceHealth

                        delegate: PanelRow {
                            required property var modelData

                            width: parent.width
                            tokens: view.tokens
                            theme: view.theme
                            title: modelData.name
                            value: view.stateWord(modelData.state)
                            valueColor:
                                view.theme.semanticStatusColor(
                                    view.stateClass(modelData.state)
                                )
                            hint:
                                modelData.at > 0
                                ? view.shellState.observedText(modelData.at)
                                    + " · "
                                    + view.shellState.observedAge(modelData.at)
                                : "never observed"
                        }
                    }
                }
            }

            SectionHeader {
                width: parent.width
                visible:
                    view.section === "overview"
                    && view.shellState.operations.length > 0
                tokens: view.tokens
                theme: view.theme
                label: "Recent operations"
                description:
                    "What the reviewed bridges reported. A launched operation "
                    + "terminal is accepted, not completed."
            }

            ShellCard {
                width: parent.width
                visible:
                    view.section === "overview"
                    && view.shellState.operations.length > 0
                tokens: view.tokens
                theme: view.theme

                Column {
                    id: operationRows

                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: view.tokens.spaceSm

                    Repeater {
                        model: view.shellState.operations

                        delegate: ActionFeedback {
                            required property var modelData

                            width: parent.width
                            tokens: view.tokens
                            theme: view.theme
                            record: modelData
                        }
                    }
                }
            }

            EmptyState {
                width: parent.width
                visible:
                    view.section === "overview"
                    && view.shellState.operations.length === 0
                tokens: view.tokens
                theme: view.theme
                kind: "empty"
                title: "No operations this session"
                description:
                    "Host and machine operations started from HyperLab are "
                    + "recorded here with what the bridge reported."
            }

            // ----------------------------------------------- Isolation

            SectionHeader {
                width: parent.width
                visible: view.section === "isolation"
                tokens: view.tokens
                theme: view.theme
                label: "Isolation and GPU"
                description:
                    "Current ownership, the claim that survives this boot, "
                    + "and the policy both are measured against."
            }

            ShellCard {
                width: parent.width
                visible: view.section === "isolation"
                tokens: view.tokens
                theme: view.theme
                padding: view.tokens.spaceXl

                OwnershipInstrument {
                    id: instrument

                    anchors.left: parent.left
                    anchors.right: parent.right
                    tokens: view.tokens
                    theme: view.theme
                    icons: view.icons
                    shellState: view.shellState
                    horizontal: frame.compact
                }
            }

            ShellLabel {
                width: parent.width
                visible: view.section === "isolation"
                tokens: view.tokens
                role: "meta"
                wrapMode: Text.WordWrap
                text:
                    "This diagram explains policy. It performs no handoff, "
                    + "and a provenance label grants no permission."
                color: view.theme.textQuiet
            }

            // ----------------------------------------------- Inventory

            SectionHeader {
                width: parent.width
                visible: view.section === "inventory"
                tokens: view.tokens
                theme: view.theme
                label: "Machine inventory"
                description: "Whether the inventory can be trusted right now."
            }

            ShellCard {
                width: parent.width
                visible: view.section === "inventory"
                tokens: view.tokens
                theme: view.theme

                Column {
                    id: inventoryRows

                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: 2

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        title: "Availability"
                        value:
                            view.shellState.machinesAvailable
                            ? "Reporting"
                            : "Not answering"
                        valueColor:
                            view.theme.semanticStatusColor(
                                view.shellState.machinesAvailable ? "ok" : "bad"
                            )
                        hint:
                            view.shellState.machinesAvailable
                            ? ""
                            : "the host inventory bridge did not answer"
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        title: "Defined machines"
                        value:
                            view.shellState.machinesAvailable
                            ? String(view.shellState.machines.length)
                            : "Unknown"
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        title: "Running machines"
                        value:
                            view.shellState.machinesAvailable
                            ? String(view.shellState.machinesRunning)
                            : "Unknown"
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        title: "Last observation"
                        value:
                            view.shellState.observedText(
                                view.shellState.machinesObservedAt
                            )
                        hint:
                            view.shellState.observedAge(
                                view.shellState.machinesObservedAt
                            )
                    }
                }
            }

            SectionHeader {
                width: parent.width
                visible: view.section === "inventory"
                tokens: view.tokens
                theme: view.theme
                label: "By provenance"
                description:
                    "Counts come from host-resolved provenance only. "
                    + "Nothing is grouped by name, network or appearance."
            }

            ShellCard {
                width: parent.width
                visible: view.section === "inventory"
                tokens: view.tokens
                theme: view.theme

                Column {
                    id: provenanceRows

                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: 2

                    Repeater {
                        model: view.shellState.provenanceOrder

                        delegate: Item {
                            required property var modelData

                            width: parent.width
                            height: view.tokens.rowHeightCompact

                            ProvenanceTag {
                                anchors.left: parent.left
                                anchors.leftMargin: view.tokens.spaceMd
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: view.tokens
                                theme: view.theme
                                identity: modelData
                            }

                            ShellLabel {
                                anchors.right: parent.right
                                anchors.rightMargin: view.tokens.spaceMd
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: view.tokens
                                role: "mono"
                                text:
                                    view.shellState.machinesAvailable
                                    ? String(
                                        view.shellState.machinesWithProvenance(
                                            modelData
                                        )
                                      )
                                    : "—"
                                color: view.theme.textPrimary
                            }
                        }
                    }
                }
            }

            SectionHeader {
                width: parent.width
                visible: view.section === "inventory"
                tokens: view.tokens
                theme: view.theme
                label: "Outside the product inventory"
                description:
                    "Libvirt domains with no Machine record: checked-in "
                    + "fixtures and external domains. They are observed "
                    + "here, never offered as Machines."
            }

            ShellCard {
                width: parent.width
                visible: view.section === "inventory"
                tokens: view.tokens
                theme: view.theme

                Column {
                    id: outsideRows

                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: 2

                    PanelRow {
                        width: parent.width
                        visible:
                            !view.shellState.outsideDomainsAvailable
                            || view.shellState.outsideDomains.length === 0
                        tokens: view.tokens
                        theme: view.theme
                        title: "Domains"
                        value:
                            view.shellState.outsideDomainsAvailable
                            ? "None"
                            : "Not answering"
                        valueColor:
                            view.theme.semanticStatusColor(
                                view.shellState.outsideDomainsAvailable
                                ? "ok"
                                : "bad"
                            )
                        hint:
                            view.shellState.outsideDomainsAvailable
                            ? ""
                            : "libvirt domains could not be observed"
                    }

                    Repeater {
                        model:
                            view.shellState.outsideDomainsAvailable
                            ? view.shellState.outsideDomains
                            : []

                        delegate: PanelRow {
                            required property var modelData

                            width: parent.width
                            tokens: view.tokens
                            theme: view.theme
                            title: modelData.name
                            value: view.icons.machineStateWord(modelData.state)
                            hint: view.shellState.outsideDomainKind(modelData)
                        }
                    }
                }
            }

            // ------------------------------------------------- Session

            SectionHeader {
                width: parent.width
                visible: view.section === "session"
                tokens: view.tokens
                theme: view.theme
                label: "Focused surface"
                description:
                    "What the compositor reports about the window in front "
                    + "of you, and what the host can say about its origin."
            }

            ShellCard {
                width: parent.width
                visible: view.section === "session"
                tokens: view.tokens
                theme: view.theme

                Column {
                    id: focusRows

                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: 2

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        title: "Compositor identity"
                        value:
                            view.shellState.focusedSurface.length > 0
                            ? view.shellState.focusedSurface
                            : "None reported"
                        hint:
                            "pid "
                            + (view.shellState.focusPayload.pid === null
                                ? "none"
                                : String(view.shellState.focusPayload.pid))
                            + (view.shellState.focusPayload.window_id.length > 0
                                ? " · window "
                                  + view.shellState.focusPayload.window_id
                                : "")
                            + " · host metadata, not a trust claim"
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        title: "Resolved provenance"
                        value:
                            view.shellState.focusedProvenance.available === true
                            ? view.theme.provenanceLabel(
                                view.shellState.focusedProvenance.identity
                              )
                            : String(view.shellState.focusedProvenance.label)
                        valueColor:
                            view.shellState.focusedProvenance.available === true
                            ? view.theme.provenanceColor(
                                view.shellState.focusedProvenance.identity
                              )
                            : (view.shellState.focusedProvenance.state
                                === "unresolved"
                                ? view.theme.semanticStatusColor("warning")
                                : view.theme.textQuiet)
                        hint: String(view.shellState.focusedProvenance.reason)
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        title: "Provenance source"
                        value:
                            view.shellState.focusedProvenance.domain.length > 0
                            ? view.shellState.focusedProvenance.domain
                            : (view.shellState.focusedProvenance.source.length > 0
                                ? view.shellState.focusedProvenance.source
                                : "None")
                        hint:
                            view.shellState.focusedProvenance.state
                            + " · "
                            + view.shellState.focusedProvenance.reasonCode
                            + (view.shellState.focusedProvenance.domain.length > 0
                                ? " · " + view.shellState.focusedProvenance.source
                                : "")
                    }
                }
            }

            SectionHeader {
                width: parent.width
                visible: view.section === "session"
                tokens: view.tokens
                theme: view.theme
                label: "Host telemetry"
            }

            ShellCard {
                width: parent.width
                visible: view.section === "session"
                tokens: view.tokens
                theme: view.theme

                HostFooter {
                    id: footer

                    anchors.left: parent.left
                    anchors.right: parent.right
                    tokens: view.tokens
                    theme: view.theme
                    icons: view.icons
                    shellState: view.shellState
                }
            }

            SectionHeader {
                width: parent.width
                visible: view.section === "session"
                tokens: view.tokens
                theme: view.theme
                label: "Appearance"
            }

            ShellCard {
                width: parent.width
                visible: view.section === "session"
                tokens: view.tokens
                theme: view.theme

                Column {
                    id: appearanceState

                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: 2

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        title: "Semantic palette"
                        value:
                            view.theme.paletteAvailable
                            ? view.theme.paletteName
                            : "Neutral fallback"
                        hint:
                            view.theme.paletteAvailable
                            ? "reviewed theme registry artefact"
                            : "the rendered palette could not be read"
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        title: "Provenance colours"
                        value:
                            view.theme.provenanceAvailable
                            ? "Complete"
                            : "Incomplete"
                        valueColor:
                            view.theme.semanticStatusColor(
                                view.theme.provenanceAvailable ? "ok" : "warn"
                            )
                        hint:
                            view.theme.provenanceAvailable
                            ? "every reviewed identity has a fixed colour"
                            : "provenance falls back to neutral text"
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        title: "Keyboard layout"
                        value: view.shellState.keyboardName()
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        title: "Wallpaper source"
                        value: view.shellState.wallpaperLabel()
                    }
                }
            }
        }
    }
}
