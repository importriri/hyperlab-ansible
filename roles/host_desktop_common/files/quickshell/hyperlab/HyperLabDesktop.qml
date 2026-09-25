// HyperLab idle desktop (V447-C9.3).
//
// The idle desktop is wallpaper, the rail, and almost nothing else. It is
// not an inventory, not a dashboard and not a permanent cockpit: rich
// content appears when an operator opens Machines, the Control Center,
// Diagnostics or the launcher, and disappears again when they close it.
//
// What survives here is a sparse identity treatment and one honest line
// about the host's own observability — if a reviewed source is not
// answering, the desktop says how many, and Diagnostics says which. No
// machine names, no provenance, no GPU caption and no fabricated state ever
// reach the wallpaper.
//
// The surface is on the bottom layer, takes no keyboard focus and has an
// empty input region, so every click reaches the compositor beneath it.

import Quickshell
import Quickshell.Wayland
import QtQuick

PanelWindow {
    id: desktop

    required property var tokens
    required property var theme
    required property var icons
    required property var shellState
    required property var shellSurfaces

    property var modelData

    screen: modelData

    readonly property int degradedCount:
        desktop.shellState.degradedSources.length

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }

    exclusiveZone: 0
    color: "transparent"

    WlrLayershell.layer: WlrLayer.Bottom
    WlrLayershell.namespace: "hyperlab-desktop"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    // The idle desktop takes no input at all. Nothing is hidden behind it.
    mask: Region {}

    Item {
        id: identityBlock

        anchors.left: parent.left
        anchors.bottom: parent.bottom
        anchors.leftMargin: desktop.tokens.spaceSection
        anchors.bottomMargin: desktop.tokens.spaceSection

        implicitWidth: identityRow.implicitWidth
        implicitHeight: identityRow.implicitHeight

        opacity: 0.62

        Row {
            id: identityRow

            spacing: desktop.tokens.spaceMd

            IsolationGlyph {
                anchors.verticalCenter: parent.verticalCenter
                size: desktop.tokens.iconProminent
                stroke: desktop.theme.textPrimary
                core: desktop.theme.textPrimary
            }

            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 0

                ShellLabel {
                    tokens: desktop.tokens
                    role: "section"
                    text: "HyperLab"
                    color: desktop.theme.textPrimary
                }

                ShellLabel {
                    tokens: desktop.tokens
                    role: "label"
                    text: "Platform"
                    color: desktop.theme.textSecondary
                }
            }
        }
    }

    // One restrained line, and only when the host is not answering. It names
    // no machine and claims no state; Diagnostics carries the detail.
    Row {
        anchors.left: identityBlock.left
        anchors.bottom: identityBlock.top
        anchors.bottomMargin: desktop.tokens.spaceLg

        visible: desktop.degradedCount > 0
        spacing: desktop.tokens.spaceSm
        opacity: 0.72

        ShellIcon {
            anchors.verticalCenter: parent.verticalCenter
            tokens: desktop.tokens
            text: desktop.icons.warning
            color: desktop.theme.semanticStatusColor("warn")
        }

        ShellLabel {
            anchors.verticalCenter: parent.verticalCenter
            tokens: desktop.tokens
            role: "meta"
            text:
                desktop.degradedCount === 1
                ? "1 host source is not reporting · open Diagnostics"
                : desktop.degradedCount
                    + " host sources are not reporting · open Diagnostics"
            color: desktop.theme.textSecondary
        }
    }
}
