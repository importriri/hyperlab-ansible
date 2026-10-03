// On-screen notices: entering a Desk, the volume, and the outcome of a Desk
// change made through the helper. Never takes input, never takes focus.

import Quickshell
import Quickshell.Wayland
import QtQuick

PanelWindow {
    id: osd

    required property var theme
    required property var deskState
    required property var stats

    property var modelData
    property bool primary: true

    screen: modelData

    // What is showing: "desk", "volume" or "notice".
    property string kind: ""
    property string title: ""
    property string detail: ""
    property bool showing: false
    property real shown: showing ? 1 : 0
    Behavior on shown { NumberAnimation { duration: osd.theme.normal; easing.type: Easing.OutCubic } }

    property bool volumeArmed: false

    visible: primary && shown > 0.001

    anchors {
        top: true
    }

    margins.top: theme.gap * 2 + theme.islandHeight + 24
    implicitWidth: 520
    implicitHeight: 132
    exclusiveZone: 0
    color: "transparent"

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "hyperlab-workspace-osd"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    mask: Region {}

    function present(kind, title, detail, duration) {
        osd.kind = kind;
        osd.title = title;
        osd.detail = detail;
        osd.showing = true;
        hide.interval = duration;
        hide.restart();
        if (osd.theme.normal > 0) {
            sweep.restart();
            if (kind === "desk")
                spread.restart();
        }
    }

    Timer {
        id: hide

        onTriggered: osd.showing = false
    }

    // Volume changes made before the shell started are not news.
    Timer {
        interval: 1500
        running: true
        onTriggered: osd.volumeArmed = true
    }

    Connections {
        target: osd.deskState

        function onDeskEntered(desk) {
            const place = osd.deskState.placeNow();
            if (!place.deskName)
                return;
            osd.present("desk", place.deskName, "DESK " + desk + "  ·  " + place.label.toUpperCase(), 1100);
        }

        function onNoticeChanged() {
            const notice = osd.deskState.notice;
            if (notice.text.length)
                osd.present(notice.kind === "error" ? "error" : "notice", notice.text, notice.detail,
                            notice.kind === "error" ? 4200 : 1800);
        }
    }

    Connections {
        target: osd.stats

        function onVolumeChanged() { osd.showVolume(); }
        function onMutedChanged() { osd.showVolume(); }
    }

    function showVolume() {
        if (!volumeArmed || stats.volume < 0)
            return;
        present("volume", stats.muted ? "Muted" : "Volume", stats.muted ? "" : stats.volume + "%", 1100);
    }

    Rectangle {
        id: card

        anchors.horizontalCenter: parent.horizontalCenter
        y: (1 - osd.shown) * -14
        width: Math.max(360, Math.min(parent.width, content.implicitWidth + 96))
        height: content.implicitHeight + 40
        radius: 18
        opacity: osd.shown
        color: osd.theme.glassStrong
        border.width: 1
        border.color: osd.kind === "error" ? osd.theme.urgent : osd.theme.line

        Column {
            id: content

            anchors.centerIn: parent
            spacing: 8

            UiText {
                id: titleText

                anchors.horizontalCenter: parent.horizontalCenter
                theme: osd.theme
                text: osd.title
                font.pixelSize: osd.kind === "desk" ? 40 : 20
                font.weight: osd.kind === "desk" ? Font.Light : Font.DemiBold
                font.letterSpacing: 0
                color: osd.kind === "error" ? osd.theme.urgent : osd.theme.text

                // A new Desk's name settles into place from wide spacing.
                NumberAnimation on font.letterSpacing {
                    id: spread

                    running: false
                    from: 14
                    to: 0.5
                    duration: osd.theme.slow * 1.6
                    easing.type: Easing.OutCubic
                }
            }

            UiText {
                anchors.horizontalCenter: parent.horizontalCenter
                visible: osd.kind !== "volume" && text.length > 0
                width: Math.min(implicitWidth, 440)
                horizontalAlignment: Text.AlignHCenter
                theme: osd.theme
                mono: osd.kind === "desk"
                font.letterSpacing: osd.kind === "desk" ? 1.6 : 0
                color: osd.theme.textMuted
                wrapMode: Text.Wrap
                elide: Text.ElideNone
                text: osd.detail
            }

            // Volume as a bar.
            Rectangle {
                visible: osd.kind === "volume"
                anchors.horizontalCenter: parent.horizontalCenter
                width: 260
                height: 6
                radius: 3
                color: osd.theme.line

                Rectangle {
                    width: parent.width * Math.min(1, Math.max(0, osd.stats.volume) / 100)
                    height: parent.height
                    radius: 3
                    color: osd.stats.muted ? osd.theme.textMuted : osd.theme.accent

                    Behavior on width { NumberAnimation { duration: osd.theme.fast } }
                }
            }
        }

        // An accent line sweeps under a new notice.
        Rectangle {
            id: underline

            anchors.bottom: parent.bottom
            anchors.bottomMargin: 1
            anchors.horizontalCenter: parent.horizontalCenter
            height: 2
            radius: 1
            width: 0
            color: osd.kind === "error" ? osd.theme.urgent : osd.theme.accent
        }

        SequentialAnimation {
            id: sweep

            NumberAnimation {
                target: underline; property: "width"; from: 0; to: card.width * 0.6
                duration: osd.theme.slow; easing.type: Easing.OutCubic
            }
            NumberAnimation {
                target: underline; property: "opacity"; from: 1; to: 0.35
                duration: osd.theme.slow
            }
        }
    }
}
