// HyperLab typed session actions (V447-C9.3).
//
// Product navigation is internal to ShellSurfaces. This bridge is reserved
// for reviewed host actions which really cross the QML/process boundary.
//
// No shell command is constructed from presentation data. Two shapes exist
// and no third is possible here:
//
//   * a fixed action identifier from `allowedActions`, which the bridge
//     resolves to an immutable argument vector it owns;
//   * one reviewed parameterised operation, workspace-select, whose only
//     argument is an integer validated here against the compositor's nine
//     slots and validated again by the bridge.
//
// Host actions are serialized through one runner, so two conflicting session
// operations cannot be in flight at once, and every operation reports its
// own result instead of looking successful because a process stopped.

import Quickshell
import Quickshell.Io
import QtQuick

Scope {
    id: actions

    readonly property string actionBridge:
        "/usr/local/bin/privatestack-shell-actions"

    readonly property var allowedActions: [
        "keyboard-cycle",
        "wallpaper-mode-toggle",
        "theme-cycle",
        "workspace-window-focus",
        "session-lock",
        "session-suspend",
        "session-logout",
        "session-reboot",
        "session-poweroff",
        "audio-mute-toggle",
        "audio-volume-up",
        "audio-volume-down"
    ]

    // The one reviewed operation that carries a value. The value is an
    // integer slot, never text a user typed.
    readonly property var parameterizedActions: [
        "workspace-select"
    ]

    readonly property int workspaceSlots: 9
    readonly property int queueLimit: 4

    property string activeAction: ""
    property var queue: []

    readonly property bool busy: actions.activeAction.length > 0

    signal actionStarted(string action)
    signal actionFinished(string action)
    signal actionResult(string action, bool ok, string detail)

    function labelFor(action) {
        switch (String(action)) {
        case "keyboard-cycle":
            return "Keyboard layout";
        case "wallpaper-mode-toggle":
            return "Wallpaper mode";
        case "theme-cycle":
            return "Theme";
        case "workspace-window-focus":
            return "Bring workspace forward";
        case "session-lock":
            return "Lock";
        case "session-suspend":
            return "Suspend";
        case "session-logout":
            return "Log out";
        case "session-reboot":
            return "Reboot";
        case "session-poweroff":
            return "Power off";
        case "audio-mute-toggle":
            return "Mute";
        case "audio-volume-up":
            return "Volume up";
        case "audio-volume-down":
            return "Volume down";
        case "workspace-select":
            return "Workspace";
        default:
            return "Action";
        }
    }

    function invoke(action) {
        const identifier = String(action);

        if (actions.allowedActions.indexOf(identifier) < 0) {
            console.warn("HyperLab refused an unknown shell action");
            actions.actionResult(
                identifier,
                false,
                "This action is not part of the reviewed host action set"
            );
            return false;
        }

        return actions.enqueue(identifier, []);
    }

    // The compositor slot is an integer, checked here and checked again by
    // the reviewed bridge. Nothing else may ever become an argument.
    function invokeWorkspace(slot) {
        const value = Number(slot);

        if (
            !Number.isInteger(value)
            || value < 1
            || value > actions.workspaceSlots
        ) {
            return false;
        }

        return actions.enqueue("workspace-select", [String(value)]);
    }

    function enqueue(identifier, argv) {
        if (actions.activeAction.length === 0) {
            actions.dispatch(identifier, argv);
            return true;
        }

        if (actions.queue.length >= actions.queueLimit)
            return false;

        const next = actions.queue.slice();
        next.push({ "action": identifier, "argv": argv });
        actions.queue = next;
        return true;
    }

    function dispatch(identifier, argv) {
        actions.activeAction = identifier;
        actions.actionStarted(identifier);
        runner.command = [actions.actionBridge, identifier].concat(argv);
        runner.running = true;
    }

    function drain() {
        if (actions.queue.length === 0) {
            actions.activeAction = "";
            return;
        }

        const next = actions.queue.slice();
        const entry = next.shift();
        actions.queue = next;
        actions.dispatch(entry.action, entry.argv);
    }

    Process {
        id: runner

        property string failureDetail: ""

        stderr: StdioCollector {
            onStreamFinished: {
                runner.failureDetail = String(this.text).trim();
            }
        }

        onExited: (exitCode, exitStatus) => {
            const action = actions.activeAction;
            const ok = exitCode === 0;

            actions.actionResult(
                action,
                ok,
                ok
                ? ""
                : (
                    runner.failureDetail.length > 0
                    ? runner.failureDetail
                    : "The host action bridge reported exit " + exitCode
                  )
            );

            // Readback happens whether the action succeeded or not: the shell
            // presents what the host now reports, never what it hoped for.
            actions.actionFinished(action);

            runner.failureDetail = "";
            actions.activeAction = "";
            actions.drain();
        }
    }
}
