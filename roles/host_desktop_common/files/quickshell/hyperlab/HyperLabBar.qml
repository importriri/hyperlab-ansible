import Quickshell
import Quickshell.Io
import QtQuick
import QtQuick.Layouts

PanelWindow {
    id: root

    property var modelData

    readonly property string statusBridge:
        "/usr/local/bin/privatestack-hyperlab"

    readonly property string compositorAdapter:
        "/usr/local/bin/privatestack-compositor-adapter"

    property var palette: ({
        "name": "fallback",
        "base": "black",
        "mantle": "black",
        "surface": "darkslategray",
        "overlay": "dimgray",
        "text": "white",
        "subtext": "lightgray",
        "accent": "deepskyblue",
        "accent2": "cyan",
        "ok": "limegreen",
        "warn": "gold",
        "bad": "crimson"
    })

    property var workspacePayload: ({
        "active": 0,
        "occupied": [],
        "urgent": []
    })

    property var trustPayload: ({
        "text": "…",
        "tooltip": "",
        "class": ""
    })

    property var ramPayload: ({
        "text": "…",
        "tooltip": "",
        "class": ""
    })

    property var gpuPayload: ({
        "text": "…",
        "tooltip": "",
        "class": ""
    })

    property var vmPayload: ({
        "text": "…",
        "tooltip": "",
        "class": ""
    })

    function validPalette(candidate) {
        const required = [
            "name",
            "base",
            "mantle",
            "surface",
            "overlay",
            "text",
            "subtext",
            "accent",
            "accent2",
            "ok",
            "warn",
            "bad"
        ];

        for (let index = 0; index < required.length; index++) {
            const key = required[index];

            if (
                candidate[key] === undefined
                || typeof candidate[key] !== "string"
                || candidate[key].length === 0
            ) {
                return false;
            }
        }

        return true;
    }

    function applyPalette(raw) {
        const source = String(raw).trim();

        if (source.length === 0)
            return;

        try {
            const parsed = JSON.parse(source);

            if (!root.validPalette(parsed))
                return;

            root.palette = parsed;
            console.info(
                "HyperLab palette loaded: " + parsed.name
            );
        } catch (error) {
            console.warn(
                "HyperLab semantic palette parse failed"
            );
        }
    }

    function parsePayload(raw, fallbackText) {
        const source = String(raw).trim();

        if (source.length === 0) {
            return {
                "text": fallbackText,
                "tooltip": "",
                "class": ""
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
                    ? String(parsed.class)
                    : ""
            };
        } catch (error) {
            return {
                "text": fallbackText,
                "tooltip":
                    "HyperLab status payload unavailable",
                "class": "error"
            };
        }
    }

    function applyWorkspacePayload(raw) {
        const source = String(raw).trim();

        if (source.length === 0)
            return;

        try {
            const parsed = JSON.parse(source);

            if (
                typeof parsed.active !== "number"
                || !Array.isArray(parsed.occupied)
                || !Array.isArray(parsed.urgent)
            ) {
                return;
            }

            root.workspacePayload = parsed;
        } catch (error) {
            console.warn(
                "HyperLab workspace payload parse failed"
            );
        }
    }

    function semanticStatusColor(statusClass) {
        switch (String(statusClass)) {
        case "ok":
            return root.palette.ok;
        case "warning":
        case "warn":
            return root.palette.warn;
        case "error":
        case "bad":
        case "critical":
            return root.palette.bad;
        default:
            return root.palette.accent;
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
    color: root.palette.base

    Component.onCompleted: {
        root.applyPalette(
            paletteFile.text()
        );
    }

    FileView {
        id: paletteFile

        path:
            Quickshell.env("HOME")
            + "/.config/hyperlab/"
            + "palette-quickshell.json"

        blockLoading: true
        watchChanges: true

        onFileChanged: reload()

        onTextChanged: {
            root.applyPalette(
                this.text()
            );
        }
    }

    SystemClock {
        id: clock
        precision: SystemClock.Minutes
    }

    // Workspace state is compositor-neutral in QML. The adapter owns
    // translation to Sway or Hyprland and emits one JSON snapshot per event.
    Process {
        id: workspaceProcess

        running: true

        command: [
            root.compositorAdapter,
            "workspace-watch"
        ]

        stdout: SplitParser {
            onRead: data => {
                root.applyWorkspacePayload(data);
            }
        }

        onRunningChanged: {
            if (!running)
                workspaceRestart.start();
        }
    }

    Timer {
        id: workspaceRestart
        interval: 2000
        repeat: false

        onTriggered: {
            if (!workspaceProcess.running)
                workspaceProcess.running = true;
        }
    }

    // Trust remains event-driven through hyperlabctl.
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
        color: root.palette.base

        Rectangle {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            height: 1
            color: root.palette.overlay
        }

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 10
            spacing: 6

            // Definitive product order: workspaces first, then HyperLab.
            Repeater {
                model: 9

                delegate: Rectangle {
                    property int workspaceNumber: index + 1

                    readonly property bool isActive:
                        root.workspacePayload.active
                        === workspaceNumber

                    readonly property bool isOccupied:
                        root.workspacePayload.occupied
                        .indexOf(workspaceNumber) >= 0

                    readonly property bool isUrgent:
                        root.workspacePayload.urgent
                        .indexOf(workspaceNumber) >= 0

                    Layout.preferredWidth: 22
                    Layout.preferredHeight: 23

                    radius: 6

                    color:
                        isActive
                        ? root.palette.accent
                        : (
                            isOccupied
                            ? root.palette.surface
                            : "transparent"
                        )

                    border.width: 1

                    border.color:
                        isUrgent
                        ? root.palette.bad
                        : (
                            isActive
                            ? root.palette.accent
                            : root.palette.overlay
                        )

                    Text {
                        anchors.centerIn: parent
                        text: parent.workspaceNumber

                        color:
                            parent.isActive
                            ? root.palette.base
                            : (
                                parent.isOccupied
                                ? root.palette.text
                                : root.palette.subtext
                            )

                        font.pixelSize: 10
                        font.bold: parent.isActive
                    }
                }
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 16
                color: root.palette.overlay
            }

            Rectangle {
                Layout.preferredHeight: 25
                Layout.preferredWidth:
                    brandText.implicitWidth + 20

                radius: 7
                color: root.palette.surface

                border.width: 1
                border.color: root.palette.accent

                Text {
                    id: brandText

                    anchors.centerIn: parent
                    text: "◆  HYPERLAB"
                    color: root.palette.text
                    font.pixelSize: 12
                    font.bold: true
                }
            }

            Rectangle {
                Layout.preferredHeight: 25
                Layout.preferredWidth:
                    trustText.implicitWidth + 18

                radius: 7
                color: root.palette.mantle

                border.width: 1

                border.color:
                    root.semanticStatusColor(
                        root.trustPayload.class
                    )

                Text {
                    id: trustText

                    anchors.centerIn: parent

                    text:
                        "TRUST "
                        + root.trustPayload.text

                    color: root.palette.text
                    font.pixelSize: 11
                    font.bold: true
                }
            }

            Item {
                Layout.fillWidth: true
            }

            Text {
                text:
                    "RAM "
                    + root.ramPayload.text

                color: root.palette.subtext
                font.pixelSize: 11
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 14
                color: root.palette.overlay
            }

            Text {
                text:
                    "GPU "
                    + root.gpuPayload.text

                color: root.palette.subtext
                font.pixelSize: 11
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 14
                color: root.palette.overlay
            }

            Text {
                text:
                    "VM "
                    + root.vmPayload.text

                color: root.palette.subtext
                font.pixelSize: 11
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 14
                color: root.palette.overlay
            }

            Text {
                text: Qt.formatDateTime(
                    clock.date,
                    "ddd dd MMM  HH:mm"
                )

                color: root.palette.text
                font.pixelSize: 11
                font.bold: true
            }
        }
    }
}
