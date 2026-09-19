import Quickshell
import Quickshell.Io
import QtQuick
import QtQuick.Layouts

PanelWindow {
    id: root

    property var modelData

    readonly property string statusBridge:
        "/usr/local/bin/privatestack-hyperlab"

    property var trustPayload: ({
        "text": "…",
        "tooltip": ""
    })
    property var ramPayload: ({
        "text": "…",
        "tooltip": ""
    })
    property var gpuPayload: ({
        "text": "…",
        "tooltip": ""
    })
    property var vmPayload: ({
        "text": "…",
        "tooltip": ""
    })

    function parsePayload(raw, fallbackText) {
        const source = String(raw).trim();

        if (source.length === 0) {
            return {
                "text": fallbackText,
                "tooltip": ""
            };
        }

        try {
            const parsed = JSON.parse(source);

            return {
                "text":
                    parsed.text !== undefined
                    ? String(parsed.text)
                    : fallbackText,
                "tooltip":
                    parsed.tooltip !== undefined
                    ? String(parsed.tooltip)
                    : "",
                "class":
                    parsed.class !== undefined
                    ? parsed.class
                    : ""
            };
        } catch (error) {
            return {
                "text": fallbackText,
                "tooltip": "HyperLab status payload unavailable"
            };
        }
    }

    function refreshSlowMetrics() {
        if (!ramProcess.running)
            ramProcess.running = true;

        if (!gpuProcess.running)
            gpuProcess.running = true;

        if (!vmProcess.running)
            vmProcess.running = true;
    }

    screen: modelData

    anchors {
        top: true
        left: true
        right: true
    }

    implicitHeight: 37
    exclusiveZone: 37
    color: "#0b0f14"

    SystemClock {
        id: clock
        precision: SystemClock.Minutes
    }

    // Trust is an event stream. No periodic trust polling is allowed.
    Process {
        id: trustProcess

        running: true
        command: [
            root.statusBridge,
            "watch",
            "trust"
        ]

        stdout: SplitParser {
            onRead: data => {
                root.trustPayload =
                    root.parsePayload(data, "?");
            }
        }

        onRunningChanged: {
            if (!running)
                trustRestart.start();
        }
    }

    Timer {
        id: trustRestart

        interval: 2000
        repeat: false

        onTriggered: {
            if (!trustProcess.running)
                trustProcess.running = true;
        }
    }

    // Slow status fields deliberately retain the existing 30-second
    // HyperLab cadence instead of turning the shell into a busy poller.
    Process {
        id: ramProcess

        command: [
            root.statusBridge,
            "ram"
        ]

        stdout: StdioCollector {
            onStreamFinished: {
                root.ramPayload =
                    root.parsePayload(this.text, "?");
            }
        }
    }

    Process {
        id: gpuProcess

        command: [
            root.statusBridge,
            "gpu"
        ]

        stdout: StdioCollector {
            onStreamFinished: {
                root.gpuPayload =
                    root.parsePayload(this.text, "?");
            }
        }
    }

    Process {
        id: vmProcess

        command: [
            root.statusBridge,
            "vms"
        ]

        stdout: StdioCollector {
            onStreamFinished: {
                root.vmPayload =
                    root.parsePayload(this.text, "?");
            }
        }
    }

    Timer {
        interval: 30000
        repeat: true
        running: true
        triggeredOnStart: true

        onTriggered: root.refreshSlowMetrics()
    }

    Rectangle {
        anchors.fill: parent
        color: "#0b0f14"

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: "#25303a"
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            spacing: 8

            Rectangle {
                Layout.preferredHeight: 25
                Layout.preferredWidth: brandText.implicitWidth + 20
                radius: 7
                color: "#131a21"
                border.width: 1
                border.color: "#35404a"

                Text {
                    id: brandText
                    anchors.centerIn: parent
                    text: "◆  HYPERLAB"
                    color: "#e6edf3"
                    font.pixelSize: 12
                    font.bold: true
                }
            }

            Rectangle {
                Layout.preferredHeight: 25
                Layout.preferredWidth: trustText.implicitWidth + 18
                radius: 7
                color: "#111820"
                border.width: 1
                border.color: "#35404a"

                Text {
                    id: trustText
                    anchors.centerIn: parent
                    text: "TRUST " + root.trustPayload.text
                    color: "#d2dae2"
                    font.pixelSize: 11
                    font.bold: true
                }
            }

            Item {
                Layout.fillWidth: true
            }

            Text {
                text: "RAM " + root.ramPayload.text
                color: "#aab6c2"
                font.pixelSize: 11
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 14
                color: "#25303a"
            }

            Text {
                text: "GPU " + root.gpuPayload.text
                color: "#aab6c2"
                font.pixelSize: 11
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 14
                color: "#25303a"
            }

            Text {
                text: "VM " + root.vmPayload.text
                color: "#aab6c2"
                font.pixelSize: 11
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 14
                color: "#25303a"
            }

            Text {
                text: Qt.formatDateTime(
                    clock.date,
                    "ddd dd MMM  HH:mm"
                )
                color: "#e6edf3"
                font.pixelSize: 11
                font.bold: true
            }
        }
    }
}
