// HyperLab typography primitive (V447-C9.3).
//
// Every string in the shell is rendered through one component so the product
// has a single reading hierarchy. The role decides family, size, line
// height, weight and tracking; a caller names the job of the text and picks
// an explicit tone.
//
//   display  sans 24/31 600   workspace title
//   title    sans 20/26 600   machine name
//   heading  sans 18/23 600   page heading
//   section  sans 16/21 600   section heading
//   body     sans 14/18 400   main interface text
//   meta     sans 13/17 400   metadata
//   label    sans 12/16 500   short provenance / section labels (caps)
//   bar      sans 13/17 500   rail text
//   value    mono 16/21 500   technical values (tabular)
//   mono     mono 13/17 400   identifiers, shortcuts
//
// Nothing essential renders below 13px. Presentation only.

import QtQuick

Text {
    id: label

    required property var tokens

    property string role: "body"
    property bool caps: false

    readonly property bool monoRole:
        label.role === "value" || label.role === "mono"

    font.family:
        label.monoRole
        ? label.tokens.fontMono
        : label.tokens.fontSans

    font.pixelSize: {
        switch (label.role) {
        case "display":
            return label.tokens.fontDisplay;
        case "title":
            return label.tokens.fontTitle;
        case "heading":
            return label.tokens.fontHeading;
        case "section":
            return label.tokens.fontValue;
        case "label":
            return label.tokens.fontLabel;
        case "meta":
        case "bar":
        case "mono":
            return label.tokens.fontMeta;
        case "value":
            return label.tokens.fontValue;
        default:
            return label.tokens.fontBody;
        }
    }

    lineHeight: 1.3

    font.weight: {
        switch (label.role) {
        case "display":
        case "title":
        case "heading":
        case "section":
            return Font.DemiBold;
        case "label":
        case "bar":
        case "value":
            return Font.Medium;
        default:
            return Font.Normal;
        }
    }

    font.letterSpacing:
        label.role === "label" || label.caps
        ? label.tokens.trackingLabel
        : 0

    font.capitalization:
        label.role === "label" || label.caps
        ? Font.AllUppercase
        : Font.MixedCase

    font.features: label.monoRole ? ({ "tnum": 1 }) : ({})

    textFormat: Text.PlainText
    renderType: Text.NativeRendering
    elide: Text.ElideRight

    // An elided string still has to be reachable, so the full text is always
    // the accessible name even when the visible run is cut.
    Accessible.role: Accessible.StaticText
    Accessible.name: label.text
}
