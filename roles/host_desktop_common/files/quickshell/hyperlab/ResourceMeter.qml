// HyperLab resource meter (V447-C9.3).
//
// One scoped host reading: the metric label, the value in tabular mono,
// and the scope beneath it (what the number means, which sensor, which
// interface). The value takes a status tone only when the host reports one;
// an unavailable reading is quiet and says so, never a zero.

import QtQuick

Item {
    id: meter

    required property var tokens
    required property var theme
    required property string label
    required property string scope
    required property var payload

    property string valueOverride: ""
    // Ownership and identity values are facts, not warnings: keep them
    // primary unless the bridge reports an error.
    property bool neutral: false

    readonly property bool errored:
        String(meter.payload.class) === "error" || String(meter.payload.class) === "bad"

    readonly property bool unavailable:
        String(meter.payload.class) === "unavailable"
        || String(meter.payload.class) === "loading"
        || String(meter.payload.text).length === 0

    implicitWidth: Math.max(column.implicitWidth, 120)
    implicitHeight: column.implicitHeight

    Column {
        id: column

        spacing: 2

        Row {
            spacing: meter.tokens.spaceSm

            ShellLabel {
                anchors.baseline: valueLabel.baseline
                tokens: meter.tokens
                role: "label"
                text: meter.label
                color: meter.theme.textSecondary
            }

            ShellLabel {
                id: valueLabel
                tokens: meter.tokens
                role: "value"
                text: meter.valueOverride.length > 0
                    ? meter.valueOverride
                    : (meter.unavailable
                        ? (String(meter.payload.class) === "loading"
                            ? "Not yet observed"
                            : "Unavailable")
                        : String(meter.payload.text))
                color: meter.neutral && !meter.errored
                    ? meter.theme.textPrimary
                    : meter.theme.telemetryTextColor(meter.payload)
            }
        }

        ShellLabel {
            tokens: meter.tokens
            role: "meta"
            text: meter.scope
            color: meter.theme.textQuiet
        }
    }
}
