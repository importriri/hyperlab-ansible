// HyperLab Workbench (ADR 0015, roadmap milestone 3).
//
// Golden Image candidates: domains adopted to be captured into an image.
// A candidate is never a product Machine, so it lives here and never in
// Machines; the Workbench refuses to adopt or seal a product Machine.
//
// The list is the bridge's answer (the root-owned registry joined with live
// state) and is presentation only. Start, shut down and the console reach a
// candidate as they reach any domain; Seal hands a shut-off candidate to the
// reviewed seal playbook through the operation runner, which asks for the
// password in its own window. Every action is checked again by the bridge.

import QtQuick

Item {
    id: view

    required property var tokens
    required property var theme
    required property var icons
    required property var machineActions
    required property var shellSurfaces

    readonly property var candidates: view.machineActions.workbenchCandidates
    readonly property string readState: view.machineActions.workbenchState

    function refresh() {
        view.machineActions.requestWorkbench();
    }

    function runtimeWord(runtime) {
        switch (String(runtime)) {
        case "running":
            return "Running";
        case "shut off":
            return "Shut off";
        case "missing":
            return "No such domain";
        case "crashed":
            return "Crashed";
        default:
            return "State " + String(runtime);
        }
    }

    // What may be offered for one candidate; the bridge decides for real.
    function actionsFor(row) {
        const off = row.runtime === "shut off" || row.runtime === "crashed";
        const running = row.runtime === "running";
        return [
            { "verb": "start", "label": "Start", "enabled": off,
              "reason": "Only a shut-off candidate starts" },
            { "verb": "shutdown", "label": "Shut down", "enabled": running,
              "reason": "The candidate is not running" },
            { "verb": "console", "label": "Console", "enabled": running,
              "reason": "The console needs a running candidate" },
            { "verb": "seal", "label": "Seal", "enabled": row.state === "candidate" && off,
              "reason": row.state === "captured"
                  ? "Already captured; release it before sealing again"
                  : "Shut the candidate down before sealing it" }
        ];
    }

    onVisibleChanged: {
        if (view.visible)
            view.refresh();
    }

    Timer {
        interval: 15000
        running: view.visible
        repeat: true
        onTriggered: view.refresh()
    }

    Connections {
        target: view.machineActions

        function onInventoryRefreshRequested() {
            if (view.visible)
                view.refresh();
        }
    }

    WorkspaceFrame {
        id: frame

        anchors.fill: parent
        tokens: view.tokens
        theme: view.theme

        title: "Workbench"
        subtitle: "Golden Image candidates. A candidate is never a product Machine."
        maxContentWidth: 1040

        Column {
            width: frame.bodyWidth
            spacing: view.tokens.spaceLg

            SectionHeader {
                width: parent.width
                tokens: view.tokens
                theme: view.theme
                label: "Candidates"
                description:
                    "Adopted with playbooks/workbench-adopt.yml. Seal copies a shut-off "
                    + "candidate, generalizes and scans the copy, records its build "
                    + "provenance and stages it for import; the operation window asks "
                    + "for your password."
            }

            EmptyState {
                width: parent.width
                visible: view.readState !== "ready"
                tokens: view.tokens
                theme: view.theme
                kind: view.readState === "unavailable" ? "unavailable" : "empty"
                title: {
                    switch (view.readState) {
                    case "unavailable":
                        return "The Workbench could not be read";
                    case "empty":
                        return "The Workbench is empty";
                    default:
                        return "Reading the Workbench";
                    }
                }
                description: {
                    switch (view.readState) {
                    case "unavailable":
                        return view.machineActions.workbenchDetail;
                    case "empty":
                        return "Adopt a domain built for capture with playbooks/workbench-adopt.yml.";
                    default:
                        return "";
                    }
                }
            }

            Repeater {
                model: view.readState === "ready" ? view.candidates : []

                ShellCard {
                    id: card

                    required property var modelData

                    objectName: "workbench-" + card.modelData.domain
                    width: parent.width
                    tokens: view.tokens
                    theme: view.theme
                    accessibleName: "Workbench candidate " + card.modelData.domain

                    Column {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        spacing: view.tokens.spaceSm

                        Row {
                            spacing: view.tokens.spaceMd

                            ShellLabel {
                                tokens: view.tokens
                                role: "heading"
                                text: card.modelData.domain
                                color: view.theme.textPrimary
                            }

                            ShellLabel {
                                tokens: view.tokens
                                role: "meta"
                                text: "to " + card.modelData.image_id
                                    + " · " + card.modelData.profile
                                    + " over " + card.modelData.base_image
                                color: view.theme.textSecondary
                            }
                        }

                        ShellLabel {
                            width: parent.width
                            tokens: view.tokens
                            role: "meta"
                            wrapMode: Text.Wrap
                            text: card.modelData.state === "captured"
                                ? "Captured · sha256 " + String(card.modelData.sha256).slice(0, 16)
                                    + "… · " + view.runtimeWord(card.modelData.runtime)
                                    + ". Import it with the commands the seal printed, then release it."
                                : "Candidate · " + view.runtimeWord(card.modelData.runtime)
                            color: card.modelData.runtime === "missing"
                                ? view.theme.semanticStatusColor("warn")
                                : view.theme.textSecondary
                        }

                        Row {
                            spacing: view.tokens.spaceSm

                            Repeater {
                                model: view.actionsFor(card.modelData)

                                ShellControl {
                                    id: control

                                    required property var modelData

                                    objectName: "workbench-" + control.modelData.verb
                                        + "-" + card.modelData.domain
                                    tokens: view.tokens
                                    theme: view.theme
                                    enabled: control.modelData.enabled
                                    busy: view.machineActions.busyFor(card.modelData.domain)
                                    disabledReason: control.modelData.reason
                                    accessibleName: control.modelData.label + " " + card.modelData.domain

                                    content: [
                                        ShellLabel {
                                            anchors.verticalCenter: parent.verticalCenter
                                            tokens: view.tokens
                                            role: "body"
                                            text: control.modelData.label
                                            color: view.theme.textPrimary
                                        }
                                    ]

                                    onActivated: {
                                        view.machineActions.invoke(
                                            control.modelData.verb,
                                            card.modelData.domain
                                        );
                                    }
                                }
                            }
                        }
                    }
                }
            }

            ShellCard {
                width: parent.width
                visible: view.machineActions.workbenchErrors.length > 0
                tokens: view.tokens
                theme: view.theme

                Column {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: view.tokens.spaceXs

                    Repeater {
                        model: view.machineActions.workbenchErrors

                        ShellLabel {
                            required property var modelData

                            width: parent.width
                            tokens: view.tokens
                            role: "meta"
                            wrapMode: Text.Wrap
                            text: "Refused registry record: " + modelData
                            color: view.theme.semanticStatusColor("warn")
                        }
                    }
                }
            }
        }
    }
}
