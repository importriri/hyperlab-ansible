// The desktop itself, under every window: a large clock, a greeting and
// where you are. It only shows where no window covers it, so an empty
// workspace greets you and a full one stays out of the way.

import Quickshell
import Quickshell.Wayland
import QtQuick

PanelWindow {
    id: desktop

    required property var theme
    required property var deskState

    property var modelData

    screen: modelData

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }

    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    WlrLayershell.layer: WlrLayer.Bottom
    WlrLayershell.namespace: "hyperlab-workspace-desktop"
    WlrLayershell.keyboardFocus: WlrKeyboardFocus.None

    mask: Region {}

    readonly property string user: {
        const name = String(Quickshell.env("USER") || "");
        return name.length ? name.charAt(0).toUpperCase() + name.slice(1) : "";
    }

    function greeting(hour) {
        if (hour < 5)
            return "Working late";
        if (hour < 12)
            return "Good morning";
        if (hour < 18)
            return "Good afternoon";
        return "Good evening";
    }

    SystemClock {
        id: clock
        precision: SystemClock.Minutes
    }

    Column {
        id: block

        x: 72
        y: desktop.height - height - desktop.theme.dockHeight - desktop.theme.gap - 72
        spacing: 6
        opacity: 0

        Component.onCompleted: rise.start()

        ParallelAnimation {
            id: rise

            NumberAnimation {
                target: block; property: "opacity"; from: 0; to: 1
                duration: desktop.theme.slow * 2; easing.type: Easing.OutCubic
            }
            NumberAnimation {
                target: shift; property: "y"; from: 24; to: 0
                duration: desktop.theme.slow * 2; easing.type: Easing.OutCubic
            }
        }

        transform: Translate { id: shift }

        UiText {
            theme: desktop.theme
            mono: true
            font.pixelSize: 14
            font.letterSpacing: 3
            color: desktop.theme.accent
            text: (desktop.greeting(clock.date.getHours())
                   + (desktop.user.length ? ", " + desktop.user : "")).toUpperCase()
        }

        UiText {
            theme: desktop.theme
            font.pixelSize: 132
            font.weight: Font.Light
            font.letterSpacing: -4
            text: Qt.formatDateTime(clock.date, "HH:mm")
        }

        UiText {
            theme: desktop.theme
            font.pixelSize: 22
            color: desktop.theme.textSoft
            text: Qt.formatDateTime(clock.date, "dddd d MMMM")
        }

        Item { width: 1; height: 14 }

        Row {
            spacing: 12

            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: 28
                height: 2
                radius: 1
                color: desktop.theme.accent
            }

            UiText {
                anchors.verticalCenter: parent.verticalCenter
                theme: desktop.theme
                mono: true
                font.pixelSize: 13
                font.letterSpacing: 1.6
                color: desktop.theme.textMuted
                text: desktop.deskState.place.deskName
                    ? ("DESK " + desktop.deskState.place.desk + "  ·  "
                       + desktop.deskState.place.deskName.toUpperCase() + "  /  "
                       + desktop.deskState.place.label.toUpperCase())
                    : "HYPERLAB WORKSTATION"
            }
        }
    }
}
