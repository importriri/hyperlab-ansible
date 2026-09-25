// HyperLab product workspace (V447-C9.3).
//
// Machines, the Control Center and Diagnostics are one compositor-managed
// window, not a permanently mapped layer surface pretending to be an
// application. It is opened deliberately, it takes keyboard focus like any
// other window, it closes back to the quiet desktop, and the compositor
// places, tiles and stacks it with everything else the operator is running.
//
// One destination navigation frame is shared by all three views, so the
// product reads as one application rather than three panels. The single
// confirmation dialog lives here too: it belongs to the workspace, so
// leaving the workspace invalidates it.

import Quickshell
import QtQuick

FloatingWindow {
    id: workspace

    required property var tokens
    required property var theme
    required property var icons
    required property var shellState
    required property var shellActions
    required property var machineActions
    required property var shellSurfaces

    readonly property string view: workspace.shellSurfaces.workspaceView

    readonly property var destinations: [
        { "id": "machines", "label": "Machines", "glyph": workspace.icons.machines },
        { "id": "controls", "label": "Control Center", "glyph": workspace.icons.controlCenter },
        { "id": "diagnostics", "label": "Diagnostics", "glyph": workspace.icons.diagnostics }
    ]

    readonly property bool compact:
        workspace.width < workspace.tokens.breakpointMedium

    title: {
        switch (workspace.view) {
        case "controls":
            return "HyperLab · Control Center";
        case "diagnostics":
            return "HyperLab · Diagnostics";
        default:
            return "HyperLab · Machines";
        }
    }

    implicitWidth: workspace.tokens.workspaceWidth
    implicitHeight: workspace.tokens.workspaceHeight
    minimumSize: Qt.size(
        workspace.tokens.workspaceMinWidth,
        workspace.tokens.workspaceMinHeight
    )

    color: workspace.theme.workspace

    visible: workspace.shellSurfaces.workspaceOpen

    // Closing the window from the compositor is closing the workspace. The
    // coordinator stays the single authority for whether it is open.
    onVisibleChanged: {
        if (!workspace.visible && workspace.shellSurfaces.workspaceOpen)
            workspace.shellSurfaces.closeWorkspace();
    }

    // Re-requesting an open workspace brings the existing window forward
    // through the reviewed compositor route; the window is never hidden and
    // re-shown to steal focus.
    Connections {
        target: workspace.shellSurfaces

        function onWorkspaceRaiseRequested() {
            workspace.shellActions.invoke("workspace-window-focus");
        }
    }

    // Any change that could move a confirmation's target out from under it
    // invalidates the dialog rather than letting it execute against
    // something the operator is no longer looking at.
    Connections {
        target: workspace.shellState

        function onMachinesGenerationChanged() {
            workspace.shellSurfaces.invalidateConfirmation(
                workspace.shellState.machinesGeneration
            );
        }

        // A fresh answer that no longer offers the armed operation for the
        // armed target withdraws the dialog.
        function onMachineCapabilitiesChanged() {
            const record = workspace.shellSurfaces.confirmation;

            if (
                record === null
                || record.kind !== "machine"
                || workspace.shellState.machineCapabilities.machine
                    !== record.targetId
                || workspace.shellState.machineCapabilities.state === "loading"
            )
                return;

            if (
                !workspace.shellState.capabilityFor(
                    record.targetId,
                    record.actionId
                ).available
            )
                workspace.shellSurfaces.cancelConfirmation();
        }
    }

    Item {
        anchors.fill: parent
        focus: true

        Keys.onEscapePressed: {
            if (workspace.shellSurfaces.confirmation !== null)
                workspace.shellSurfaces.cancelConfirmation();
            else
                workspace.shellSurfaces.closeWorkspace();
        }

        // Everything behind the confirmation. While a dialog is open it is
        // disabled as a whole: no background control can take focus, be
        // reached with Tab, answer Enter or accept a click.
        Item {
            id: background

            objectName: "workspace-background"
            anchors.fill: parent
            enabled: !confirmationSurface.modal

            // Destination navigation: one strip, always visible, so every
            // destination is reachable from every destination.
            Rectangle {
                id: destinationBar

                anchors.top: parent.top
                anchors.left: parent.left
                anchors.right: parent.right
                height: workspace.tokens.controlHeightLarge
                    + workspace.tokens.spaceMd * 2
                color: workspace.theme.mantle

                Row {
                    anchors.left: parent.left
                    anchors.leftMargin: workspace.tokens.spaceLg
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: workspace.tokens.spaceMd

                    IsolationGlyph {
                        anchors.verticalCenter: parent.verticalCenter
                        size: workspace.tokens.brandMark
                        stroke: workspace.theme.textSecondary
                        core: workspace.theme.textSecondary
                    }

                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: workspace.tokens.spaceXs

                        Repeater {
                            model: workspace.destinations

                            delegate: ShellControl {
                                required property var modelData

                                height: workspace.tokens.controlHeightLarge
                                tokens: workspace.tokens
                                theme: workspace.theme
                                flat: true
                                selected: modelData.id === workspace.view
                                accessibleName: modelData.label

                                content: [
                                    ShellIcon {
                                        anchors.verticalCenter: parent.verticalCenter
                                        tokens: workspace.tokens
                                        text: modelData.glyph
                                        color:
                                            modelData.id === workspace.view
                                            ? workspace.theme.textPrimary
                                            : workspace.theme.textSecondary
                                    },

                                    ShellLabel {
                                        anchors.verticalCenter: parent.verticalCenter
                                        visible: !workspace.compact
                                        tokens: workspace.tokens
                                        role: "body"
                                        text: modelData.label
                                        color:
                                            modelData.id === workspace.view
                                            ? workspace.theme.textPrimary
                                            : workspace.theme.textSecondary
                                    }
                                ]

                                onActivated:
                                    workspace.shellSurfaces.switchWorkspace(
                                        modelData.id
                                    )
                            }
                        }
                    }
                }

                ShellControl {
                    anchors.right: parent.right
                    anchors.rightMargin: workspace.tokens.spaceLg
                    anchors.verticalCenter: parent.verticalCenter

                    height: workspace.tokens.controlHeightLarge
                    tokens: workspace.tokens
                    theme: workspace.theme
                    flat: true
                    accessibleName: "Close workspace"

                    content: [
                        ShellIcon {
                            anchors.verticalCenter: parent.verticalCenter
                            tokens: workspace.tokens
                            text: workspace.icons.close
                            color: workspace.theme.textSecondary
                        }
                    ]

                    onActivated: workspace.shellSurfaces.closeWorkspace()
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 1
                    color: workspace.theme.hairline
                }
            }

            Item {
                id: viewHost

                anchors.top: destinationBar.bottom
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom

                MachineStage {
                    anchors.fill: parent
                    visible: workspace.view === "machines"

                    tokens: workspace.tokens
                    theme: workspace.theme
                    icons: workspace.icons
                    shellState: workspace.shellState
                    machineActions: workspace.machineActions
                    shellSurfaces: workspace.shellSurfaces
                }

                ControlCenterView {
                    anchors.fill: parent
                    visible: workspace.view === "controls"

                    tokens: workspace.tokens
                    theme: workspace.theme
                    icons: workspace.icons
                    shellState: workspace.shellState
                    shellActions: workspace.shellActions
                    shellSurfaces: workspace.shellSurfaces
                }

                DiagnosticsView {
                    anchors.fill: parent
                    visible: workspace.view === "diagnostics"

                    tokens: workspace.tokens
                    theme: workspace.theme
                    icons: workspace.icons
                    shellState: workspace.shellState
                    shellSurfaces: workspace.shellSurfaces
                }
            }
        }

        ConfirmationSurface {
            id: confirmationSurface

            anchors.fill: parent

            tokens: workspace.tokens
            theme: workspace.theme
            shellSurfaces: workspace.shellSurfaces

            // The captured record is what executes. Routing is the only thing
            // this layer adds, and it adds nothing to the record.
            onConfirmed: record => {
                if (record.kind === "machine") {
                    // Revalidate the captured target, never a new selection:
                    // a machine that is no longer in the inventory is refused
                    // here, and the bridge re-checks everything again.
                    if (workspace.shellState.machineById(record.targetId) === null) {
                        workspace.shellState.recordOperation({
                            "id": "machine:" + record.targetId + ":" + record.actionId,
                            "kind": "machine",
                            "label": workspace.machineActions.labelFor(record.actionId),
                            "target": record.targetId,
                            "phase": "refused",
                            "detail": "The machine is no longer in the inventory"
                        });
                        return;
                    }

                    // A transport that cannot take it now (another power
                    // operation is in flight) is a visible refusal, not a
                    // dialog that closed and did nothing.
                    if (
                        !workspace.machineActions.invoke(
                            record.actionId,
                            record.targetId
                        )
                    ) {
                        workspace.shellState.recordOperation({
                            "id": "machine:" + record.targetId + ":" + record.actionId,
                            "kind": "machine",
                            "label": workspace.machineActions.labelFor(record.actionId),
                            "target": record.targetId,
                            "phase": "refused",
                            "detail": "Another power operation is still running"
                        });
                    }
                    return;
                }

                workspace.shellActions.invoke(record.actionId);
            }
        }
    }
}
