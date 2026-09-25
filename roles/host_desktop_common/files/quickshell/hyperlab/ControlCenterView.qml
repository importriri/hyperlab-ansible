// HyperLab Control Center (V447-C9.3).
//
// The host's own settings, native, in three sections an operator can name:
// Session, Audio and network, Input and appearance. It replaces the old Rofi
// and GTK control routes entirely — nothing here opens a legacy surface —
// and it uses the same rows, cards and confirmation as the rest of the
// product.
//
// Two honesty rules shape what is here:
//
//   * a control exists only where the reviewed bridge can really perform it,
//     so nothing draws a toggle that does nothing;
//   * focused-window operations are shown as the shortcut they are, because
//     opening this window makes this window the focused one — offering them
//     here would act on the Control Center itself.
//
// Log out, reboot and power off go through the one shared confirmation, and
// the confirmation names how many machines are running when the host knows.

import QtQuick

Item {
    id: view

    required property var tokens
    required property var theme
    required property var icons
    required property var shellState
    required property var shellActions
    required property var shellSurfaces

    readonly property var sections: [
        { "id": "session", "label": "Session" },
        { "id": "audio", "label": "Audio and network" },
        { "id": "appearance", "label": "Input and appearance" }
    ]

    readonly property string section: view.shellSurfaces.subpage

    readonly property string runningSummary:
        view.shellState.machinesAvailable
        ? (
            view.shellState.machinesRunning === 1
            ? "1 machine is running."
            : view.shellState.machinesRunning + " machines are running."
          )
        : "The host could not report how many machines are running."

    function dangerTitle(action) {
        switch (String(action)) {
        case "session-logout":
            return "Log out of this session?";
        case "session-reboot":
            return "Reboot this host?";
        case "session-poweroff":
            return "Power off this host?";
        default:
            return "Run this action?";
        }
    }

    function dangerConsequence(action) {
        switch (String(action)) {
        case "session-logout":
            return "Every host application and every running machine loses "
                + "this session. " + view.runningSummary;
        case "session-reboot":
            return "The host restarts. Running machines are stopped by the "
                + "host, and the GPU boot claim is released. "
                + view.runningSummary;
        case "session-poweroff":
            return "The host powers off. Running machines are stopped by the "
                + "host. " + view.runningSummary;
        default:
            return "";
        }
    }

    function requestDanger(action) {
        view.shellSurfaces.requestConfirmation({
            "kind": "session",
            "actionId": String(action),
            "targetId": "host",
            "targetName": "This host",
            "title": view.dangerTitle(action),
            "consequence": view.dangerConsequence(action),
            "confirmLabel": view.shellActions.labelFor(action),
            "requiresName": false,
            "generation": -1
        });
    }

    WorkspaceFrame {
        id: frame

        anchors.fill: parent
        tokens: view.tokens
        theme: view.theme

        title: "Control Center"
        subtitle: "Host settings and session controls"
        sections: view.sections
        currentSection: view.section
        maxContentWidth: 1040

        onSectionRequested: identifier => {
            view.shellSurfaces.openSubpage(identifier);
        }

        Column {
            width: frame.bodyWidth
            spacing: view.tokens.spaceLg

            // ------------------------------------------------- Session

            SectionHeader {
                width: parent.width
                visible: view.section === "session"
                tokens: view.tokens
                theme: view.theme
                label: "Session"
                description: view.runningSummary
            }

            ShellCard {
                width: parent.width
                visible: view.section === "session"
                tokens: view.tokens
                theme: view.theme

                Column {
                    id: sessionRows

                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: 2

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.power
                        title: "Lock"
                        value: "Screen"
                        hint: "immediate"
                        interactive: true
                        busy: view.shellActions.busy
                        onActivated: view.shellActions.invoke("session-lock")
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.power
                        title: "Suspend"
                        value: "Host"
                        hint: "immediate"
                        interactive: true
                        busy: view.shellActions.busy
                        onActivated: view.shellActions.invoke("session-suspend")
                    }

                    ShellDivider {
                        width: parent.width
                        vertical: false
                        tokens: view.tokens
                        theme: view.theme
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.session
                        title: "Log out"
                        value: "Session"
                        hint: "confirmation required"
                        tone: "danger"
                        interactive: true
                        busy: view.shellActions.busy
                        onActivated: view.requestDanger("session-logout")
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.power
                        title: "Reboot"
                        value: "Host"
                        hint: "confirmation required"
                        tone: "danger"
                        interactive: true
                        busy: view.shellActions.busy
                        onActivated: view.requestDanger("session-reboot")
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.power
                        title: "Power off"
                        value: "Host"
                        hint: "confirmation required"
                        tone: "danger"
                        interactive: true
                        busy: view.shellActions.busy
                        onActivated: view.requestDanger("session-poweroff")
                    }
                }
            }

            ActionFeedback {
                width: parent.width
                visible: view.section === "session"
                tokens: view.tokens
                theme: view.theme
                record: view.shellState.latestOperationFor("host")
            }

            // -------------------------------------------------- Audio

            SectionHeader {
                width: parent.width
                visible: view.section === "audio"
                tokens: view.tokens
                theme: view.theme
                label: "Audio"
                description: "Default host sink"
            }

            ShellCard {
                width: parent.width
                visible: view.section === "audio"
                tokens: view.tokens
                theme: view.theme

                Column {
                    id: audioRows

                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: view.tokens.spaceSm

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.audioGlyph(view.shellState.audioLevel)
                        title: "Level"
                        value:
                            view.shellState.audioLevel.known === true
                            ? (
                                view.shellState.audioLevel.muted === true
                                ? "Muted"
                                : view.shellState.audioLevel.percent + "%"
                              )
                            : "Unavailable"
                        valueColor:
                            view.theme.telemetryTextColor(
                                view.shellState.audioPayload
                            )
                        hint: String(view.shellState.audioPayload.detail)
                    }

                    Row {
                        spacing: view.tokens.spaceSm

                        ShellControl {
                            tokens: view.tokens
                            theme: view.theme
                            enabled: view.shellState.audioLevel.known === true
                            disabledReason: "Audio is unavailable"
                            accessibleName: "Mute or unmute"

                            content: [
                                ShellLabel {
                                    anchors.verticalCenter: parent.verticalCenter
                                    tokens: view.tokens
                                    role: "body"
                                    text: "Mute"
                                    color: view.theme.textPrimary
                                }
                            ]

                            onActivated: {
                                view.shellSurfaces.showActionOsd(
                                    "audio",
                                    "audio-mute-toggle",
                                    view.shellActions.invoke("audio-mute-toggle"),
                                    ""
                                );
                            }
                        }

                        ShellControl {
                            tokens: view.tokens
                            theme: view.theme
                            enabled: view.shellState.audioLevel.known === true
                            disabledReason: "Audio is unavailable"
                            accessibleName: "Volume down five percent"

                            content: [
                                ShellLabel {
                                    anchors.verticalCenter: parent.verticalCenter
                                    tokens: view.tokens
                                    role: "body"
                                    text: "−5"
                                    color: view.theme.textPrimary
                                }
                            ]

                            onActivated: {
                                view.shellSurfaces.showActionOsd(
                                    "audio",
                                    "audio-volume-down",
                                    view.shellActions.invoke("audio-volume-down"),
                                    ""
                                );
                            }
                        }

                        ShellControl {
                            tokens: view.tokens
                            theme: view.theme
                            enabled: view.shellState.audioLevel.known === true
                            disabledReason: "Audio is unavailable"
                            accessibleName: "Volume up five percent"

                            content: [
                                ShellLabel {
                                    anchors.verticalCenter: parent.verticalCenter
                                    tokens: view.tokens
                                    role: "body"
                                    text: "+5"
                                    color: view.theme.textPrimary
                                }
                            ]

                            onActivated: {
                                view.shellSurfaces.showActionOsd(
                                    "audio",
                                    "audio-volume-up",
                                    view.shellActions.invoke("audio-volume-up"),
                                    ""
                                );
                            }
                        }
                    }
                }
            }

            SectionHeader {
                width: parent.width
                visible: view.section === "audio"
                tokens: view.tokens
                theme: view.theme
                label: "Network"
                description:
                    "Observed host connectivity. Interface configuration is "
                    + "not yet a reviewed host operation."
            }

            ShellCard {
                width: parent.width
                visible: view.section === "audio"
                tokens: view.tokens
                theme: view.theme

                Column {
                    id: networkRows

                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: 2

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.networkGlyph(
                            view.shellState.networkPayload
                        )
                        title: "Default route"
                        value: String(view.shellState.networkPayload.text)
                        valueColor:
                            view.theme.telemetryTextColor(
                                view.shellState.networkPayload
                            )
                        hint: String(view.shellState.networkPayload.detail)
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.temperature
                        title: "Temperature"
                        value: String(view.shellState.temperaturePayload.text)
                        valueColor:
                            view.theme.telemetryTextColor(
                                view.shellState.temperaturePayload
                            )
                        hint: String(view.shellState.temperaturePayload.detail)
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.battery
                        title: "Battery"
                        value: {
                            if (view.shellState.batteryPresence.known !== true)
                                return "Unavailable";

                            return view.shellState.batteryPresence.present
                                ? String(view.shellState.batteryPayload.text)
                                : "Not present";
                        }
                        valueColor:
                            view.theme.telemetryTextColor(
                                view.shellState.batteryPayload
                            )
                        hint: String(view.shellState.batteryPayload.detail)
                    }
                }
            }

            // --------------------------------------------- Appearance

            SectionHeader {
                width: parent.width
                visible: view.section === "appearance"
                tokens: view.tokens
                theme: view.theme
                label: "Input and appearance"
                description:
                    "Cycling controls are the reviewed host operations. "
                    + "Explicit selection needs a wider bridge."
            }

            ShellCard {
                width: parent.width
                visible: view.section === "appearance"
                tokens: view.tokens
                theme: view.theme

                Column {
                    id: appearanceRows

                    anchors.left: parent.left
                    anchors.right: parent.right
                    spacing: 2

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.keyboard
                        title: "Keyboard layout"
                        value: view.shellState.keyboardName()
                        hint: "cycle"
                        interactive: true
                        busy: view.shellActions.busy
                        onActivated: {
                            view.shellSurfaces.showActionOsd(
                                "keyboard",
                                "keyboard-cycle",
                                view.shellActions.invoke("keyboard-cycle"),
                                ""
                            );
                        }
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.theme
                        title: "Theme"
                        value: view.shellState.themeLabel()
                        hint: "cycle"
                        interactive: true
                        busy: view.shellActions.busy
                        onActivated: {
                            view.shellSurfaces.showActionOsd(
                                "theme",
                                "theme-cycle",
                                view.shellActions.invoke("theme-cycle"),
                                ""
                            );
                        }
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.wallpaper
                        title: "Wallpaper source"
                        value: view.shellState.wallpaperLabel()
                        hint:
                            view.shellState.themeState.known
                            && view.shellState.themeState.value === "trust-model"
                            ? "trust pool"
                            : "public · personal · HyperLab"
                        interactive: true
                        busy: view.shellActions.busy
                        onActivated: {
                            view.shellSurfaces.showActionOsd(
                                "wallpaper",
                                "wallpaper-mode-toggle",
                                view.shellActions.invoke("wallpaper-mode-toggle"),
                                ""
                            );
                        }
                    }

                    ShellDivider {
                        width: parent.width
                        vertical: false
                        tokens: view.tokens
                        theme: view.theme
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.controlCenter
                        title: "Top rail"
                        value:
                            view.shellSurfaces.topRailVisible
                            ? "Visible"
                            : "Hidden"
                        hint: "toggle"
                        interactive: true
                        onActivated: view.shellSurfaces.toggleTopRail()
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.details
                        title: "Reduced motion"
                        value:
                            view.shellState.reducedMotion
                            ? "On"
                            : "Off"
                        hint: "host setting"
                    }

                    ShellDivider {
                        width: parent.width
                        vertical: false
                        tokens: view.tokens
                        theme: view.theme
                    }

                    // Focused-window operations act on whatever the compositor
                    // reports as focused. Opening this window makes it the
                    // focused window, so they live on the compositor shortcut
                    // only, until a target-bound operation is reviewed.
                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.machines
                        title: "Focused window fullscreen"
                        value: "SUPER + F"
                        hint: "shortcut"
                    }

                    PanelRow {
                        width: parent.width
                        tokens: view.tokens
                        theme: view.theme
                        glyph: view.icons.machines
                        title: "Focused window opacity"
                        value: "SUPER + O"
                        hint: "shortcut"
                    }
                }
            }
        }
    }
}
