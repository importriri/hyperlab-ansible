pragma Singleton
import QtQuick

// Fixtures and records shared by every stand-in.
QtObject {
    // command joined by spaces -> {stdout, stderr, code}
    property var processes: ({})
    // path -> text; a missing path fails to load
    property var files: ({})
    // every command the shell ran, in order
    property var commands: []
    // IPC handlers by target
    property var ipc: ({})
    property date now: new Date(2026, 9, 3, 16, 52)

    function record(argv) {
        commands = commands.concat([argv.join(" ")]);
    }

    function answer(argv) {
        const key = argv.join(" ");
        if (processes[key] !== undefined)
            return processes[key];
        for (const pattern in processes) {
            if (pattern.endsWith("*") && key.startsWith(pattern.slice(0, -1)))
                return processes[pattern];
        }
        return { "stdout": "", "stderr": "no fixture for " + key, "code": 127 };
    }
}
