// HyperLab glyph primitive (V447-C9.3).
//
// Icons are outline glyphs from the shared icon table on three grids: 16px
// in the rail, 20px in controls, 24px for prominent detail. Sized from
// tokens so a glyph never drifts from the type scale beside it. A glyph is
// decoration unless the caller names it, because an unnamed icon carries no
// meaning for anyone reading the interface with assistive technology.

import QtQuick

Text {
    id: icon

    required property var tokens

    // bar | control | prominent
    property string grid: "bar"
    property string accessibleName: ""

    font.family: icon.tokens.fontMono
    font.pixelSize: {
        switch (icon.grid) {
        case "prominent":
            return icon.tokens.iconProminent;
        case "control":
            return icon.tokens.iconControl;
        default:
            return icon.tokens.iconBar;
        }
    }

    textFormat: Text.PlainText
    renderType: Text.NativeRendering
    verticalAlignment: Text.AlignVCenter
    horizontalAlignment: Text.AlignHCenter

    Accessible.ignored: icon.accessibleName.length === 0
    Accessible.role: Accessible.Graphic
    Accessible.name: icon.accessibleName
}
