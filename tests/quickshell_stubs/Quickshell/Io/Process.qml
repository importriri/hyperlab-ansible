import QtQuick
import Quickshell

// Answers from QsHarness.processes one event-loop turn after starting.
QtObject {
    id: process

    property var command: []
    property bool running: false
    property QtObject stdout: null
    property QtObject stderr: null

    signal exited(int exitCode, int exitStatus)

    function finish() {
        const reply = QsHarness.answer(process.command);
        if (process.stdout) {
            process.stdout.text = reply.stdout || "";
            process.stdout.streamFinished();
        }
        if (process.stderr) {
            process.stderr.text = reply.stderr || "";
            process.stderr.streamFinished();
        }
        process.running = false;
        process.exited(reply.code || 0, 0);
    }

    onRunningChanged: {
        if (running) {
            QsHarness.record(command);
            Qt.callLater(process.finish);
        }
    }
}
