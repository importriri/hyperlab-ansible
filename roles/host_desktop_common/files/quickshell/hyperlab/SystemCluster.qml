// HyperLab system cluster (V447-C9.3).
//
// Network, audio and battery as one glyph cluster on the 16px grid. Values
// appear where an operator acts on them without opening anything (the audio
// level, the battery percentage); the network shows state through its glyph.
// One quiet dot reports that some secondary readout needs attention.
//
// Absence and unreadability stay distinct: a host with no battery shows no
// battery, while a battery the host cannot read stays visible and says so.
// Activation opens the native system panel; the wheel adjusts volume.

import QtQuick

ShellControl {
    id: cluster

    required property var audioPayload
    required property var audioLevel
    required property var batteryPayload
    required property var batteryPresence
    required property var networkPayload
    required property string attentionClass
    required property var icons

    signal panelRequested()
    signal volumeUpRequested()
    signal volumeDownRequested()

    readonly property bool needsAttention:
        cluster.attentionClass.length > 0

    // A battery that is known to be absent is hidden; a battery that cannot
    // be read stays on the rail as an unavailable reading.
    readonly property bool batteryVisible:
        !(cluster.batteryPresence.known === true
          && cluster.batteryPresence.present === false)

    readonly property string audioText:
        cluster.audioLevel.known === true
        ? (
            cluster.audioLevel.muted === true
            ? "Muted"
            : cluster.audioLevel.percent + "%"
          )
        : "—"

    flat: true
    contentSpacing: cluster.tokens.spaceMd

    accessibleName:
        "System. Audio " + cluster.audioText
        + ". Network " + String(cluster.networkPayload.text)

    content: [
        ShellIcon {
            anchors.verticalCenter: parent.verticalCenter
            tokens: cluster.tokens
            text: cluster.icons.networkGlyph(cluster.networkPayload)
            color: cluster.theme.telemetryTextColor(cluster.networkPayload)
        },

        Row {
            anchors.verticalCenter: parent.verticalCenter
            spacing: cluster.tokens.spaceXs

            ShellIcon {
                anchors.verticalCenter: parent.verticalCenter
                tokens: cluster.tokens
                text: cluster.icons.audioGlyph(cluster.audioLevel)
                color: cluster.theme.telemetryTextColor(cluster.audioPayload)
            }

            ShellLabel {
                anchors.verticalCenter: parent.verticalCenter
                tokens: cluster.tokens
                role: "bar"
                font.weight: Font.Normal
                text: cluster.audioText
                color: cluster.theme.telemetryTextColor(cluster.audioPayload)
            }
        },

        Row {
            anchors.verticalCenter: parent.verticalCenter
            visible: cluster.batteryVisible
            spacing: cluster.tokens.spaceXs

            ShellIcon {
                anchors.verticalCenter: parent.verticalCenter
                tokens: cluster.tokens
                text: cluster.icons.battery
                color: cluster.theme.telemetryTextColor(cluster.batteryPayload)
            }

            ShellLabel {
                anchors.verticalCenter: parent.verticalCenter
                tokens: cluster.tokens
                role: "bar"
                font.weight: Font.Normal
                text: String(cluster.batteryPayload.text)
                color: cluster.theme.telemetryTextColor(cluster.batteryPayload)
            }
        },

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            visible: cluster.needsAttention

            width: 6
            height: 6
            radius: 3

            color:
                cluster.theme.semanticStatusColor(
                    cluster.attentionClass
                )
        }
    ]

    onActivated: cluster.panelRequested()

    WheelHandler {
        onWheel: event => {
            if (event.angleDelta.y > 0) {
                cluster.volumeUpRequested();
            } else if (event.angleDelta.y < 0) {
                cluster.volumeDownRequested();
            }

            event.accepted = true;
        }
    }
}
