// The keyboard sheet (ALT+H): every guest key, grouped, from keys.json, the
// same file the rofi fallback reads, so the sheet and the keys cannot drift
// apart silently.

import Quickshell
import Quickshell.Io
import Quickshell.Wayland
import QtQuick

PanelWindow {
    id: sheet

    required property var theme
    required property var surfaces

    property var modelData
    property bool primary: true

    screen: modelData

    readonly property bool open: surfaces.cheatsheetOpen && primary
    property real shown: open ? 1 : 0
    Behavior on shown { NumberAnimation { duration: sheet.theme.normal; easing.type: Easing.OutCubic } }

    property var groups: []
    property string loadError: ""

    visible: shown > 0.001

    anchors {
        top: true
        bottom: true
        left: true
        right: true
    }

    exclusionMode: ExclusionMode.Ignore
    color: "transparent"

    WlrLayershell.layer: WlrLayer.Overlay
    WlrLayershell.namespace: "hyperlab-workspace-cheatsheet"
    WlrLayershell.keyboardFocus: open ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    onOpenChanged: {
        if (open)
            keys.forceActiveFocus();
    }

    function apply(text) {
        try {
            const data = JSON.parse(String(text));
            if (!data || !Array.isArray(data.groups))
                throw new Error("no groups");
            sheet.groups = data.groups;
            sheet.loadError = "";
        } catch (error) {
            sheet.loadError = "The key list could not be read.";
        }
    }

    FileView {
        path: Qt.resolvedUrl("keys.json").toString().replace("file://", "")
        printErrors: false

        onTextChanged: sheet.apply(this.text())
        onLoadFailed: error => sheet.loadError = "The key list could not be read."
    }

    Rectangle {
        anchors.fill: parent
        color: sheet.theme.scrimDeep
        opacity: sheet.shown

        TapHandler { onTapped: sheet.surfaces.closeAll() }
    }

    FocusScope {
        id: keys

        anchors.fill: parent

        Keys.onPressed: event => {
            if (event.key === Qt.Key_Escape || event.key === Qt.Key_H) {
                sheet.surfaces.closeAll();
                event.accepted = true;
            }
        }

        Column {
            id: page

            anchors.horizontalCenter: parent.horizontalCenter
            y: Math.round(sheet.height * 0.08) + (1 - sheet.shown) * 20
            width: Math.min(sheet.width - 96, 1400)
            opacity: sheet.shown
            spacing: 28

            Item {
                width: parent.width
                height: heading.height

                Column {
                    id: heading

                    spacing: 8

                    UiText {
                        theme: sheet.theme
                        mono: true
                        text: "KEYS · THIS MACHINE"
                        color: sheet.theme.textMuted
                        font.pixelSize: 13
                        font.letterSpacing: 2
                    }

                    UiText {
                        theme: sheet.theme
                        text: "Everything here starts with ALT"
                        font.pixelSize: 36
                        font.weight: Font.DemiBold
                    }
                }

                UiText {
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    theme: sheet.theme
                    mono: true
                    font.pixelSize: 13
                    color: sheet.theme.textMuted
                    text: "Esc or ALT+H close"
                }
            }

            UiText {
                visible: sheet.loadError.length > 0
                theme: sheet.theme
                color: sheet.theme.urgent
                text: sheet.loadError
            }

            Flow {
                id: flow

                width: parent.width
                spacing: 20

                Repeater {
                    model: sheet.groups

                    Rectangle {
                        id: card

                        required property var modelData
                        required property int index

                        width: (flow.width - flow.spacing * 2) / 3
                        height: list.implicitHeight + 40
                        radius: 16
                        color: sheet.theme.glassStrong
                        border.width: 1
                        border.color: index === 0 ? sheet.theme.accent : sheet.theme.line
                        opacity: Math.max(0, Math.min(1, sheet.shown * 1.6 - index * 0.1))

                        Column {
                            id: list

                            x: 20
                            y: 20
                            width: parent.width - 40
                            spacing: 10

                            UiText {
                                theme: sheet.theme
                                mono: true
                                font.pixelSize: 12
                                font.letterSpacing: 1.6
                                color: sheet.theme.accent
                                text: String(card.modelData.title).toUpperCase()
                            }

                            Repeater {
                                model: card.modelData.keys

                                Item {
                                    required property var modelData

                                    width: list.width
                                    height: 30

                                    KeyHint {
                                        id: chord

                                        anchors.verticalCenter: parent.verticalCenter
                                        theme: sheet.theme
                                        keys: parent.modelData.keys
                                    }

                                    UiText {
                                        anchors.left: chord.right
                                        anchors.leftMargin: 12
                                        anchors.right: parent.right
                                        anchors.verticalCenter: parent.verticalCenter
                                        theme: sheet.theme
                                        font.pixelSize: 14
                                        color: sheet.theme.textSoft
                                        text: parent.modelData.does
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}
