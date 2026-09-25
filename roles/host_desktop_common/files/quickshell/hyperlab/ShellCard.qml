// HyperLab card (V447-C9.3).
//
// The one enclosure in the product: a raised opaque panel with a single
// hairline boundary, a shared radius and shared padding. Machines, the
// Control Center groups and the Diagnostics sections all use it, so a
// bounded region always means the same thing and never invents its own
// margin, radius or border weight.
//
// Selection and focus are neutral: a card is a container, so it never
// borrows a provenance colour to say "chosen".

import QtQuick

Rectangle {
    id: card

    required property var tokens
    required property var theme

    property bool interactive: false
    property bool selected: false
    property bool recessed: false
    property int padding: card.tokens.cardPadding
    property string accessibleName: ""

    default property alias body: contentArea.data

    readonly property bool actionable: card.interactive && card.enabled

    signal activated()

    // A card measures itself from what it contains, so a caller can never
    // size it with the wrong padding and quietly clip its own content.
    implicitHeight:
        contentArea.childrenRect.height
        + card.padding * 2
        + (card.recessed ? card.tokens.spaceXs : 0)

    radius: card.tokens.radiusCard

    color:
        card.selected
        ? card.theme.mix(card.theme.text, card.theme.raised, 0.08)
        : (
            card.actionable && (hover.hovered || press.pressed)
            ? card.theme.mix(card.theme.text, card.theme.raised, 0.05)
            : card.theme.raised
        )

    border.width:
        card.activeFocus || card.selected
        ? card.tokens.focusOutline
        : card.tokens.borderSize

    border.color:
        card.activeFocus
        ? card.theme.focusRing
        : (
            card.selected
            ? card.theme.boundaryStrong
            : (hover.hovered && card.actionable
                ? card.theme.boundaryStrong
                : card.theme.boundary)
        )

    activeFocusOnTab: card.actionable

    Accessible.role: card.interactive ? Accessible.Button : Accessible.Grouping
    Accessible.name: card.accessibleName
    Accessible.onPressAction: card.activate()

    function activate() {
        if (!card.actionable)
            return;

        card.activated();
    }

    Behavior on color {
        ColorAnimation {
            duration: card.tokens.motionHover
        }
    }

    // Restrained depth: one recessed bottom edge, no shadow and no glass.
    // It is drawn by the card, because the content area clips.
    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: card.border.width
        visible: card.recessed
        height: card.tokens.spaceXs
        color: card.theme.recess
    }

    Item {
        id: contentArea

        anchors.fill: parent
        anchors.margins: card.padding
        anchors.bottomMargin:
            card.padding + (card.recessed ? card.tokens.spaceXs : 0)
        clip: true
    }

    HoverHandler {
        id: hover
        enabled: card.actionable
        cursorShape: card.actionable ? Qt.PointingHandCursor : Qt.ArrowCursor
    }

    TapHandler {
        id: press
        enabled: card.actionable
        onTapped: card.activate()
    }

    Keys.onPressed: event => {
        if (
            event.key === Qt.Key_Return
            || event.key === Qt.Key_Enter
            || event.key === Qt.Key_Space
        ) {
            card.activate();
            event.accepted = true;
        }
    }
}
