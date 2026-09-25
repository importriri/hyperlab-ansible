// HyperLab confirmation (V447-C9.3).
//
// One native confirmation for the whole product, owned by ShellSurfaces and
// bound to an immutable captured target. Cancel is the default and holds
// keyboard focus; Escape cancels; opening a dialog never executes anything;
// and the record carried here is the record executed, so re-selecting a
// different machine while the dialog is open can never redirect the
// operation.
//
// It is modal, not merely drawn on top: while it is open the host disables
// everything behind it (`modal` below is what the host binds to), so Tab and
// Backtab cycle only through the name field, Cancel and the confirm button,
// and neither Enter nor a click can reach a background control. A replaced
// record resets the field and focus; closing returns focus to where it was.
// The body scrolls inside a bounded card and the buttons stay in a fixed
// footer, so a long target or a short window never pushes them off screen.
//
// Destructive lifecycle operations may require the exact machine name to be
// typed. That is an interaction safeguard, not a privilege boundary: the
// reviewed backend remains the authority that enforces the operation.

import QtQuick
import QtQuick.Window

Item {
    id: confirmation

    required property var tokens
    required property var theme
    required property var shellSurfaces

    readonly property var record: confirmation.shellSurfaces.confirmation

    readonly property bool open:
        confirmation.record !== null
        && confirmation.record !== undefined
        && confirmation.record.open === true

    readonly property bool requiresName:
        confirmation.open && confirmation.record.requiresName === true

    // Keep the record-null transition safe. ShellSurfaces deliberately sets
    // confirmation to null after cancel/submit, and QML bindings do not all
    // necessarily settle in the same evaluation turn.
    readonly property string targetName:
        confirmation.open
        ? String(confirmation.record.targetName)
        : ""

    readonly property bool nameConfirmed:
        confirmation.open
        && (
            !confirmation.requiresName
            || nameField.text === confirmation.targetName
        )

    // True while a record is open; the host disables its background on it.
    readonly property bool modal: confirmation.open

    // Where keyboard focus was before the dialog took it.
    property var returnFocus: null

    signal confirmed(var record)

    visible: confirmation.open
    z: 100

    // Every new record, including one that replaces an open record, starts
    // from an empty name and the default Cancel.
    function reset() {
        nameField.text = "";
        body.contentY = 0;
        cancelButton.forceActiveFocus();
    }

    function captureReturnFocus() {
        if (confirmation.returnFocus !== null)
            return;

        const current = confirmation.Window.activeFocusItem;

        confirmation.returnFocus =
            current && !confirmation.contains(current) ? current : null;
    }

    // Opening: the dialog must be visible before it can take focus, so the
    // reset follows the visibility change. Replacing an open record resets
    // in place.
    onVisibleChanged: {
        if (!confirmation.visible)
            return;

        confirmation.captureReturnFocus();
        confirmation.reset();
    }

    onRecordChanged: {
        if (!confirmation.open)
            return;

        confirmation.captureReturnFocus();

        if (confirmation.visible)
            confirmation.reset();
    }

    onOpenChanged: {
        if (confirmation.open)
            return;

        const target = confirmation.returnFocus;

        confirmation.returnFocus = null;

        if (target && target.visible && target.enabled)
            target.forceActiveFocus();
    }

    function contains(item) {
        for (let node = item; node; node = node.parent) {
            if (node === confirmation)
                return true;
        }

        return false;
    }

    function ensureVisible(item) {
        const point = item.mapToItem(body.contentItem, 0, 0);

        if (point.y < body.contentY)
            body.contentY = point.y;
        else if (point.y + item.height > body.contentY + body.height)
            body.contentY = point.y + item.height - body.height;
    }

    // The scrim is part of the dialog: it dims the workspace and absorbs the
    // clicks the dialog must not let through.
    Rectangle {
        anchors.fill: parent
        color: confirmation.theme.scrim

        TapHandler {
            onTapped: confirmation.shellSurfaces.cancelConfirmation()
        }
    }

    Rectangle {
        id: card

        anchors.centerIn: parent

        width: Math.min(
            confirmation.tokens.dialogWidth,
            Math.max(
                confirmation.tokens.workspaceMinWidth
                - confirmation.tokens.spaceHuge,
                confirmation.width - confirmation.tokens.spaceHuge
            )
        )

        readonly property real footerHeight:
            footer.implicitHeight + confirmation.tokens.spaceMd

        height: Math.min(
            column.implicitHeight + card.footerHeight
                + confirmation.tokens.spaceXl * 2,
            Math.max(
                card.footerHeight + confirmation.tokens.spaceXl * 2,
                confirmation.height - confirmation.tokens.spaceHuge
            )
        )

        radius: confirmation.tokens.radiusSurface
        color: confirmation.theme.floating
        border.width: confirmation.tokens.borderSize
        border.color: confirmation.theme.boundaryStrong

        Accessible.role: Accessible.Dialog
        Accessible.name:
            confirmation.open ? String(confirmation.record.title) : ""

        Keys.onEscapePressed: {
            confirmation.shellSurfaces.cancelConfirmation();
        }

        // The body scrolls; the footer does not.
        Flickable {
            id: body

            anchors.left: parent.left
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: footer.top
            anchors.leftMargin: confirmation.tokens.spaceXl
            anchors.rightMargin: confirmation.tokens.spaceXl
            anchors.topMargin: confirmation.tokens.spaceXl
            anchors.bottomMargin: confirmation.tokens.spaceMd

            clip: true
            contentWidth: width
            contentHeight: column.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            interactive: contentHeight > height

            Column {
                id: column

                width: body.width
                spacing: confirmation.tokens.spaceMd

                ShellLabel {
                    width: parent.width
                    tokens: confirmation.tokens
                    role: "heading"
                    wrapMode: Text.WordWrap
                    text: confirmation.open ? String(confirmation.record.title) : ""
                    color: confirmation.theme.textPrimary
                }

                ShellLabel {
                    width: parent.width
                    visible: text.length > 0
                    tokens: confirmation.tokens
                    role: "value"
                    wrapMode: Text.WrapAnywhere
                    text:
                        confirmation.open
                        ? String(confirmation.record.targetName)
                        : ""
                    color: confirmation.theme.textPrimary
                }

                ShellLabel {
                    width: parent.width
                    tokens: confirmation.tokens
                    role: "body"
                    wrapMode: Text.WordWrap
                    text:
                        confirmation.open
                        ? String(confirmation.record.consequence)
                        : ""
                    color: confirmation.theme.textSecondary
                }

                ShellLabel {
                    width: parent.width
                    visible: confirmation.requiresName
                    tokens: confirmation.tokens
                    role: "meta"
                    wrapMode: Text.WordWrap
                    text: "Type the exact machine name to continue."
                    color: confirmation.theme.textQuiet
                }

                Rectangle {
                    width: parent.width
                    visible: confirmation.requiresName
                    height: confirmation.tokens.controlHeightLarge
                    radius: confirmation.tokens.radiusControl
                    color: confirmation.theme.raised
                    border.width:
                        nameField.activeFocus
                        ? confirmation.tokens.focusOutline
                        : confirmation.tokens.borderSize
                    border.color:
                        nameField.activeFocus
                        ? confirmation.theme.focusRing
                        : confirmation.theme.boundary

                    TextInput {
                        id: nameField

                        objectName: "confirmation-name"

                        anchors.fill: parent
                        anchors.leftMargin: confirmation.tokens.spaceMd
                        anchors.rightMargin: confirmation.tokens.spaceMd
                        verticalAlignment: TextInput.AlignVCenter

                        font.family: confirmation.tokens.fontMono
                        font.pixelSize: confirmation.tokens.fontMeta
                        color: confirmation.theme.textPrimary
                        selectionColor: confirmation.theme.fillSelected
                        selectedTextColor: confirmation.theme.textPrimary
                        clip: true

                        // In the tab order explicitly; Enter here never submits.
                        activeFocusOnTab: confirmation.requiresName
                        KeyNavigation.tab: cancelButton
                        KeyNavigation.backtab:
                            confirmButton.actionable ? confirmButton : cancelButton

                        Accessible.role: Accessible.EditableText
                        Accessible.name: "Exact machine name"

                        onActiveFocusChanged: {
                            if (activeFocus)
                                confirmation.ensureVisible(parent);
                        }

                        Keys.onEscapePressed:
                            confirmation.shellSurfaces.cancelConfirmation()
                    }
                }
            }
        }

        Row {
            id: footer

            objectName: "confirmation-footer"

            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.rightMargin: confirmation.tokens.spaceXl
            anchors.bottomMargin: confirmation.tokens.spaceXl
            spacing: confirmation.tokens.spaceSm

            ShellControl {
                id: cancelButton

                objectName: "confirmation-cancel"

                tokens: confirmation.tokens
                theme: confirmation.theme
                accessibleName: "Cancel"

                KeyNavigation.tab:
                    confirmButton.actionable
                    ? confirmButton
                    : (confirmation.requiresName ? nameField : cancelButton)
                KeyNavigation.backtab:
                    confirmation.requiresName
                    ? nameField
                    : (confirmButton.actionable ? confirmButton : cancelButton)

                content: [
                    ShellLabel {
                        anchors.verticalCenter: parent.verticalCenter
                        tokens: confirmation.tokens
                        role: "body"
                        text: "Cancel"
                        color: confirmation.theme.textPrimary
                    }
                ]

                onActivated:
                    confirmation.shellSurfaces.cancelConfirmation()
            }

            ShellControl {
                id: confirmButton

                objectName: "confirmation-confirm"

                tokens: confirmation.tokens
                theme: confirmation.theme
                tone: "danger"

                KeyNavigation.tab:
                    confirmation.requiresName ? nameField : cancelButton
                KeyNavigation.backtab: cancelButton
                enabled: confirmation.nameConfirmed
                busy:
                    confirmation.open
                    && confirmation.record.submitted === true
                accessibleName:
                    confirmation.open
                    ? String(confirmation.record.confirmLabel)
                    : ""
                disabledReason: "Exact machine name required"

                content: [
                    ShellLabel {
                        anchors.verticalCenter: parent.verticalCenter
                        tokens: confirmation.tokens
                        role: "body"
                        text:
                            confirmation.open
                            ? String(confirmation.record.confirmLabel)
                            : ""
                        color:
                            confirmation.theme.semanticStatusColor("warn")
                    }
                ]

                onActivated: {
                    // The captured record is the record executed. Nothing
                    // is re-read from the current selection here.
                    const captured =
                        confirmation.shellSurfaces.submitConfirmation();

                    if (captured !== null)
                        confirmation.confirmed(captured);
                }
            }
        }
    }
}
