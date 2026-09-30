// HyperLab top rail (V447-C9.3).
//
// The rail is shell chrome: an opaque surface running edge to edge with one
// hairline beneath it. Inside the 37-unit reserve it answers three
// questions, in three bounded regions:
//
//   left    where am I          identity, compositor workspaces
//   centre  when, and on what   the clock, the focused host surface
//   right   what is the host doing   provenance, GPU, system readouts
//
// The side regions are bounded, so the clock keeps the display centre while
// there is room for it and the rail reduces in a defined order rather than
// colliding: the context elides, the date goes, the wordmark collapses to
// the mark, and workspace chips fold into a counted overflow.
//
// Presentation only. Data arrives from ShellState, actions leave through
// ShellActions, surfaces are summoned through ShellSurfaces, and no
// compositor, hypervisor or privileged call exists here.

import Quickshell
import Quickshell.Wayland
import QtQuick

PanelWindow {
    id: bar

    visible: bar.shellSurfaces.topRailVisible

    required property var tokens
    required property var theme
    required property var icons
    required property var shellState
    required property var shellActions
    required property var shellSurfaces

    property var modelData

    screen: modelData

    readonly property string outputName:
        bar.screen ? String(bar.screen.name) : ""

    // Reduction thresholds, in logical units of available rail width.
    readonly property bool wideRail: bar.width >= 1280
    readonly property bool mediumRail: bar.width >= 1000
    readonly property bool narrowRail: bar.width < 820

    anchors {
        top: true
        left: true
        right: true
    }

    implicitHeight: bar.tokens.barHeight
    exclusiveZone: bar.tokens.barHeight
    color: "transparent"

    WlrLayershell.namespace: "hyperlab-bar"

    Rectangle {
        id: barChrome

        anchors.fill: parent
        color: bar.theme.rail

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: bar.theme.hairline
        }

        // Where am I.
        Row {
            id: leftGroup

            anchors.left: parent.left
            anchors.leftMargin: bar.tokens.gapOuter - bar.tokens.spaceSm
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -1
            spacing: bar.tokens.spaceMd

            IdentityMark {
                anchors.verticalCenter: parent.verticalCenter
                tokens: bar.tokens
                theme: bar.theme
                wordmarkVisible: bar.mediumRail
                subtitleVisible: false

                onLauncherRequested: {
                    bar.shellSurfaces.toggleLauncher(bar.outputName);
                }

                onDiagnosticsRequested: {
                    bar.shellSurfaces.openWorkspace("diagnostics");
                }

                onControlCenterRequested: {
                    bar.shellSurfaces.openWorkspace("controls");
                }
            }

            ShellDivider {
                anchors.verticalCenter: parent.verticalCenter
                tokens: bar.tokens
                theme: bar.theme
            }

            WorkspaceStrip {
                anchors.verticalCenter: parent.verticalCenter
                tokens: bar.tokens
                theme: bar.theme
                payload: bar.shellState.workspacePayload
                sourceState:
                    bar.shellState.sourceState(
                        bar.shellState.workspaceSourceState,
                        bar.shellState.workspaceObservedAt
                    )
                maximumSlots: bar.wideRail ? 9 : (bar.mediumRail ? 6 : 4)

                onWorkspaceRequested: slot => {
                    bar.shellActions.invokeWorkspace(slot);
                }
            }
        }

        // Host state.
        Row {
            id: rightGroup

            anchors.right: parent.right
            anchors.rightMargin: bar.tokens.gapOuter - bar.tokens.spaceSm
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -1
            spacing: bar.tokens.spaceSm

            ProvenanceBadge {
                objectName: "provenance-badge"
                anchors.verticalCenter: parent.verticalCenter
                visible: bar.wideRail || badgeShown
                tokens: bar.tokens
                theme: bar.theme
                icons: bar.icons
                provenance: bar.shellState.focusedProvenance

                readonly property bool badgeShown:
                    bar.shellState.focusedProvenance.available === true
                    || bar.shellState.focusedProvenance.state === "unresolved"

                onDetailsRequested: {
                    bar.shellSurfaces.openWorkspacePage(
                        "diagnostics",
                        "overview"
                    );
                }
            }

            GpuBadge {
                anchors.verticalCenter: parent.verticalCenter
                tokens: bar.tokens
                theme: bar.theme
                icons: bar.icons
                payload: bar.shellState.gpuPayload
                claim: bar.shellState.trustClaim
                claimState: bar.shellState.trustClaimState
                ownership: bar.shellState.gpuOwnership
                sourceState:
                    bar.shellState.sourceState(
                        bar.shellState.gpuSourceState,
                        bar.shellState.gpuObservedAt
                    )

                onDetailsRequested: {
                    bar.shellSurfaces.openWorkspacePage(
                        "diagnostics",
                        "isolation"
                    );
                }
            }

            ShellDivider {
                anchors.verticalCenter: parent.verticalCenter
                tokens: bar.tokens
                theme: bar.theme
            }

            SystemCluster {
                anchors.verticalCenter: parent.verticalCenter
                tokens: bar.tokens
                theme: bar.theme
                icons: bar.icons
                audioPayload: bar.shellState.audioPayload
                audioLevel: bar.shellState.audioLevel
                batteryPayload: bar.shellState.batteryPayload
                batteryPresence: bar.shellState.batteryPresence
                networkPayload: bar.shellState.networkPayload
                selected: bar.shellSurfaces.systemPanelOpen

                attentionClass:
                    bar.theme.worstStatusClass(
                        bar.shellState.secondaryPayloads
                    )

                onPanelRequested: {
                    bar.shellSurfaces.toggleSystemPanel(bar.outputName);
                }

                onVolumeUpRequested: {
                    bar.shellSurfaces.showActionOsd(
                        "audio",
                        "audio-volume-up",
                        bar.shellActions.invoke("audio-volume-up"),
                        bar.outputName
                    );
                }

                onVolumeDownRequested: {
                    bar.shellSurfaces.showActionOsd(
                        "audio",
                        "audio-volume-down",
                        bar.shellActions.invoke("audio-volume-down"),
                        bar.outputName
                    );
                }
            }

            ControlEntry {
                anchors.verticalCenter: parent.verticalCenter
                tokens: bar.tokens
                theme: bar.theme
                icons: bar.icons
                selected:
                    bar.shellSurfaces.workspaceOpen
                    && bar.shellSurfaces.workspaceView === "controls"

                onActivated: {
                    bar.shellSurfaces.toggleWorkspace("controls");
                }
            }
        }

        // When, and on what. The clock holds the display centre while both
        // side regions still fit beside it; below that the rail reserves a
        // centre block instead of letting the regions overlap.
        ContextCluster {
            id: contextCluster

            readonly property real widestSide:
                Math.max(leftGroup.width, rightGroup.width)

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -1

            tokens: bar.tokens
            theme: bar.theme
            context: bar.shellState.focusedSurface
            clock: bar.shellState.clock
            dateVisible: bar.mediumRail

            centeredClock:
                parent.width / 2 - contextCluster.widestSide
                > bar.tokens.railClockGuard

            centerX:
                contextCluster.centeredClock
                ? parent.width / 2
                : Math.min(
                    parent.width - rightGroup.width - bar.tokens.spaceLg,
                    leftGroup.x + leftGroup.width + bar.tokens.spaceXl + 40
                  )

            maximumContextWidth:
                bar.narrowRail
                ? 0
                : Math.max(
                    0,
                    Math.round(contextCluster.centerX - 48)
                    - (leftGroup.x + leftGroup.width)
                    - bar.tokens.spaceHuge
                )
        }
    }
}
