// The launcher (ALT+Space): one search over applications, the projects of
// every Desk and a few machine actions. Applications open in the current
// Desk; a project opens on its own workspace. Leaving the session or
// powering the machine off asks for a second Enter.

import Quickshell
import Quickshell.Wayland
import Quickshell.Widgets
import QtQuick
import "launcher.js" as Search
import "desks.js" as Desks

PanelWindow {
    id: launcher

    required property var theme
    required property var deskState
    required property var surfaces

    property var modelData
    property bool primary: true

    screen: modelData

    readonly property bool open: surfaces.launcherOpen && primary
    property real shown: open ? 1 : 0
    Behavior on shown { NumberAnimation { duration: launcher.theme.normal; easing.type: Easing.OutCubic } }

    property string query: ""
    property int cursor: 0
    property string armed: ""

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
    WlrLayershell.namespace: "hyperlab-workspace-launcher"
    WlrLayershell.keyboardFocus: open ? WlrKeyboardFocus.Exclusive : WlrKeyboardFocus.None

    onOpenChanged: {
        if (open) {
            searchField.text = "";
            launcher.cursor = 0;
            launcher.armed = "";
            searchField.forceActiveFocus();
        }
    }

    readonly property var apps: {
        const values = DesktopEntries.applications.values;
        const out = [];
        for (let i = 0; i < values.length; i++) {
            const entry = values[i];
            if (!entry || entry.noDisplay)
                continue;
            out.push({
                "kind": "app",
                "title": String(entry.name),
                "subtitle": String(entry.genericName || entry.comment || "Opens in the current Desk"),
                "keywords": (entry.keywords || []).join(" "),
                "icon": String(entry.icon || ""),
                "hint": "",
                "entry": entry
            });
        }
        return out;
    }

    readonly property var projects: {
        const out = [];
        const desks = deskState.model.desks;
        for (let d = 0; d < desks.length; d++) {
            const rows = deskState.rowsOf(d + 1);
            for (let r = 0; r < rows.length; r++) {
                out.push({
                    "kind": "project",
                    "title": rows[r].name,
                    "subtitle": desks[d].name + " · " + rows[r].meta,
                    "hint": "",
                    "desk": d + 1,
                    "slot": rows[r].slot
                });
            }
        }
        return out;
    }

    readonly property var actions: {
        const desk = Desks.deskAt(deskState.model, deskState.currentDesk);
        const q = query.trim();
        const list = [];
        if (q.length && desk) {
            list.push({
                "kind": "action", "id": "new-project", "always": true,
                "title": "New project “" + q + "” in " + desk.name,
                "subtitle": "", "hint": ""
            });
        }
        list.push({ "kind": "action", "id": "overview", "title": "Desks overview",
                    "keywords": "desk switch", "hint": "ALT+D", "always": q.length === 0 });
        list.push({ "kind": "action", "id": "lock", "title": "Lock",
                    "keywords": "lock screen away", "hint": "ALT+L" });
        list.push({ "kind": "action", "id": "theme", "title": "Next guest theme",
                    "keywords": "colour color appearance", "hint": "ALT+SHIFT+T" });
        list.push({ "kind": "action", "id": "wallpaper", "title": "Next wallpaper",
                    "keywords": "background image", "hint": "ALT+SHIFT+W" });
        list.push({ "kind": "action", "id": "logout", "title": "Log out",
                    "keywords": "exit session leave quit", "hint": "", "confirm": true });
        list.push({ "kind": "action", "id": "reboot", "title": "Restart this machine",
                    "keywords": "reboot", "hint": "", "confirm": true });
        list.push({ "kind": "action", "id": "poweroff", "title": "Power off this machine",
                    "keywords": "shutdown halt", "hint": "", "confirm": true });
        return list;
    }

    readonly property var results: Search.results(query, apps, projects, actions)

    onResultsChanged: {
        cursor = Math.max(0, Math.min(cursor, results.length - 1));
        armed = "";
    }

    function move(step) {
        if (results.length === 0)
            return;
        cursor = (cursor + step + results.length) % results.length;
        armed = "";
    }

    function activate(index) {
        const item = results[index];
        if (!item)
            return;
        if (item.confirm && armed !== item.id) {
            armed = item.id;
            return;
        }
        surfaces.closeAll();
        if (item.kind === "app") {
            item.entry.execute();
        } else if (item.kind === "project") {
            deskState.openProject(item.desk, item.slot);
        } else if (item.id === "new-project") {
            deskState.newProject(deskState.currentDesk, query);
        } else if (item.id === "overview") {
            surfaces.openOverview();
        } else {
            const commands = {
                "lock": ["loginctl", "lock-session"],
                "theme": ["privatestack-guest-theme", "next"],
                "wallpaper": ["privatestack-guest-theme", "wallpaper-next"],
                "logout": ["hyprctl", "dispatch", "exit"],
                "reboot": ["systemctl", "reboot"],
                "poweroff": ["systemctl", "poweroff"]
            };
            if (commands[item.id])
                Quickshell.execDetached(commands[item.id]);
        }
    }

    Rectangle {
        anchors.fill: parent
        color: launcher.theme.scrim
        opacity: launcher.shown * 0.8

        TapHandler { onTapped: launcher.surfaces.closeAll() }
    }

    Rectangle {
        id: panel

        anchors.horizontalCenter: parent.horizontalCenter
        y: Math.round(launcher.height * 0.18) - (1 - launcher.shown) * 16
        width: Math.min(760, launcher.width - 32)
        height: column.implicitHeight
        radius: 18
        color: launcher.theme.glassStrong
        border.width: 1
        border.color: launcher.theme.lineStrong
        opacity: launcher.shown
        scale: 0.98 + 0.02 * launcher.shown
        clip: true

        // Swallow clicks so the scrim does not close the panel under them.
        MouseArea { anchors.fill: parent }

        Column {
            id: column

            width: parent.width

            Item {
                width: parent.width
                height: 64

                SearchGlyph {
                    id: glyph

                    anchors.left: parent.left
                    anchors.leftMargin: 22
                    anchors.verticalCenter: parent.verticalCenter
                    theme: launcher.theme
                    size: 20
                    colour: launcher.theme.textMuted
                }

                TextInput {
                    id: searchField

                    anchors.left: glyph.right
                    anchors.leftMargin: 14
                    anchors.right: deskLabel.left
                    anchors.rightMargin: 14
                    anchors.verticalCenter: parent.verticalCenter
                    color: launcher.theme.text
                    selectionColor: launcher.theme.accent
                    font.family: launcher.theme.sans
                    font.pixelSize: 20
                    clip: true
                    focus: true

                    onTextChanged: launcher.query = text

                    Keys.onEscapePressed: launcher.surfaces.closeAll()
                    Keys.onDownPressed: launcher.move(1)
                    Keys.onUpPressed: launcher.move(-1)
                    Keys.onTabPressed: {
                        const next = Search.nextSection(launcher.results, launcher.cursor);
                        if (next >= 0)
                            launcher.cursor = next;
                    }
                    Keys.onReturnPressed: launcher.activate(launcher.cursor)
                    Keys.onEnterPressed: launcher.activate(launcher.cursor)

                    UiText {
                        anchors.verticalCenter: parent.verticalCenter
                        visible: searchField.text.length === 0
                        theme: launcher.theme
                        color: launcher.theme.textMuted
                        font.pixelSize: 20
                        text: "Search apps, projects and actions"
                    }
                }

                UiText {
                    id: deskLabel

                    anchors.right: parent.right
                    anchors.rightMargin: 22
                    anchors.verticalCenter: parent.verticalCenter
                    theme: launcher.theme
                    mono: true
                    color: launcher.theme.textMuted
                    text: launcher.deskState.place.deskName ? "Desk: " + launcher.deskState.place.deskName : ""
                }

                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: launcher.theme.line
                }
            }

            ListView {
                id: list

                width: parent.width
                height: Math.min(contentHeight + 20, Math.round(launcher.height * 0.5))
                topMargin: 10
                bottomMargin: 10
                leftMargin: 10
                rightMargin: 10
                clip: true
                model: launcher.results
                currentIndex: launcher.cursor
                highlightFollowsCurrentItem: false
                boundsBehavior: Flickable.StopAtBounds

                // The highlight glides between rows, skipping section titles.
                highlight: Rectangle {
                    x: 0
                    y: list.currentItem ? list.currentItem.y + list.currentItem.headerHeight : 0
                    width: list.width - 20
                    height: list.currentItem ? list.currentItem.rowHeight : 0
                    radius: 10
                    color: launcher.theme.accentSoft
                    border.width: 1
                    border.color: launcher.theme.accent

                    Behavior on y { NumberAnimation { duration: launcher.theme.fast; easing.type: Easing.OutCubic } }
                    Behavior on height { NumberAnimation { duration: launcher.theme.fast } }
                }

                delegate: Item {
                    id: resultRow

                    required property var modelData
                    required property int index

                    readonly property bool isArmed: launcher.armed.length > 0 && launcher.armed === modelData.id
                    readonly property bool opensSection:
                        index === 0 || launcher.results[index - 1].section !== modelData.section
                    readonly property real headerHeight: opensSection ? 34 : 0
                    readonly property real rowHeight: modelData.subtitle ? 58 : 48

                    width: list.width - 20
                    height: headerHeight + rowHeight

                    UiText {
                        visible: resultRow.opensSection
                        anchors.left: parent.left
                        anchors.leftMargin: 12
                        y: 10
                        theme: launcher.theme
                        mono: true
                        color: launcher.theme.textMuted
                        font.letterSpacing: 1.8
                        text: resultRow.modelData.section
                    }

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 14
                        anchors.right: hintLabel.left
                        anchors.rightMargin: 12
                        y: resultRow.headerHeight + (resultRow.rowHeight - height) / 2
                        spacing: 12

                        Item {
                            visible: resultRow.modelData.kind === "app"
                            anchors.verticalCenter: parent.verticalCenter
                            width: 28
                            height: 28

                            readonly property string iconSource:
                                resultRow.modelData.icon ? Quickshell.iconPath(resultRow.modelData.icon, true) : ""

                            IconImage {
                                anchors.fill: parent
                                visible: parent.iconSource.length > 0
                                source: parent.iconSource
                                asynchronous: true
                            }

                            Rectangle {
                                anchors.fill: parent
                                visible: parent.iconSource.length === 0
                                radius: 7
                                color: launcher.theme.accentSoft

                                UiText {
                                    anchors.centerIn: parent
                                    theme: launcher.theme
                                    font.weight: Font.DemiBold
                                    text: resultRow.modelData.title.charAt(0).toUpperCase()
                                }
                            }
                        }

                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            width: parent.width - 40

                            Text {
                                width: parent.width
                                textFormat: Text.StyledText
                                elide: Text.ElideRight
                                color: resultRow.isArmed ? launcher.theme.urgent : launcher.theme.text
                                font.family: launcher.theme.sans
                                font.pixelSize: 16
                                font.weight: Font.Medium
                                text: resultRow.isArmed
                                    ? "Press Enter again: " + Search.escapeHtml(resultRow.modelData.title.toLowerCase())
                                    : Search.marked(launcher.query, resultRow.modelData.title, launcher.theme.accent)
                            }

                            UiText {
                                visible: text.length > 0
                                width: parent.width
                                theme: launcher.theme
                                font.pixelSize: 13
                                color: launcher.theme.textMuted
                                text: resultRow.modelData.subtitle || ""
                            }
                        }
                    }

                    UiText {
                        id: hintLabel

                        anchors.right: parent.right
                        anchors.rightMargin: 14
                        y: resultRow.headerHeight + (resultRow.rowHeight - height) / 2
                        theme: launcher.theme
                        mono: true
                        color: launcher.theme.textMuted
                        text: resultRow.index === launcher.cursor ? "Enter" : (resultRow.modelData.hint || "")
                    }

                    MouseArea {
                        anchors.fill: parent
                        anchors.topMargin: resultRow.headerHeight
                        hoverEnabled: true
                        onEntered: launcher.cursor = resultRow.index
                        onClicked: launcher.activate(resultRow.index)
                    }
                }
            }

            UiText {
                visible: launcher.results.length === 0
                width: parent.width
                height: 56
                leftPadding: 24
                theme: launcher.theme
                color: launcher.theme.textMuted
                text: "Nothing matches “" + launcher.query + "”."
            }

            Rectangle {
                width: parent.width
                height: 1
                color: launcher.theme.line
            }

            Item {
                width: parent.width
                height: 42

                UiText {
                    anchors.left: parent.left
                    anchors.leftMargin: 22
                    anchors.verticalCenter: parent.verticalCenter
                    theme: launcher.theme
                    mono: true
                    color: launcher.theme.textMuted
                    text: "↑↓ move · Enter open · Tab next section"
                }

                UiText {
                    anchors.right: parent.right
                    anchors.rightMargin: 22
                    anchors.verticalCenter: parent.verticalCenter
                    theme: launcher.theme
                    mono: true
                    color: launcher.theme.textMuted
                    text: "Esc close"
                }
            }
        }
    }
}
