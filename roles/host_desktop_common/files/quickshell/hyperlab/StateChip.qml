// HyperLab runtime state chip (V447-C9.3).
//
// A machine state is a neutral fact, so it is drawn as a neutral glyph plus
// the state word. State never borrows a provenance colour, and an unknown
// state says so instead of resolving to "off".

import QtQuick

Row {
    id: chip

    required property var tokens
    required property var theme
    required property var icons
    required property string state

    property string role: "meta"

    readonly property string word: chip.icons.machineStateWord(chip.state)

    readonly property bool unknown: {
        const raw = String(chip.state).toLowerCase();

        return raw.length === 0 || raw === "unknown";
    }

    spacing: chip.tokens.spaceXs

    Accessible.role: Accessible.StaticText
    Accessible.name: "State " + chip.word

    ShellIcon {
        anchors.verticalCenter: parent.verticalCenter
        tokens: chip.tokens
        text: chip.icons.machineStateGlyph(chip.state)
        color: chip.unknown ? chip.theme.textQuiet : chip.theme.textSecondary
    }

    ShellLabel {
        anchors.verticalCenter: parent.verticalCenter
        tokens: chip.tokens
        role: chip.role
        text: chip.word
        color: chip.unknown ? chip.theme.textQuiet : chip.theme.textPrimary
    }
}
