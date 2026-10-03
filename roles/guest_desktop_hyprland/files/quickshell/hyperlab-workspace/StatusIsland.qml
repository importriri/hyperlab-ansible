// What is this machine doing: GPU, CPU, memory, volume, network and the
// time. Readouts whose source cannot be read are hidden, not faked.

import Quickshell
import QtQuick

Island {
    id: status

    required property var stats

    padding: 16
    enterDelay: 90
    enterFrom: Qt.point(18, 0)

    // A readout that runs hot turns to the urgent colour.
    function heat(percent) {
        return percent !== null && percent >= 85 ? status.theme.urgent : status.theme.textSoft;
    }

    SystemClock {
        id: clock
        precision: SystemClock.Minutes
    }

    Row {
        spacing: 18

        Readout {
            anchors.verticalCenter: parent.verticalCenter
            visible: status.stats.gpu !== null
            theme: status.theme
            label: "GPU"
            value: status.stats.gpu ? status.stats.gpu.load + "%" : ""
            valueColor: status.heat(status.stats.gpu ? status.stats.gpu.load : null)
        }

        Row {
            anchors.verticalCenter: parent.verticalCenter
            visible: status.stats.cpu !== null
            spacing: 8

            Readout {
                anchors.verticalCenter: parent.verticalCenter
                theme: status.theme
                label: "CPU"
                value: status.stats.cpu !== null ? status.stats.cpu + "%" : ""
                valueColor: status.heat(status.stats.cpu)
            }

            Sparkline {
                anchors.verticalCenter: parent.verticalCenter
                theme: status.theme
                samples: status.stats.cpuHistory
            }
        }

        Readout {
            anchors.verticalCenter: parent.verticalCenter
            visible: status.stats.memory !== null
            theme: status.theme
            label: "RAM"
            valueColor: status.heat(status.stats.memory
                ? Math.round(100 * status.stats.memory.usedGiB / status.stats.memory.totalGiB) : null)
            value: status.stats.memory
                ? status.stats.memory.usedGiB.toFixed(1) + " / " + status.stats.memory.totalGiB.toFixed(1) + " G"
                : ""
        }

        Readout {
            anchors.verticalCenter: parent.verticalCenter
            visible: status.stats.volume >= 0
            theme: status.theme
            label: "VOL"
            value: status.stats.muted ? "muted" : status.stats.volume + "%"
        }

        Readout {
            anchors.verticalCenter: parent.verticalCenter
            visible: status.stats.networkKnown
            theme: status.theme
            label: "NET"
            value: status.stats.network || "offline"
            valueColor: status.stats.network ? status.theme.textSoft : status.theme.urgent
        }

        UiText {
            anchors.verticalCenter: parent.verticalCenter
            theme: status.theme
            mono: true
            font.pixelSize: 13
            font.weight: Font.Medium
            text: Qt.formatDateTime(clock.date, "ddd d MMM") + "  ·  " + Qt.formatDateTime(clock.date, "HH:mm")
        }
    }
}
