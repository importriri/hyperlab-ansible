// The dock: the Desks of this machine, the workspaces of the current Desk
// and the launcher. A highlight glides to the active Desk; the active
// workspace is a pill, occupied ones are lit dots.

import QtQuick

Island {
    id: dock

    required property var deskState
    required property var surfaces

    padding: 8
    implicitHeight: theme.dockHeight - 4
    enterDelay: 160
    enterFrom: Qt.point(0, 22)

    readonly property int current: deskState.currentDesk

    Row {
        spacing: 6

        Item {
            id: deskStrip

            anchors.verticalCenter: parent.verticalCenter
            width: deskRow.width
            height: 40

            Rectangle {
                id: deskGlide

                readonly property Item target:
                    dock.current >= 1 && dock.current <= deskRepeater.count
                    ? deskRepeater.itemAt(dock.current - 1) : null

                visible: target !== null
                x: target ? target.x : 0
                width: target ? target.width : 0
                height: parent.height
                radius: dock.theme.radiusSmall
                color: dock.theme.accentSoft
                border.width: 1
                border.color: dock.theme.accent

                Behavior on x { NumberAnimation { duration: dock.theme.normal; easing.type: Easing.OutCubic } }
                Behavior on width { NumberAnimation { duration: dock.theme.normal; easing.type: Easing.OutCubic } }
            }

            Row {
                id: deskRow

                Repeater {
                    id: deskRepeater

                    model: dock.deskState.model.desks

                    Item {
                        id: deskButton

                        required property var modelData
                        required property int index

                        readonly property int desk: index + 1
                        readonly property bool active: desk === dock.current
                        readonly property int windows: dock.deskState.windowsOn(desk)

                        width: deskLabel.implicitWidth + (active ? keyHint.implicitWidth + 8 : 0) + 32
                        height: 40

                        Behavior on width { NumberAnimation { duration: dock.theme.normal; easing.type: Easing.OutCubic } }

                        Rectangle {
                            anchors.fill: parent
                            radius: dock.theme.radiusSmall
                            color: hover.containsMouse && !deskButton.active ? dock.theme.highlight : "transparent"
                        }

                        Row {
                            anchors.centerIn: parent
                            spacing: 8

                            UiText {
                                id: deskLabel

                                anchors.verticalCenter: parent.verticalCenter
                                theme: dock.theme
                                text: deskButton.modelData.name
                                color: deskButton.active ? dock.theme.text : dock.theme.textSoft
                                font.weight: deskButton.active ? Font.DemiBold : Font.Normal
                            }

                            UiText {
                                id: keyHint

                                anchors.verticalCenter: parent.verticalCenter
                                visible: deskButton.active
                                theme: dock.theme
                                mono: true
                                text: "ALT+" + deskButton.desk
                                color: dock.theme.textMuted
                            }
                        }

                        // A Desk with open windows carries a small tick.
                        Rectangle {
                            visible: deskButton.windows > 0 && !deskButton.active
                            anchors.horizontalCenter: parent.horizontalCenter
                            anchors.bottom: parent.bottom
                            anchors.bottomMargin: 5
                            width: 4
                            height: 4
                            radius: 2
                            color: dock.theme.textMuted
                        }

                        MouseArea {
                            id: hover

                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: dock.deskState.goDesk(deskButton.desk)
                        }
                    }
                }
            }

            WheelHandler {
                onWheel: event => {
                    const step = event.angleDelta.y < 0 ? 1 : -1;
                    const count = dock.deskState.deskCount;
                    if (count > 0)
                        dock.deskState.goDesk((dock.current - 1 + step + count) % count + 1);
                }
            }
        }

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: 1
            height: 28
            color: dock.theme.lineStrong
        }

        Row {
            id: slotRow

            anchors.verticalCenter: parent.verticalCenter
            leftPadding: 10
            rightPadding: 10
            spacing: 4

            Repeater {
                model: dock.deskState.slotsOf(dock.current)

                Item {
                    id: slotItem

                    required property var modelData

                    width: dot.width + 8
                    height: 28

                    Rectangle {
                        id: dot

                        anchors.centerIn: parent
                        width: slotItem.modelData.active ? 22 : 6
                        height: 6
                        radius: 3
                        color: slotItem.modelData.active ? dock.theme.accent
                             : (slotItem.modelData.windows > 0 ? dock.theme.textSoft : "transparent")
                        border.width: slotItem.modelData.windows > 0 || slotItem.modelData.active ? 0 : 1
                        border.color: dock.theme.dotIdle

                        Behavior on width { NumberAnimation { duration: dock.theme.normal; easing.type: Easing.OutBack } }
                        Behavior on color { ColorAnimation { duration: dock.theme.normal } }
                    }

                    MouseArea {
                        id: slotHover

                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: dock.deskState.goSlot(slotItem.modelData.slot)
                    }

                    // Name of the slot on hover, above the dock.
                    Rectangle {
                        visible: slotHover.containsMouse
                        anchors.horizontalCenter: parent.horizontalCenter
                        anchors.bottom: parent.top
                        anchors.bottomMargin: 14
                        width: tip.implicitWidth + 16
                        height: 26
                        radius: 7
                        color: dock.theme.glassStrong
                        border.width: 1
                        border.color: dock.theme.line

                        UiText {
                            id: tip

                            anchors.centerIn: parent
                            theme: dock.theme
                            font.pixelSize: 12
                            text: slotItem.modelData.name
                        }
                    }
                }
            }
        }

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            width: 1
            height: 28
            color: dock.theme.lineStrong
        }

        Item {
            id: launcherButton

            anchors.verticalCenter: parent.verticalCenter
            width: launcherRow.implicitWidth + 28
            height: 40

            Rectangle {
                anchors.fill: parent
                radius: dock.theme.radiusSmall
                color: launcherHover.containsMouse ? dock.theme.highlight : "transparent"
            }

            Row {
                id: launcherRow

                anchors.centerIn: parent
                spacing: 8

                SearchGlyph {
                    anchors.verticalCenter: parent.verticalCenter
                    theme: dock.theme
                }

                UiText {
                    anchors.verticalCenter: parent.verticalCenter
                    theme: dock.theme
                    mono: true
                    text: "ALT+Space"
                    color: dock.theme.textMuted
                }
            }

            MouseArea {
                id: launcherHover

                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: dock.surfaces.toggleLauncher()
            }
        }
    }
}
