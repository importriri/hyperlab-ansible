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

    readonly property string telemetryBridge:
        "/usr/local/bin/privatestack-telemetry"

    readonly property string actionBridge:
        "/usr/local/bin/privatestack-shell-actions"

    property string keyboardLayout: "it"
    property string wallpaperMode: "public"

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

    property var temperaturePayload: ({
        "text": "…",
        "tooltip": "",
        "class": ""
    })

    property var networkPayload: ({
        "text": "…",
        "tooltip": "",
        "class": ""
    })

    property var audioPayload: ({
        "text": "…",
        "tooltip": "",
        "class": ""
    })

    property var batteryPayload: ({
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

    function normalizeStatusPayload(candidate, fallbackText) {
        if (
            candidate === undefined
            || candidate === null
            || typeof candidate !== "object"
        ) {
            return {
                "text": fallbackText,
                "tooltip": "",
                "class": "unavailable"
            };
        }

        return {
            "text":
                candidate.text !== undefined
                ? String(candidate.text)
                : fallbackText,
            "tooltip":
                candidate.tooltip !== undefined
                ? String(candidate.tooltip)
                : "",
            "class":
                candidate.class !== undefined
                ? String(candidate.class)
                : ""
        };
    }

    function applyTelemetryPayload(raw) {
        const source = String(raw).trim();

        if (source.length === 0)
            return;

        try {
            const parsed = JSON.parse(source);

            root.temperaturePayload =
                root.normalizeStatusPayload(
                    parsed.temperature,
                    "—"
                );

            root.networkPayload =
                root.normalizeStatusPayload(
                    parsed.network,
                    "—"
                );

            root.audioPayload =
                root.normalizeStatusPayload(
                    parsed.audio,
                    "—"
                );

            root.batteryPayload =
                root.normalizeStatusPayload(
                    parsed.battery,
                    "—"
                );
        } catch (error) {
            console.warn(
                "HyperLab telemetry payload parse failed"
            );
        }
    }

    function applyKeyboardLayout(raw) {
        const candidate = String(raw).trim();

        if (
            candidate === "it"
            || candidate === "us"
            || candidate === "ara"
        ) {
            root.keyboardLayout = candidate;
        }
    }

    function applyWallpaperMode(raw) {
        const candidate = String(raw).trim();

        if (
            candidate === "public"
            || candidate === "personal"
        ) {
            root.wallpaperMode = candidate;
        }
    }

    function keyboardLabel() {
        switch (root.keyboardLayout) {
        case "us":
            return "EN";
        case "ara":
            return "AR";
        default:
            return "IT";
        }
    }

    function wallpaperLabel() {
        return root.wallpaperMode === "personal"
            ? "PVT"
            : "PUB";
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

    function telemetryTextColor(candidate) {
        const statusClass = String(candidate.class);

        if (
            statusClass.length === 0
            || statusClass === "unavailable"
        ) {
            return root.palette.subtext;
        }

        return root.semanticStatusColor(statusClass);
    }

    function refreshSlowMetrics() {
        if (!ramProcess.running)
            ramProcess.running = true;

        if (!gpuProcess.running)
            gpuProcess.running = true;

        if (!vmProcess.running)
            vmProcess.running = true;

        if (!telemetryProcess.running)
            telemetryProcess.running = true;
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

        root.applyKeyboardLayout(
            keyboardStateFile.text()
        );

        root.applyWallpaperMode(
            wallpaperModeStateFile.text()
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

    FileView {
        id: keyboardStateFile

        path:
            Quickshell.env("HOME")
            + "/.config/hyperlab/"
            + "keyboard-layout"

        watchChanges: true

        onFileChanged: reload()

        onTextChanged: {
            root.applyKeyboardLayout(
                this.text()
            );
        }
    }

    FileView {
        id: wallpaperModeStateFile

        path:
            Quickshell.env("HOME")
            + "/.config/hyperlab/"
            + "wallpaper-mode"

        watchChanges: true

        onFileChanged: reload()

        onTextChanged: {
            root.applyWallpaperMode(
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

    Process {
        id: telemetryProcess

        command: [
            root.telemetryBridge,
            "snapshot"
        ]

        stdout: StdioCollector {
            onStreamFinished: {
                root.applyTelemetryPayload(this.text);
            }
        }
    }

    Process {
        id: keyboardActionProcess

        command: [
            root.actionBridge,
            "keyboard-cycle"
        ]

        onRunningChanged: {
            if (!running)
                keyboardStateFile.reload();
        }
    }

    Process {
        id: wallpaperActionProcess

        command: [
            root.actionBridge,
            "wallpaper-mode-toggle"
        ]

        onRunningChanged: {
            if (!running)
                wallpaperModeStateFile.reload();
        }
    }

    Process {
        id: controlsActionProcess

        command: [
            root.actionBridge,
            "controls-open"
        ]
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
                text:
                    "TEMP "
                    + root.temperaturePayload.text

                color:
                    root.telemetryTextColor(
                        root.temperaturePayload
                    )

                font.pixelSize: 11
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 14
                color: root.palette.overlay
            }

            Text {
                text:
                    "NET "
                    + root.networkPayload.text

                color:
                    root.telemetryTextColor(
                        root.networkPayload
                    )

                font.pixelSize: 11
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 14
                color: root.palette.overlay
            }

            Text {
                text:
                    "VOL "
                    + root.audioPayload.text

                color:
                    root.telemetryTextColor(
                        root.audioPayload
                    )

                font.pixelSize: 11
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 14
                color: root.palette.overlay
            }

            Text {
                text:
                    "BAT "
                    + root.batteryPayload.text

                color:
                    root.telemetryTextColor(
                        root.batteryPayload
                    )

                font.pixelSize: 11
            }

            Rectangle {
                Layout.preferredWidth: 1
                Layout.preferredHeight: 14
                color: root.palette.overlay
            }

            Rectangle {
                Layout.preferredHeight: 23
                Layout.preferredWidth:
                    keyboardControlText.implicitWidth + 14

                radius: 6
                color: root.palette.mantle

                border.width: 1
                border.color: root.palette.overlay

                Text {
                    id: keyboardControlText

                    anchors.centerIn: parent

                    text:
                        "KEY "
                        + root.keyboardLabel()

                    color: root.palette.text
                    font.pixelSize: 10
                    font.bold: true
                }

                TapHandler {
                    onTapped: {
                        if (!keyboardActionProcess.running)
                            keyboardActionProcess.running = true;
                    }
                }
            }

            Rectangle {
                Layout.preferredHeight: 23
                Layout.preferredWidth:
                    wallpaperControlText.implicitWidth + 14

                radius: 6
                color: root.palette.mantle

                border.width: 1
                border.color: root.palette.overlay

                Text {
                    id: wallpaperControlText

                    anchors.centerIn: parent

                    text:
                        "WALL "
                        + root.wallpaperLabel()

                    color: root.palette.text
                    font.pixelSize: 10
                    font.bold: true
                }

                TapHandler {
                    onTapped: {
                        if (!wallpaperActionProcess.running)
                            wallpaperActionProcess.running = true;
                    }
                }
            }

            Rectangle {
                Layout.preferredHeight: 23
                Layout.preferredWidth:
                    controlsText.implicitWidth + 14

                radius: 6
                color: root.palette.surface

                border.width: 1
                border.color: root.palette.accent

                Text {
                    id: controlsText

                    anchors.centerIn: parent
                    text: "CTL"

                    color: root.palette.text
                    font.pixelSize: 10
                    font.bold: true
                }

                TapHandler {
                    onTapped: {
                        if (!controlsActionProcess.running)
                            controlsActionProcess.running = true;
                    }
                }
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
