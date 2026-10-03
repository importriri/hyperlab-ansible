// Readouts for the status island, each from a real source in this guest:
//
//   CPU      /proc/stat, sampled every two seconds
//   RAM      /proc/meminfo
//   NET      the interface holding the default route in /proc/net/route
//   GPU      nvidia-smi, only when the guest has an NVIDIA driver
//   VOLUME   the default PipeWire sink
//
// A source that cannot be read leaves its readout null, and the island
// hides it. Nothing is decorative data.

import Quickshell
import Quickshell.Io
import Quickshell.Services.Pipewire
import QtQuick
import "stats.js" as Stats

Item {
    id: stats

    visible: false

    property int interval: 2000

    property var cpu: null
    property var cpuHistory: []
    property var memory: null
    property string network: ""
    property bool networkKnown: false
    property var gpu: null
    property bool gpuAvailable: true

    readonly property var sink: Pipewire.defaultAudioSink
    readonly property bool audioReady: sink !== null && sink.audio !== null
    readonly property int volume: audioReady ? Math.round(sink.audio.volume * 100) : -1
    readonly property bool muted: audioReady && sink.audio.muted

    property var lastCpuSample: null

    function sample() {
        procStat.reload();
        procMem.reload();
        procRoute.reload();
        if (stats.gpuAvailable && !gpuProcess.running)
            gpuProcess.running = true;
    }

    PwObjectTracker {
        objects: [stats.sink]
    }

    Timer {
        interval: stats.interval
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: stats.sample()
    }

    FileView {
        id: procStat

        path: "/proc/stat"
        blockLoading: true

        onLoaded: {
            const current = Stats.cpuSample(this.text());
            const percent = Stats.cpuPercent(stats.lastCpuSample, current);
            stats.lastCpuSample = current;
            if (percent !== null) {
                stats.cpu = percent;
                stats.cpuHistory = Stats.pushHistory(stats.cpuHistory, percent, 24);
            }
        }
    }

    FileView {
        id: procMem

        path: "/proc/meminfo"
        blockLoading: true

        onLoaded: stats.memory = Stats.memory(this.text())
    }

    FileView {
        id: procRoute

        path: "/proc/net/route"
        blockLoading: true

        onLoaded: {
            stats.network = Stats.defaultInterface(this.text());
            stats.networkKnown = true;
        }
    }

    Process {
        id: gpuProcess

        // Exits 127 without starting anything when the guest has no driver.
        command: [
            "sh", "-c",
            "command -v nvidia-smi >/dev/null || exit 127; "
            + "exec nvidia-smi --query-gpu=utilization.gpu,temperature.gpu "
            + "--format=csv,noheader,nounits"
        ]

        stdout: StdioCollector {
            onStreamFinished: stats.gpu = Stats.gpu(this.text)
        }

        // No driver, no readout: the island never shows a GPU it cannot see.
        onExited: (exitCode, exitStatus) => {
            if (exitCode !== 0) {
                stats.gpu = null;
                stats.gpuAvailable = false;
            }
        }
    }
}
