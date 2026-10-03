// The Desks overview (ALT+D): every Desk of this machine as a card with its
// projects, where you choose where to work next.
//
// Keyboard: 1-9 go to a Desk, arrows move, Enter opens, N adds a project to
// the selected Desk, Esc closes. A Desk is organisation, not isolation, and
// the overview says so in its own words.

import Quickshell
import Quickshell.Wayland
import QtQuick

PanelWindow {
    id: overview

    required property var theme
    required property var deskState
    required property var surfaces

    property var modelData
    property bool primary: true

    screen: modelData

    readonly property bool open: surfaces.overviewOpen && primary
    property real shown: open ? 1 : 0
    Behavior on shown { NumberAnimation { duration: overview.theme.normal; easing.type: Easing.OutCubic } }

    // Selection: a Desk, and a row inside it (-1 = the Desk itself).
    property int selectedDesk: 1
    property int selectedRow: -1
    property bool creating: false

    readonly property var desks: deskState.model.desks

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
    WlrLayershell.namespace: "hyperlab-workspace-overview"
    WlrLayershell.keyboardFocus: open ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    onOpenChanged: {
        if (open) {
            selectedDesk = Math.max(1, deskState.currentDesk);
            selectedRow = -1;
            creating = false;
            keyScope.forceActiveFocus();
        }
    }

    Connections {
        target: overview.surfaces
        function onNewProjectSerialChanged() {
            overview.selectedDesk = Math.max(1, overview.deskState.currentDesk);
            overview.startCreating();
        }
    }

    function rows(desk) {
        return deskState.rowsOf(desk);
    }

    function move(dx, dy) {
        if (creating)
            return;
        const count = desks.length;
        if (dx !== 0 && count > 0) {
            selectedDesk = (selectedDesk - 1 + dx + count) % count + 1;
            selectedRow = Math.min(selectedRow, rows(selectedDesk).length - 1);
        }
        if (dy !== 0) {
            const last = rows(selectedDesk).length - 1;
            selectedRow = Math.max(-1, Math.min(last, selectedRow + dy));
        }
    }

    function activate() {
        const list = rows(selectedDesk);
        if (selectedRow >= 0 && selectedRow < list.length)
            deskState.openProject(selectedDesk, list[selectedRow].slot);
        else
            deskState.goDesk(selectedDesk);
        surfaces.closeAll();
    }

    function startCreating() {
        const card = cardRepeater.itemAt(selectedDesk - 1);
        if (!card)
            return;
        creating = true;
        card.beginCreate();
    }

    function finishCreating(accepted, name) {
        if (accepted && String(name).trim().length)
            deskState.newProject(selectedDesk, name);
        creating = false;
        keyScope.forceActiveFocus();
    }

    // Scrim: the desktop recedes.
    Rectangle {
        anchors.fill: parent
        color: overview.theme.scrimDeep
        opacity: overview.shown

        TapHandler { onTapped: overview.surfaces.closeAll() }
    }

    FocusScope {
        id: keyScope

        anchors.fill: parent
        focus: true

        Keys.onPressed: event => {
            if (overview.creating)
                return;
            const digit = event.key - Qt.Key_0;
            if (digit >= 1 && digit <= 9 && digit <= overview.desks.length) {
                overview.deskState.goDesk(digit);
                overview.surfaces.closeAll();
            } else if (event.key === Qt.Key_Escape) {
                overview.surfaces.closeAll();
            } else if (event.key === Qt.Key_Left) {
                overview.move(-1, 0);
            } else if (event.key === Qt.Key_Right || event.key === Qt.Key_Tab) {
                overview.move(1, 0);
            } else if (event.key === Qt.Key_Up) {
                overview.move(0, -1);
            } else if (event.key === Qt.Key_Down) {
                overview.move(0, 1);
            } else if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                overview.activate();
            } else if (event.key === Qt.Key_N) {
                overview.startCreating();
            } else {
                return;
            }
            event.accepted = true;
        }

        Column {
            id: page

            x: Math.max(48, Math.round(overview.width * 0.0625))
            width: overview.width - x * 2
            y: Math.round(overview.height * 0.09) + (1 - overview.shown) * 24
            opacity: overview.shown
            spacing: 28

            Item {
                width: parent.width
                height: heading.height

                Column {
                    id: heading

                    spacing: 8

                    UiText {
                        theme: overview.theme
                        mono: true
                        text: "DESKS · THIS MACHINE"
                        color: overview.theme.textMuted
                        font.pixelSize: 13
                        font.letterSpacing: 2
                    }

                    UiText {
                        theme: overview.theme
                        text: "Where do you want to work?"
                        font.pixelSize: 40
                        font.weight: Font.DemiBold
                        font.letterSpacing: -0.4
                    }
                }

                UiText {
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    theme: overview.theme
                    mono: true
                    font.pixelSize: 13
                    color: overview.theme.textMuted
                    text: "1…" + overview.desks.length + " desk · ←→↑↓ move · Enter open · N new project · Esc close"
                }
            }

            // A refused configuration is said, not hidden.
            Rectangle {
                visible: overview.deskState.configErrors.length > 0 || overview.deskState.modelError.length > 0
                width: parent.width
                height: visible ? errorText.implicitHeight + 24 : 0
                radius: overview.theme.radiusSmall
                color: Qt.rgba(overview.theme.urgent.r, overview.theme.urgent.g, overview.theme.urgent.b, 0.12)
                border.width: 1
                border.color: overview.theme.urgent

                UiText {
                    id: errorText

                    x: 12
                    y: 12
                    width: parent.width - 24
                    theme: overview.theme
                    wrapMode: Text.Wrap
                    elide: Text.ElideNone
                    font.pixelSize: 13
                    text: overview.deskState.modelError.length
                        ? overview.deskState.modelError
                        : "Your desks.json was refused, so the default Desks are shown: "
                          + overview.deskState.configErrors[0]
                }
            }

            Row {
                id: cards

                spacing: 20

                readonly property int count: Math.max(1, overview.desks.length)
                readonly property real cardWidth:
                    Math.min(420, (page.width - spacing * (count - 1)) / count)

                Repeater {
                    id: cardRepeater

                    model: overview.desks

                    DeskCard {
                        required property var modelData
                        required property int index

                        width: cards.cardWidth
                        height: Math.max(420, Math.min(560, overview.height * 0.52))
                        theme: overview.theme
                        desk: modelData
                        deskIndex: index + 1
                        rows: overview.rows(index + 1)
                        current: index + 1 === overview.deskState.currentDesk
                        selected: index + 1 === overview.selectedDesk
                        selectedRow: index + 1 === overview.selectedDesk ? overview.selectedRow : -2
                        shown: overview.shown
                        windows: overview.deskState.windowsOn(index + 1)

                        onPicked: row => {
                            overview.selectedDesk = index + 1;
                            overview.selectedRow = row;
                            overview.activate();
                        }

                        creating: overview.creating && index + 1 === overview.selectedDesk

                        onCreateRequested: {
                            overview.selectedDesk = index + 1;
                            overview.startCreating();
                        }

                        onCreateFinished: (accepted, name) => overview.finishCreating(accepted, name)
                    }
                }
            }

            UiText {
                width: Math.min(parent.width, 900)
                theme: overview.theme
                wrapMode: Text.Wrap
                elide: Text.ElideNone
                lineHeight: 1.4
                color: overview.theme.textMuted
                text: "A Desk groups projects and their windows inside this machine. "
                    + "It is organisation, not isolation: every Desk shares the same machine, "
                    + "network and trust. Work that needs a different trust level belongs in a "
                    + "different Machine, started from the host."
            }
        }
    }
}
