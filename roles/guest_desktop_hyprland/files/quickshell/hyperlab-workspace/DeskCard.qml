// One Desk in the overview: its name and key, what it is for, its projects
// with their live window counts, and a way to add a project.

import QtQuick

Item {
    id: card

    required property var theme
    required property var desk
    required property int deskIndex
    required property var rows
    property bool current: false
    property bool selected: false
    property int selectedRow: -2
    property real shown: 1
    property int windows: 0
    property bool creating: false

    signal picked(int row)
    signal createRequested()
    signal createFinished(bool accepted, string name)

    function beginCreate() {
        nameField.text = "";
        nameField.forceActiveFocus();
    }

    // Cards rise in one after another.
    opacity: Math.max(0, Math.min(1, shown * 1.6 - deskIndex * 0.12))
    transform: Translate { y: (1 - card.shown) * (28 + card.deskIndex * 16) }

    // Selection ring.
    Rectangle {
        anchors.fill: body
        anchors.margins: -5
        radius: body.radius + 5
        color: "transparent"
        border.width: 2
        border.color: card.theme.accentGlow
        opacity: card.selected && card.selectedRow === -1 ? 1 : 0

        Behavior on opacity { NumberAnimation { duration: card.theme.fast } }
    }

    Rectangle {
        id: body

        anchors.fill: parent
        radius: 16
        color: card.theme.glassStrong
        border.width: 1
        border.color: card.current ? card.theme.accent : card.theme.line

        Behavior on border.color { ColorAnimation { duration: card.theme.normal } }

        // A faint accent wash on the Desk you are in.
        Rectangle {
            anchors.fill: parent
            radius: parent.radius
            visible: card.current
            gradient: Gradient {
                GradientStop { position: 0; color: card.theme.accentSoft }
                GradientStop { position: 0.45; color: "transparent" }
            }
        }

        MouseArea {
            anchors.fill: parent
            onClicked: card.picked(-1)
        }
    }

    Column {
        id: content

        anchors.fill: parent
        anchors.margins: 24
        // Leave the add-project control its own room.
        anchors.bottomMargin: 86
        spacing: 16
        clip: true

        Item {
            width: parent.width
            height: 30

            UiText {
                anchors.left: parent.left
                anchors.right: key.left
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                theme: card.theme
                text: card.desk.name
                font.pixelSize: 22
                font.weight: Font.DemiBold
            }

            KeyHint {
                id: key

                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                theme: card.theme
                keys: "ALT+" + card.deskIndex
            }
        }

        UiText {
            width: parent.width
            theme: card.theme
            mono: true
            font.pixelSize: 12
            color: card.current ? card.theme.accent : card.theme.textMuted
            text: card.current ? "YOU ARE HERE" + (card.windows ? " · " + card.windows + " OPEN" : "")
                : (card.windows ? card.windows + (card.windows === 1 ? " WINDOW" : " WINDOWS") + " OPEN" : "QUIET")
            font.letterSpacing: 1.4
        }

        UiText {
            width: parent.width
            visible: text.length > 0
            theme: card.theme
            text: card.desk.blurb || ""
            color: card.theme.textMuted
            wrapMode: Text.Wrap
            elide: Text.ElideNone
            lineHeight: 1.35
        }

        Column {
            width: parent.width
            spacing: 8

            Repeater {
                model: card.rows

                Rectangle {
                    id: row

                    required property var modelData
                    required property int index

                    readonly property bool chosen: card.selected && card.selectedRow === index

                    width: parent.width
                    height: 44
                    radius: 9
                    color: chosen ? card.theme.accentSoft
                         : (rowHover.containsMouse ? card.theme.highlight : Qt.rgba(1, 1, 1, 0.03))
                    border.width: chosen ? 1 : 0
                    border.color: card.theme.accent

                    Behavior on color { ColorAnimation { duration: card.theme.fast } }

                    Row {
                        anchors.left: parent.left
                        anchors.leftMargin: 10
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 10

                        Rectangle {
                            anchors.verticalCenter: parent.verticalCenter
                            width: 22
                            height: 22
                            radius: 6
                            color: row.modelData.active ? card.theme.accent : "transparent"
                            border.width: 1
                            border.color: row.modelData.active ? card.theme.accent : card.theme.lineStrong

                            UiText {
                                anchors.centerIn: parent
                                theme: card.theme
                                mono: true
                                font.pixelSize: 11
                                text: row.modelData.slot
                                color: row.modelData.active ? card.theme.background : card.theme.textMuted
                            }
                        }

                        UiText {
                            anchors.verticalCenter: parent.verticalCenter
                            width: row.width - 150
                            theme: card.theme
                            font.pixelSize: 15
                            text: row.modelData.name
                        }
                    }

                    UiText {
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        theme: card.theme
                        mono: true
                        color: row.modelData.windows > 0 ? card.theme.textSoft : card.theme.textMuted
                        text: row.modelData.meta
                    }

                    MouseArea {
                        id: rowHover

                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: card.picked(row.index)
                    }
                }
            }

            UiText {
                visible: card.rows.length === 0
                width: parent.width
                theme: card.theme
                color: card.theme.textMuted
                font.pixelSize: 13
                wrapMode: Text.Wrap
                elide: Text.ElideNone
                text: "No projects yet. A project is a named workspace of this Desk with its own folder and programs."
            }
        }
    }

    // Add a project: a quiet button, or the name field while creating.
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: 20
        height: 46
        radius: card.theme.radiusSmall
        color: card.creating ? card.theme.background
             : (addHover.containsMouse ? card.theme.highlight : "transparent")
        border.width: 1
        border.color: card.creating ? card.theme.accent : card.theme.lineStrong

        UiText {
            visible: !card.creating
            anchors.left: parent.left
            anchors.leftMargin: 16
            anchors.verticalCenter: parent.verticalCenter
            theme: card.theme
            color: card.theme.textSoft
            font.weight: Font.Medium
            text: "+  New project"
        }

        KeyHint {
            visible: !card.creating && card.selected
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            theme: card.theme
            keys: "N"
        }

        MouseArea {
            id: addHover

            anchors.fill: parent
            enabled: !card.creating
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: card.createRequested()
        }

        TextInput {
            id: nameField

            visible: card.creating
            anchors.fill: parent
            anchors.leftMargin: 16
            anchors.rightMargin: 16
            verticalAlignment: TextInput.AlignVCenter
            color: card.theme.text
            selectionColor: card.theme.accent
            font.family: card.theme.sans
            font.pixelSize: 15
            maximumLength: 40
            clip: true

            Keys.onReturnPressed: card.createFinished(true, nameField.text)
            Keys.onEnterPressed: card.createFinished(true, nameField.text)
            Keys.onEscapePressed: card.createFinished(false, "")

            UiText {
                anchors.verticalCenter: parent.verticalCenter
                visible: nameField.text.length === 0
                theme: card.theme
                color: card.theme.textMuted
                text: "Project name, then Enter"
            }
        }
    }
}
