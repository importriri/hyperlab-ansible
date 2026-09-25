// HyperLab IPC receivers (V447-C9.3).
//
// The only way into the shell from outside: fixed, argument-checked
// functions that summon presentation surfaces. A caller can open the command
// palette, open a product destination or ask the OSD to show a telemetry
// kind; it cannot pass a value, a command or a path, and nothing here starts
// a process.
//
//   qs -c hyperlab ipc call launcher toggle
//   qs -c hyperlab ipc call workspace machines
//   qs -c hyperlab ipc call workspace close
//   qs -c hyperlab ipc call osd show audio
//   qs -c hyperlab ipc call panel system
//   qs -c hyperlab ipc call session locking
//
// Compositor keybindings use these so the host shortcuts and the pointer
// reach exactly the same surfaces, on Hyprland and on Sway alike.

import Quickshell
import Quickshell.Io
import QtQuick

Scope {
    id: ipc

    required property var shellState
    required property var shellSurfaces
    required property var theme

    Timer {
        id: appearanceRefreshDebounce

        interval: 120
        repeat: false

        onTriggered: {
            ipc.theme.refreshPalette();
            ipc.shellState.refreshAppearanceState();
        }
    }

    IpcHandler {
        target: "launcher"

        function toggle(): string {
            ipc.shellSurfaces.toggleLauncher("");
            return ipc.shellSurfaces.launcherOpen ? "open" : "closed";
        }

        function open(): string {
            ipc.shellSurfaces.openLauncher("");
            return "open";
        }

        function close(): string {
            ipc.shellSurfaces.closeLauncher();
            return "closed";
        }
    }

    IpcHandler {
        target: "appearance"

        function refresh(): string {
            appearanceRefreshDebounce.restart();
            return "queued";
        }
    }

    IpcHandler {
        target: "osd"

        // The OSD shows the host's state for the kind, never a caller value.
        function show(kind: string): string {
            if (!ipc.shellSurfaces.showOsd(kind, ""))
                return "refused";

            if (String(kind) === "audio")
                ipc.shellState.refreshTelemetry();

            return "shown";
        }
    }

    IpcHandler {
        target: "workspace"

        function machines(): string {
            ipc.shellSurfaces.openWorkspace("machines");
            return "machines";
        }

        function controls(): string {
            ipc.shellSurfaces.openWorkspace("controls");
            return "controls";
        }

        function diagnostics(): string {
            ipc.shellSurfaces.openWorkspace("diagnostics");
            return "diagnostics";
        }

        function close(): string {
            ipc.shellSurfaces.closeWorkspace();
            return "closed";
        }
    }

    IpcHandler {
        target: "bar"

        function toggle(): string {
            ipc.shellSurfaces.toggleTopRail();
            return ipc.shellSurfaces.topRailVisible ? "visible" : "hidden";
        }

        function show(): string {
            ipc.shellSurfaces.showTopRail();
            return "visible";
        }

        function hide(): string {
            ipc.shellSurfaces.hideTopRail();
            return "hidden";
        }
    }

    // Sent by the shared lock helper on every lock path. It only withdraws
    // shell state; it cannot lock, unlock or run anything.
    IpcHandler {
        target: "session"

        function locking(): string {
            ipc.shellSurfaces.sessionLocking();
            return "dismissed";
        }
    }

    IpcHandler {
        target: "panel"

        function system(): string {
            ipc.shellSurfaces.toggleSystemPanel("");
            return ipc.shellSurfaces.systemPanelOpen ? "open" : "closed";
        }

        function dismiss(): string {
            ipc.shellSurfaces.dismissAll();
            return "closed";
        }
    }
}
