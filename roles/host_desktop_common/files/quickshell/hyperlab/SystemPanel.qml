// HyperLab quick system panel (V447-C9.3).
//
// The rail's system cluster opens this panel under its trigger, on the
// output that asked for it, and only one output shows it at a time. It is
// the same design system as the Control Center — the same rows, the same
// card, the same heights — because it is the same product, not a second one.
//
// It carries quick adjustments only. Anything that configures the host
// belongs in the Control Center, and the footer links there rather than
// growing a second settings surface.
//
// Focused-window fullscreen and opacity are shown as the compositor
// shortcuts they are, not as buttons. A button here would act on whatever
// the compositor reports as focused when the queued action finally runs,
// which may no longer be the window the operator meant -- including the
// HyperLab workspace itself. Until a target-bound operation is reviewed, the
// shortcut is the only honest route.
//
// Presentation only: values from ShellState, actions through ShellActions.

import Quickshell
import Quickshell.Wayland
import QtQuick

PanelWindow {
    id: panel

    required property var tokens
    required property var theme
    required property var icons
    required property var shellState
    required property var shellActions
    required property var shellSurfaces

    property var modelData

    screen: modelData

    readonly property string outputName:
        panel.screen ? String(panel.screen.name) : ""

    readonly property bool open:
        panel.shellSurfaces.systemPanelOpen
        && panel.shellSurfaces.ownsTransient("panel", panel.outputName)

    visible: panel.open

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }

    exclusiveZone: 0
    color: "transparent"

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "hyperlab-panel"
    WlrLayershell.keyboardFocus:
        panel.open ? WlrKeyboardFocus.OnDemand : WlrKeyboardFocus.None

    // Click outside closes.
    TapHandler {
        onTapped: panel.shellSurfaces.closeSystemPanel()
    }

    Item {
        anchors.fill: parent
        focus: panel.open

        Keys.onEscapePressed: panel.shellSurfaces.closeSystemPanel()
    }

    Rectangle {
        id: card

        anchors.top: parent.top
        anchors.right: parent.right
        anchors.topMargin: panel.tokens.barHeight + panel.tokens.spaceSm
        anchors.rightMargin:
            panel.tokens.gapOuter
            + panel.tokens.controlHeight
            + panel.tokens.spaceMd

        width: Math.min(
            panel.tokens.panelWidth,
            parent.width - panel.tokens.spaceHuge
        )

        // The panel never runs off a short output: it scrolls instead.
        height: Math.min(
            column.implicitHeight + panel.tokens.panelPadding * 2,
            parent.height - panel.tokens.barHeight - panel.tokens.spaceHuge
        )

        radius: panel.tokens.radiusSurface
        color: panel.theme.floating
        border.width: panel.tokens.borderSize
        border.color: panel.theme.boundary
        clip: true

        opacity: panel.open ? 1 : 0

        Accessible.role: Accessible.Dialog
        Accessible.name: "System"

        Behavior on opacity {
            NumberAnimation {
                duration:
                    panel.open
                    ? panel.tokens.motionEnter
                    : panel.tokens.motionExit
                easing.type: Easing.OutCubic
            }
        }

        // The card swallows its own taps so the outside handler does not.
        TapHandler {
            onTapped: {}
        }

        FocusFollow {
            flickable: panelViewport
        }

        Flickable {
            id: panelViewport

            anchors.fill: parent
            contentWidth: width
            contentHeight: column.implicitHeight + panel.tokens.panelPadding * 2
            interactive: contentHeight > height
            boundsBehavior: Flickable.StopAtBounds
            clip: true

            Column {
                id: column

                x: panel.tokens.panelPadding
                y: panel.tokens.panelPadding
                width: card.width - panel.tokens.panelPadding * 2
                spacing: panel.tokens.spaceSm

                ShellLabel {
                    tokens: panel.tokens
                    role: "heading"
                    text: "System"
                    color: panel.theme.textPrimary

                    Accessible.role: Accessible.Heading
                }

                SectionHeader {
                    width: parent.width
                    tokens: panel.tokens
                    theme: panel.theme
                    label: "Host"
                }

                PanelRow {
                    width: parent.width
                    tokens: panel.tokens
                    theme: panel.theme
                    glyph: panel.icons.networkGlyph(
                        panel.shellState.networkPayload
                    )
                    title: "Network"
                    value: String(panel.shellState.networkPayload.text)
                    valueColor:
                        panel.theme.telemetryTextColor(
                            panel.shellState.networkPayload
                        )
                    hint:
                        String(panel.shellState.networkPayload.detail).length > 0
                        ? String(panel.shellState.networkPayload.detail)
                        : String(panel.shellState.networkPayload.tooltip)
                }

                PanelRow {
                    width: parent.width
                    tokens: panel.tokens
                    theme: panel.theme
                    glyph: panel.icons.audioGlyph(panel.shellState.audioLevel)
                    title: "Audio"
                    value:
                        panel.shellState.audioLevel.known === true
                        ? (
                            panel.shellState.audioLevel.muted === true
                            ? "Muted"
                            : panel.shellState.audioLevel.percent + "%"
                          )
                        : "Unavailable"
                    valueColor:
                        panel.theme.telemetryTextColor(
                            panel.shellState.audioPayload
                        )
                    hint: "default sink"
                }

                // Reviewed audio controls.
                Row {
                    anchors.right: parent.right
                    spacing: panel.tokens.spaceSm

                    ShellControl {
                        tokens: panel.tokens
                        theme: panel.theme
                        height: panel.tokens.controlHeightLarge
                        enabled: panel.shellState.audioLevel.known === true
                        disabledReason: "Audio is unavailable"
                        accessibleName: "Mute or unmute"

                        content: [
                            ShellLabel {
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: panel.tokens
                                role: "body"
                                text: "Mute"
                                color: panel.theme.textPrimary
                            }
                        ]

                        onActivated: {
                            panel.shellSurfaces.showActionOsd(
                                "audio",
                                "audio-mute-toggle",
                                panel.shellActions.invoke("audio-mute-toggle"),
                                panel.outputName
                            );
                        }
                    }

                    ShellControl {
                        tokens: panel.tokens
                        theme: panel.theme
                        height: panel.tokens.controlHeightLarge
                        enabled: panel.shellState.audioLevel.known === true
                        disabledReason: "Audio is unavailable"
                        accessibleName: "Volume down five percent"

                        content: [
                            ShellLabel {
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: panel.tokens
                                role: "body"
                                text: "−5"
                                color: panel.theme.textPrimary
                            }
                        ]

                        onActivated: {
                            panel.shellSurfaces.showActionOsd(
                                "audio",
                                "audio-volume-down",
                                panel.shellActions.invoke("audio-volume-down"),
                                panel.outputName
                            );
                        }
                    }

                    ShellControl {
                        tokens: panel.tokens
                        theme: panel.theme
                        height: panel.tokens.controlHeightLarge
                        enabled: panel.shellState.audioLevel.known === true
                        disabledReason: "Audio is unavailable"
                        accessibleName: "Volume up five percent"

                        content: [
                            ShellLabel {
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: panel.tokens
                                role: "body"
                                text: "+5"
                                color: panel.theme.textPrimary
                            }
                        ]

                        onActivated: {
                            panel.shellSurfaces.showActionOsd(
                                "audio",
                                "audio-volume-up",
                                panel.shellActions.invoke("audio-volume-up"),
                                panel.outputName
                            );
                        }
                    }
                }

                // A host with no battery shows no battery row; a battery the
                // host cannot read stays visible and says so.
                PanelRow {
                    width: parent.width
                    visible:
                        !(panel.shellState.batteryPresence.known === true
                          && panel.shellState.batteryPresence.present === false)
                    tokens: panel.tokens
                    theme: panel.theme
                    glyph: panel.icons.battery
                    title: "Battery"
                    value: String(panel.shellState.batteryPayload.text)
                    valueColor:
                        panel.theme.telemetryTextColor(
                            panel.shellState.batteryPayload
                        )
                    hint: String(panel.shellState.batteryPayload.detail)
                }

                PanelRow {
                    width: parent.width
                    tokens: panel.tokens
                    theme: panel.theme
                    glyph: panel.icons.temperature
                    title: "Temperature"
                    value: String(panel.shellState.temperaturePayload.text)
                    valueColor:
                        panel.theme.telemetryTextColor(
                            panel.shellState.temperaturePayload
                        )
                    hint: String(panel.shellState.temperaturePayload.detail)
                }

                ShellDivider {
                    width: parent.width
                    vertical: false
                    tokens: panel.tokens
                    theme: panel.theme
                }

                SectionHeader {
                    width: parent.width
                    tokens: panel.tokens
                    theme: panel.theme
                    label: "Session"
                }

                PanelRow {
                    width: parent.width
                    tokens: panel.tokens
                    theme: panel.theme
                    glyph: panel.icons.keyboard
                    title: "Keyboard"
                    value: panel.shellState.keyboardName()
                    hint: "cycle"
                    interactive: true
                    busy: panel.shellActions.busy
                    onActivated: {
                        panel.shellSurfaces.showActionOsd(
                            "keyboard",
                            "keyboard-cycle",
                            panel.shellActions.invoke("keyboard-cycle"),
                            panel.outputName
                        );
                    }
                }

                PanelRow {
                    width: parent.width
                    tokens: panel.tokens
                    theme: panel.theme
                    glyph: panel.icons.theme
                    title: "Theme"
                    value: panel.shellState.themeLabel()
                    hint: "cycle"
                    interactive: true
                    busy: panel.shellActions.busy
                    onActivated: {
                        panel.shellSurfaces.showActionOsd(
                            "theme",
                            "theme-cycle",
                            panel.shellActions.invoke("theme-cycle"),
                            panel.outputName
                        );
                    }
                }

                PanelRow {
                    width: parent.width
                    tokens: panel.tokens
                    theme: panel.theme
                    glyph: panel.icons.wallpaper
                    title: "Wallpaper"
                    value: panel.shellState.wallpaperLabel()
                    hint:
                        panel.shellState.themeState.known
                        && panel.shellState.themeState.value === "trust-model"
                        ? "next"
                        : "public · personal · HyperLab"
                    interactive: true
                    busy: panel.shellActions.busy
                    onActivated: {
                        panel.shellSurfaces.showActionOsd(
                            "wallpaper",
                            "wallpaper-mode-toggle",
                            panel.shellActions.invoke("wallpaper-mode-toggle"),
                            panel.outputName
                        );
                    }
                }

                ShellDivider {
                    width: parent.width
                    vertical: false
                    tokens: panel.tokens
                    theme: panel.theme
                }

                SectionHeader {
                    width: parent.width
                    tokens: panel.tokens
                    theme: panel.theme
                    label: "Focused window"
                    description: "Shortcuts act on the window that has focus."
                }

                PanelRow {
                    width: parent.width
                    tokens: panel.tokens
                    theme: panel.theme
                    glyph: panel.icons.machines
                    title: "Fullscreen"
                    value: "SUPER + F"
                    hint: "shortcut"
                }

                PanelRow {
                    width: parent.width
                    tokens: panel.tokens
                    theme: panel.theme
                    glyph: panel.icons.machines
                    title: "Opacity"
                    value: "SUPER + O"
                    hint: "shortcut"
                }

                ShellDivider {
                    width: parent.width
                    vertical: false
                    tokens: panel.tokens
                    theme: panel.theme
                }

                Row {
                    anchors.right: parent.right
                    spacing: panel.tokens.spaceSm

                    ShellControl {
                        tokens: panel.tokens
                        theme: panel.theme
                        height: panel.tokens.controlHeightLarge
                        accessibleName: "Lock the screen"

                        content: [
                            ShellIcon {
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: panel.tokens
                                text: panel.icons.power
                                color: panel.theme.textSecondary
                            },

                            ShellLabel {
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: panel.tokens
                                role: "body"
                                text: "Lock"
                                color: panel.theme.textPrimary
                            }
                        ]

                        onActivated: {
                            panel.shellSurfaces.closeSystemPanel();
                            panel.shellActions.invoke("session-lock");
                        }
                    }

                    ShellControl {
                        tokens: panel.tokens
                        theme: panel.theme
                        height: panel.tokens.controlHeightLarge
                        accessibleName: "Open the Control Center"

                        content: [
                            ShellLabel {
                                anchors.verticalCenter: parent.verticalCenter
                                tokens: panel.tokens
                                role: "body"
                                text: "Open Control Center"
                                color: panel.theme.textPrimary
                            }
                        ]

                        onActivated: {
                            panel.shellSurfaces.closeSystemPanel();
                            panel.shellSurfaces.openWorkspacePage(
                                "controls",
                                "session"
                            );
                        }
                    }
                }
            }
        }
    }
}
