// HyperLab system entry (V447-C9.3).
//
// The last control on the rail opens the Control Center. It is the one place
// an operator needs to find when they do not know where something lives, so
// it is labelled, reachable by keyboard and never a hidden alternate click.

import QtQuick

ShellControl {
    id: entry

    required property var icons

    flat: true

    accessibleName: "Control Center"
    Accessible.description: "Host settings and session controls"

    content: [
        ShellIcon {
            anchors.verticalCenter: parent.verticalCenter
            tokens: entry.tokens
            text: entry.icons.controlCenter
            color: entry.theme.textPrimary
        }
    ]
}
