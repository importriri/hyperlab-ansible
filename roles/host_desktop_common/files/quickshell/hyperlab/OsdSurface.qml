// HyperLab on-screen display (V447-C9.3).
//
// One OSD geometry for the whole shell, 320x72, bottom-centred above the
// screen edge: one icon, one labelled value, one neutral track. Audio after
// a volume or mute action, the keyboard layout, theme or wallpaper mode
// after a cycle.
//
// The card reads the host's own structured state — the audio level as a
// number, never a percentage parsed back out of display text — so it cannot
// claim a change that did not happen. An unknown level has no fill, and a
// failed action is shown as a failure rather than as the previous value
// wearing a success. While the action it reports on is still in flight the
// card says so; the hold starts when that action's own result arrives.
//
// It appears on the output that asked for it, on the overlay layer, with an
// empty input region: the OSD never blocks a click and never takes focus.

import Quickshell
import Quickshell.Wayland
import QtQuick

PanelWindow {
    id: osd

    required property var tokens
    required property var theme
    required property var icons
    required property var shellState
    required property var shellSurfaces

    property var modelData

    screen: modelData

    readonly property string outputName:
        osd.screen ? String(osd.screen.name) : ""

    readonly property bool owns:
        osd.shellSurfaces.ownsTransient("osd", osd.outputName)

    readonly property string kind: osd.shellSurfaces.osdKind
    property bool shown: false

    readonly property string failure:
        osd.shown ? String(osd.shellSurfaces.osdFailure) : ""

    readonly property bool pending:
        osd.shown && osd.shellSurfaces.osdPending === true

    readonly property var level: osd.shellState.audioLevel

    readonly property bool audioKnown:
        osd.kind === "audio" && osd.level.known === true

    readonly property string glyph: {
        switch (osd.kind) {
        case "audio":
            return osd.icons.audioGlyph(osd.level);
        case "keyboard":
            return osd.icons.keyboard;
        case "wallpaper":
            return osd.icons.wallpaper;
        default:
            return osd.icons.theme;
        }
    }

    readonly property string label: {
        switch (osd.kind) {
        case "audio":
            return "Audio";
        case "keyboard":
            return "Keyboard";
        case "wallpaper":
            return "Wallpaper";
        default:
            return "Theme";
        }
    }

    readonly property string value: {
        if (osd.failure.length > 0)
            return "Failed";

        if (osd.pending)
            return "Applying…";

        switch (osd.kind) {
        case "audio":
            if (!osd.audioKnown)
                return "Unavailable";

            return osd.level.muted === true
                ? "Muted"
                : osd.level.percent + "%";
        case "keyboard":
            return osd.shellState.keyboardName();
        case "wallpaper":
            return osd.shellState.wallpaperLabel();
        default:
            return osd.shellState.themeLabel();
        }
    }

    readonly property bool hasProgress:
        osd.failure.length === 0
        && !osd.pending
        && osd.audioKnown
        && osd.level.muted !== true

    // A repeated request restarts the hold rather than queueing another card.
    Connections {
        target: osd.shellSurfaces

        function onOsdSerialChanged() {
            if (!osd.owns) {
                osd.shown = false;
                return;
            }

            osd.shown = true;

            if (osd.shellSurfaces.osdPending) {
                holdTimer.stop();
                pendingLimit.restart();
            } else {
                holdTimer.restart();
            }
        }

        // The action's own result: show it, even if the card had already
        // gone, and hold it long enough to be read.
        function onOsdSettledSerialChanged() {
            if (!osd.owns)
                return;

            pendingLimit.stop();
            osd.shown = true;
            holdTimer.restart();
        }
    }

    Timer {
        id: holdTimer
        interval:
            osd.failure.length > 0
            ? osd.tokens.osdHoldMs * 2
            : osd.tokens.osdHoldMs
        repeat: false

        onTriggered: osd.shown = false
    }

    // A bridge that never answers must not pin the card on screen; the
    // outcome is still recorded in Diagnostics when it eventually arrives.
    Timer {
        id: pendingLimit
        interval: osd.tokens.osdHoldMs * 5
        repeat: false

        onTriggered: osd.shown = false
    }

    visible: osd.owns && (osd.shown || card.opacity > 0)

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }

    exclusiveZone: 0
    color: "transparent"

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "hyperlab-osd"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    mask: Region {}

    Rectangle {
        id: card

        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: osd.tokens.osdBottom

        width: Math.min(osd.tokens.osdWidth, parent.width - osd.tokens.spaceHuge)
        height: osd.tokens.osdHeight
        radius: osd.tokens.radiusSurface
        color: osd.theme.floating
        border.width: osd.tokens.borderSize
        border.color:
            osd.failure.length > 0
            ? osd.theme.semanticStatusColor("bad")
            : osd.theme.boundary

        opacity: osd.shown ? 1 : 0

        Accessible.role: Accessible.StaticText
        Accessible.name: osd.label + " " + osd.value

        transform: Translate {
            y: osd.shown ? 0 : osd.tokens.motionReveal

            Behavior on y {
                NumberAnimation {
                    duration: osd.tokens.motionOsd
                    easing.type: Easing.OutCubic
                }
            }
        }

        Behavior on opacity {
            NumberAnimation {
                duration:
                    osd.shown ? osd.tokens.motionOsd : osd.tokens.motionExit
                easing.type: Easing.OutCubic
            }
        }

        Row {
            anchors.fill: parent
            anchors.leftMargin: osd.tokens.panelPadding
            anchors.rightMargin: osd.tokens.panelPadding
            spacing: osd.tokens.spaceLg

            ShellIcon {
                anchors.verticalCenter: parent.verticalCenter
                tokens: osd.tokens
                grid: "prominent"
                text: osd.glyph
                color:
                    osd.failure.length > 0
                    ? osd.theme.semanticStatusColor("bad")
                    : osd.theme.textPrimary
            }

            Column {
                anchors.verticalCenter: parent.verticalCenter
                width:
                    parent.width
                    - osd.tokens.iconProminent
                    - osd.tokens.spaceLg
                spacing: osd.tokens.spaceSm

                Row {
                    width: parent.width
                    spacing: osd.tokens.spaceSm

                    ShellLabel {
                        anchors.verticalCenter: parent.verticalCenter
                        tokens: osd.tokens
                        role: "label"
                        text: osd.label
                        color: osd.theme.textSecondary
                    }

                    ShellLabel {
                        anchors.verticalCenter: parent.verticalCenter
                        tokens: osd.tokens
                        role: "value"
                        text: osd.value
                        color:
                            osd.failure.length > 0
                            ? osd.theme.semanticStatusColor("bad")
                            : osd.theme.textPrimary
                    }
                }

                // Neutral track with the 100% tick, because the host allows
                // 125%. An unknown level draws no fill at all.
                Item {
                    width: parent.width
                    height: 4
                    visible: osd.hasProgress

                    Rectangle {
                        anchors.fill: parent
                        radius: 2
                        color: osd.theme.fillSelected
                    }

                    Rectangle {
                        height: parent.height
                        width:
                            parent.width
                            * Math.min(osd.level.percent, osd.level.maximum)
                            / Math.max(1, osd.level.maximum)
                        radius: 2
                        color: osd.theme.textPrimary

                        Behavior on width {
                            NumberAnimation {
                                duration: osd.tokens.motionOsd
                                easing.type: Easing.OutCubic
                            }
                        }
                    }

                    Rectangle {
                        x: parent.width * 100 / Math.max(1, osd.level.maximum) - 1
                        y: -3
                        width: 1
                        height: parent.height + 6
                        color: osd.theme.boundaryStrong
                    }
                }
            }
        }
    }
}
