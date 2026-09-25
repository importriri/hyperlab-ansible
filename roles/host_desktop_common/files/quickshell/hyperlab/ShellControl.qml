// HyperLab interactive surface primitive (V447-C9.3).
//
// One container for every clickable control, and the only place activation
// semantics are written. A control is reachable by pointer and by keyboard,
// announces itself, refuses activation while disabled or busy, and carries
// one neutral visual language: a fill that rises on hover, settles on press
// and holds while selected, plus a neutral focus ring when it owns keyboard
// focus.
//
// Hierarchy comes from tone, so a control never competes with content or
// with provenance colour. `tone` is "neutral" or "danger"; danger only
// changes the boundary, never the fill, so a destructive control still reads
// as a control.
//
// Content is assigned explicitly through the content property.

import QtQuick

Rectangle {
    id: control

    required property var tokens
    required property var theme

    property bool selected: false
    property bool flat: false
    property bool busy: false
    property string tone: "neutral"
    property string accessibleName: ""
    property string disabledReason: ""

    property alias content: contentRow.data
    property alias contentSpacing: contentRow.spacing
    property alias hovered: hover.hovered
    property alias pressed: press.pressed

    readonly property bool actionable: control.enabled && !control.busy

    signal activated()

    implicitHeight: control.tokens.controlHeight

    implicitWidth:
        contentRow.implicitWidth
        + control.tokens.controlPadding * 2

    radius: control.tokens.radiusControl

    activeFocusOnTab: control.actionable

    opacity: control.enabled ? 1 : 0.55

    Accessible.role: Accessible.Button
    Accessible.name: control.accessibleName
    Accessible.description: control.enabled ? "" : control.disabledReason
    Accessible.onPressAction: control.activate()

    color:
        control.selected
        ? control.theme.fillSelected
        : (
            !control.actionable
            ? "transparent"
            : (
                press.pressed
                ? control.theme.fillPressed
                : (hover.hovered ? control.theme.fillHover : "transparent")
            )
        )

    border.width:
        control.activeFocus
        ? control.tokens.focusOutline
        : (control.flat ? 0 : control.tokens.borderSize)

    border.color:
        control.activeFocus
        ? control.theme.focusRing
        : (
            control.tone === "danger"
            ? control.theme.semanticStatusColor("warn")
            : control.theme.boundary
        )

    function activate() {
        if (!control.actionable)
            return;

        control.activated();
    }

    Behavior on color {
        ColorAnimation {
            duration: control.tokens.motionHover
        }
    }

    Row {
        id: contentRow

        anchors.centerIn: parent
        spacing: control.tokens.spaceSm
    }

    HoverHandler {
        id: hover
        enabled: control.actionable
        cursorShape:
            control.actionable
            ? Qt.PointingHandCursor
            : Qt.ArrowCursor
    }

    TapHandler {
        id: press
        enabled: control.actionable
        onTapped: control.activate()
    }

    Keys.onPressed: event => {
        if (
            event.key === Qt.Key_Return
            || event.key === Qt.Key_Enter
            || event.key === Qt.Key_Space
        ) {
            control.activate();
            event.accepted = true;
        }
    }
}
