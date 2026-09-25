// HyperLab panel row (V447-C9.3).
//
// One 40px row shared by every panel, settings list and result list: a
// leading glyph, a title, a value in mono, and a trailing hint. Rows are the
// unit of the system panel, the Control Center sections and the launcher
// results, so every summoned surface shares edges, heights and selection
// treatment.
//
// An interactive row is a real control: it takes keyboard focus, activates on
// Return or Space, refuses activation while disabled or busy, and explains
// why it is unavailable instead of silently doing nothing.
//
// Every text has a width budget, because a Qt Row never shrinks its
// children: the title and value share the leading column and elide (the full
// text stays in the accessible name and description), the trailing hint is
// capped and elides, and a disabled reason -- which can be a full sentence
// from a bridge -- wraps on its own second line, growing the row instead of
// running under its neighbours.

import QtQuick

Rectangle {
    id: row

    required property var tokens
    required property var theme

    property string glyph: ""
    property string title: ""
    property string value: ""
    property string hint: ""
    property color valueColor: row.theme.textPrimary
    property bool interactive: false
    property bool current: false
    property bool busy: false
    property string tone: "neutral"
    property string disabledReason: ""

    readonly property bool actionable:
        row.interactive && row.enabled && !row.busy

    signal activated()

    // The reason line appears only when the row is disabled and says why.
    readonly property bool showsReason:
        !row.enabled && row.disabledReason.length > 0

    implicitHeight:
        Math.max(
            row.tokens.rowHeight,
            leading.implicitHeight + row.tokens.spaceSm * 2
        )
    radius: row.tokens.radiusControl

    activeFocusOnTab: row.actionable

    opacity: row.enabled ? 1 : 0.55

    Accessible.role: row.interactive ? Accessible.Button : Accessible.StaticText
    Accessible.name: row.title
    Accessible.description:
        row.enabled
        ? (row.value.length > 0 ? row.value : row.hint)
        : row.disabledReason
    Accessible.onPressAction: row.activate()

    color:
        row.current
        ? row.theme.fillSelected
        : (
            !row.actionable
            ? "transparent"
            : (
                press.pressed
                ? row.theme.fillPressed
                : (hover.hovered ? row.theme.fillHover : "transparent")
            )
        )

    border.width: row.activeFocus ? row.tokens.focusOutline : 0
    border.color: row.theme.focusRing

    function activate() {
        if (!row.actionable)
            return;

        row.activated();
    }

    Behavior on color {
        ColorAnimation {
            duration: row.tokens.motionHover
        }
    }

    ShellIcon {
        id: glyphIcon

        anchors.left: parent.left
        anchors.leftMargin: row.tokens.spaceMd
        anchors.verticalCenter: parent.verticalCenter
        visible: row.glyph.length > 0
        // PanelRow uses the fixed control icon grid.  Binding width back to
        // Text.implicitWidth creates a Qt binding cycle because Text's
        // implicit geometry can itself be resolved from its explicit width.
        width: visible ? row.tokens.iconControl : 0
        tokens: row.tokens
        grid: "control"
        text: row.glyph
        color:
            row.tone === "danger"
            ? row.theme.semanticStatusColor("warn")
            : (row.current ? row.theme.textPrimary : row.theme.textSecondary)
    }

    Column {
        id: leading

        anchors.left: glyphIcon.right
        anchors.leftMargin: glyphIcon.visible ? row.tokens.spaceMd : 0
        anchors.right: trailing.visible ? trailing.left : parent.right
        anchors.rightMargin: trailing.visible ? row.tokens.spaceSm : row.tokens.spaceMd
        anchors.verticalCenter: parent.verticalCenter
        spacing: row.tokens.spaceXs

        Item {
            id: titleLine

            width: parent.width
            height: Math.max(titleLabel.implicitHeight, valueLabel.implicitHeight)

            // The value keeps up to half the line; the title takes the rest.
            readonly property real valueBudget:
                valueLabel.visible
                ? Math.min(valueLabel.implicitWidth, titleLine.width / 2)
                : 0

            ShellLabel {
                id: titleLabel

                anchors.left: parent.left
                anchors.verticalCenter: parent.verticalCenter
                width:
                    Math.min(
                        implicitWidth,
                        titleLine.width
                        - (valueLabel.visible
                            ? titleLine.valueBudget + row.tokens.spaceMd
                            : 0)
                    )
                tokens: row.tokens
                role: "body"
                text: row.title
                color:
                    row.enabled
                    ? row.theme.textPrimary
                    : row.theme.textDisabled
            }

            ShellLabel {
                id: valueLabel

                anchors.left: titleLabel.right
                anchors.leftMargin: row.tokens.spaceMd
                anchors.verticalCenter: parent.verticalCenter
                visible: row.value.length > 0
                width:
                    Math.max(
                        0,
                        titleLine.width - titleLabel.width - row.tokens.spaceMd
                    )
                tokens: row.tokens
                role: "mono"
                text: row.value
                color: row.enabled ? row.valueColor : row.theme.textDisabled
            }
        }

        ShellLabel {
            width: parent.width
            visible: row.showsReason
            tokens: row.tokens
            role: "meta"
            wrapMode: Text.WordWrap
            text: row.disabledReason
            color: row.theme.textQuiet
        }
    }

    // Optional short trailing hint. Never more than a third of the row, and
    // never a disabled reason -- that has its own wrapping line.
    ShellLabel {
        id: trailing

        anchors.right: parent.right
        anchors.rightMargin: row.tokens.spaceMd
        anchors.verticalCenter: parent.verticalCenter
        visible: row.enabled && row.hint.length > 0
        width: Math.min(implicitWidth, row.width / 3)
        horizontalAlignment: Text.AlignRight
        tokens: row.tokens
        role: "meta"
        text: row.hint
        color: row.theme.textQuiet
    }

    HoverHandler {
        id: hover
        enabled: row.actionable
        cursorShape: row.actionable ? Qt.PointingHandCursor : Qt.ArrowCursor
    }

    TapHandler {
        id: press
        enabled: row.actionable
        onTapped: row.activate()
    }

    Keys.onPressed: event => {
        if (
            event.key === Qt.Key_Return
            || event.key === Qt.Key_Enter
            || event.key === Qt.Key_Space
        ) {
            row.activate();
            event.accepted = true;
        }
    }
}
