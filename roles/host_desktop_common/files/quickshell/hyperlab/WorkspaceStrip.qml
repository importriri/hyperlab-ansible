// HyperLab compositor workspace navigation (V447-C9.3).
//
// Only meaningful workspaces are visible: active, occupied or urgent. The
// compositor-neutral adapter remains the sole workspace authority, so an
// empty or unreadable snapshot presents an explicit unavailable state — the
// rail never invents a workspace 1 the compositor did not report.
//
// Activation leaves through the reviewed workspace-select operation. There
// is no compositor call in this file, and the slot is an integer the action
// layer and the bridge both re-validate.

import QtQuick

Item {
    id: strip

    required property var tokens
    required property var theme
    required property var payload
    required property string sourceState

    // Chips beyond this fold into a labelled overflow rather than pushing the
    // rest of the rail out of the way.
    property int maximumSlots: 9

    signal workspaceRequested(int slot)

    readonly property int slotWidth: strip.tokens.workspaceSlot

    readonly property bool available: strip.sourceState === "ok"

    readonly property var observedWorkspaces: {
        const result = [];

        function addWorkspace(candidate) {
            const value = Number(candidate);

            if (!Number.isInteger(value) || value < 1)
                return;

            if (result.indexOf(value) < 0)
                result.push(value);
        }

        addWorkspace(strip.payload.active);

        const occupied = strip.payload.occupied || [];
        const urgent = strip.payload.urgent || [];

        for (let index = 0; index < occupied.length; index++)
            addWorkspace(occupied[index]);

        for (let index = 0; index < urgent.length; index++)
            addWorkspace(urgent[index]);

        result.sort(function(a, b) {
            return a - b;
        });

        return result;
    }

    // When not every workspace fits, the active and urgent ones always stay
    // visible; the remaining room goes to the others in order, and the rest
    // is counted in the overflow.
    readonly property var visibleWorkspaces: {
        const limit = Math.max(1, strip.maximumSlots);
        const all = strip.observedWorkspaces;

        if (all.length <= limit)
            return all;

        const chosen = [];
        const urgent = strip.payload.urgent || [];
        const pinned = [Number(strip.payload.active)].concat(
            urgent.map(value => Number(value))
        );

        for (let index = 0; index < pinned.length && chosen.length < limit; index++) {
            if (all.indexOf(pinned[index]) >= 0 && chosen.indexOf(pinned[index]) < 0)
                chosen.push(pinned[index]);
        }

        for (let index = 0; index < all.length && chosen.length < limit; index++) {
            if (chosen.indexOf(all[index]) < 0)
                chosen.push(all[index]);
        }

        return chosen.sort(function(a, b) {
            return a - b;
        });
    }

    readonly property int overflowCount:
        Math.max(0, strip.observedWorkspaces.length - strip.maximumSlots)

    readonly property bool emptyObservation:
        strip.available && strip.observedWorkspaces.length === 0

    implicitWidth:
        strip.available
        ? (
            strip.emptyObservation
            ? unavailable.implicitWidth
            : strip.slotWidth * strip.visibleWorkspaces.length
                + (strip.overflowCount > 0 ? strip.tokens.workspaceOverflow : 0)
          )
        : unavailable.implicitWidth

    implicitHeight: strip.tokens.controlHeight

    Accessible.role: Accessible.PageTabList
    Accessible.name: "Compositor workspaces"

    // An unreadable or empty compositor observation says so. It never
    // resolves to a workspace nobody reported.
    ShellLabel {
        id: unavailable

        anchors.verticalCenter: parent.verticalCenter
        anchors.verticalCenterOffset: -1
        visible: !strip.available || strip.emptyObservation

        tokens: strip.tokens
        role: "bar"
        font.weight: Font.Normal
        text:
            strip.available
            ? "No workspaces reported"
            : "Workspaces unavailable"
        color: strip.theme.textQuiet
    }

    Rectangle {
        id: activeTab

        readonly property int activeIndex:
            strip.visibleWorkspaces.indexOf(
                Number(strip.payload.active)
            )

        visible:
            strip.available
            && !strip.emptyObservation
            && activeTab.activeIndex >= 0

        x:
            Math.max(0, activeTab.activeIndex)
            * strip.slotWidth

        width: strip.slotWidth
        height: parent.height
        radius: strip.tokens.radiusControl - 2
        color: strip.theme.fillSelected

        Behavior on x {
            NumberAnimation {
                duration: strip.tokens.motionWorkspace
                easing.type: Easing.OutCubic
            }
        }

        Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            anchors.bottom: parent.bottom

            width: parent.width - 8
            height: 2
            radius: 1
            color: strip.theme.textPrimary
        }
    }

    Row {
        anchors.fill: parent
        visible: strip.available && !strip.emptyObservation
        spacing: 0

        Repeater {
            model: strip.visibleWorkspaces

            delegate: Item {
                id: workspaceItem

                required property var modelData

                readonly property int workspaceNumber:
                    Number(workspaceItem.modelData)

                readonly property bool isActive:
                    Number(strip.payload.active)
                    === workspaceItem.workspaceNumber

                readonly property bool isOccupied:
                    (strip.payload.occupied || []).indexOf(
                        workspaceItem.workspaceNumber
                    ) >= 0

                readonly property bool isUrgent:
                    (strip.payload.urgent || []).indexOf(
                        workspaceItem.workspaceNumber
                    ) >= 0

                width: strip.slotWidth
                height: parent.height

                activeFocusOnTab: true

                Accessible.role: Accessible.PageTab
                Accessible.name: "Workspace " + workspaceItem.workspaceNumber
                Accessible.onPressAction:
                    strip.workspaceRequested(workspaceItem.workspaceNumber)

                Rectangle {
                    anchors.fill: parent
                    radius: strip.tokens.radiusControl - 2
                    color:
                        chipHover.hovered && !workspaceItem.isActive
                        ? strip.theme.fillHover
                        : "transparent"
                    border.width:
                        workspaceItem.activeFocus
                        ? strip.tokens.focusOutline
                        : 0
                    border.color: strip.theme.focusRing
                }

                ShellLabel {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.verticalCenterOffset: -1

                    tokens: strip.tokens
                    role: "mono"
                    font.pixelSize: strip.tokens.fontLabel
                    font.weight:
                        workspaceItem.isActive
                        ? Font.DemiBold
                        : Font.Medium

                    text: String(workspaceItem.workspaceNumber)

                    color:
                        workspaceItem.isUrgent
                        ? strip.theme.semanticStatusColor("warn")
                        : (
                            workspaceItem.isActive
                            || workspaceItem.isOccupied
                            ? strip.theme.textPrimary
                            : strip.theme.textQuiet
                        )

                    Behavior on color {
                        ColorAnimation {
                            duration: strip.tokens.motionHover
                        }
                    }
                }

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 3

                    visible:
                        workspaceItem.isOccupied
                        && !workspaceItem.isActive
                        && !workspaceItem.isUrgent

                    width: 3
                    height: 3
                    color: strip.theme.textSecondary
                }

                ShellLabel {
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.rightMargin: 3
                    anchors.topMargin: 1

                    visible: workspaceItem.isUrgent

                    tokens: strip.tokens
                    role: "mono"
                    font.pixelSize: strip.tokens.fontLabel - 2
                    font.weight: Font.Bold

                    text: "!"
                    color: strip.theme.semanticStatusColor("warn")
                }

                HoverHandler {
                    id: chipHover
                    cursorShape: Qt.PointingHandCursor
                }

                TapHandler {
                    onTapped:
                        strip.workspaceRequested(workspaceItem.workspaceNumber)
                }

                Keys.onPressed: event => {
                    if (
                        event.key === Qt.Key_Return
                        || event.key === Qt.Key_Enter
                        || event.key === Qt.Key_Space
                    ) {
                        strip.workspaceRequested(
                            workspaceItem.workspaceNumber
                        );
                        event.accepted = true;
                    }
                }
            }
        }

        // Bounded overflow: the count is a readout, never a hidden control.
        ShellLabel {
            anchors.verticalCenter: parent.verticalCenter
            anchors.verticalCenterOffset: -1
            visible: strip.overflowCount > 0
            width: strip.tokens.workspaceOverflow
            horizontalAlignment: Text.AlignHCenter
            tokens: strip.tokens
            role: "mono"
            font.pixelSize: strip.tokens.fontLabel
            text: "+" + strip.overflowCount
            color: strip.theme.textQuiet
        }
    }
}
