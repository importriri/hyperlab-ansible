// The shell's IPC receivers. Key bindings reach the shell through
//   qs -c hyperlab-workspace ipc call workspace <function>
// and fall back to plain tools when the shell is not running.

import Quickshell.Io
import QtQuick

Item {
    id: ipc

    required property var surfaces
    required property var deskState

    visible: false

    IpcHandler {
        target: "workspace"

        function launcher(): string {
            ipc.surfaces.toggleLauncher();
            return ipc.surfaces.launcherOpen ? "open" : "closed";
        }

        function overview(): string {
            ipc.surfaces.toggleOverview();
            return ipc.surfaces.overviewOpen ? "open" : "closed";
        }

        function cheatsheet(): string {
            ipc.surfaces.toggleCheatsheet();
            return ipc.surfaces.cheatsheetOpen ? "open" : "closed";
        }

        function newProject(): string {
            ipc.surfaces.newProject();
            return "open";
        }

        function close(): string {
            ipc.surfaces.closeAll();
            return "closed";
        }

        function reload(): string {
            ipc.deskState.refreshModel();
            return "queued";
        }
    }
}
