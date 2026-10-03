// Desks, projects and where the user is, for every surface of the shell.
//
// Two sources, each with one job:
//
//   hyperlab-desk model   the validated Desks and projects (configuration)
//   Quickshell.Hyprland   the active workspace and window counts (live)
//
// Every change goes back through hyperlab-desk, the same helper the ALT key
// bindings call, so the keyboard, the dock and the overview can never
// disagree about what a Desk is. A helper failure is reported, never
// replaced by an empty machine.

import Quickshell
import Quickshell.Io
import Quickshell.Hyprland
import QtQuick
import "desks.js" as Desks

Item {
    id: state

    visible: false

    property string helper: "hyperlab-desk"

    // Configuration.
    property var model: ({ "desks": [] })
    property bool modelReady: false
    property string modelError: ""
    property var configErrors: []

    // Live compositor state.
    property int activeWorkspace: Hyprland.focusedWorkspace ? Hyprland.focusedWorkspace.id : 0
    property int countsRevision: 0
    readonly property var counts: {
        countsRevision;
        return Desks.countsFrom(Hyprland.workspaces.values);
    }

    readonly property var place: Desks.place(state.model, state.activeWorkspace)
    readonly property int currentDesk: place.desk
    readonly property int deskCount: state.model.desks.length

    // Last notice for the OSD: {text, detail, kind, serial}.
    property var notice: ({ "text": "", "detail": "", "kind": "", "serial": 0 })

    signal deskEntered(int desk)

    // Read at signal time, when the `place` binding may not have caught up.
    function placeNow() {
        return Desks.place(state.model, state.activeWorkspace);
    }

    function slotsOf(desk) {
        return Desks.slots(state.model, desk, state.counts, state.activeWorkspace);
    }

    function rowsOf(desk) {
        return Desks.projectRows(state.model, desk, state.counts, state.activeWorkspace);
    }

    function windowsOn(desk) {
        return Desks.deskWindows(desk, state.counts);
    }

    function announce(text, detail, kind) {
        state.notice = {
            "text": String(text),
            "detail": String(detail || ""),
            "kind": String(kind || "info"),
            "serial": state.notice.serial + 1
        };
    }

    // Navigation is fire-and-forget: its result is the workspace change
    // Hyprland reports back, which every surface already follows.
    function goDesk(desk) {
        if (desk >= 1 && desk <= state.deskCount)
            Quickshell.execDetached([state.helper, "desk", String(desk)]);
    }

    function goSlot(slot) {
        if (slot >= 1 && slot <= 9)
            Quickshell.execDetached([state.helper, "workspace", String(slot)]);
    }

    function openProject(desk, slot) {
        runner.request(["project-open", String(desk), String(slot)], "");
    }

    function newProject(desk, name) {
        const clean = String(name).trim();
        if (!clean.length)
            return;
        runner.request(
            ["project-new", String(desk), clean],
            "Project " + clean + " added to " + (Desks.deskAt(state.model, desk) || {}).name
        );
    }

    function refreshModel() {
        if (modelProcess.running)
            modelPending = true;
        else
            modelProcess.running = true;
    }

    property bool modelPending: false

    onActiveWorkspaceChanged: {
        const position = Desks.split(state.activeWorkspace);
        if (position && position.desk !== previousDesk) {
            previousDesk = position.desk;
            state.deskEntered(position.desk);
        }
    }
    property int previousDesk: 0

    Component.onCompleted: refreshModel()

    Process {
        id: modelProcess

        command: [state.helper, "model"]

        stdout: StdioCollector {
            onStreamFinished: {
                const parsed = Desks.parseModel(this.text);
                if (parsed.ok) {
                    state.model = parsed.model;
                    state.configErrors = parsed.errors;
                    state.modelError = "";
                    state.modelReady = true;
                } else {
                    state.modelError = parsed.error;
                }
            }
        }

        onExited: (exitCode, exitStatus) => {
            if (exitCode !== 0)
                state.modelError = "The Desk helper could not be run (exit " + exitCode + ").";
            if (state.modelPending) {
                state.modelPending = false;
                modelProcess.running = true;
            }
        }
    }

    // Mutations report their own outcome.
    Process {
        id: runner

        property var queue: []
        property string success: ""
        property string failure: ""

        function request(args, successText) {
            queue = queue.concat([{ "args": args, "success": successText }]);
            next();
        }

        function next() {
            if (running || queue.length === 0)
                return;
            const job = queue[0];
            queue = queue.slice(1);
            success = job.success;
            failure = "";
            command = [state.helper].concat(job.args);
            running = true;
        }

        stderr: StdioCollector {
            onStreamFinished: runner.failure = String(this.text).trim().replace(/^hyperlab-desk: /, "")
        }

        onExited: (exitCode, exitStatus) => {
            if (exitCode === 0) {
                if (runner.success.length)
                    state.announce(runner.success, "", "done");
                state.refreshModel();
            } else {
                state.announce("That did not work", runner.failure || ("exit " + exitCode), "error");
            }
            runner.next();
        }
    }

    // The user's own file; absent is normal, the helper then uses defaults.
    FileView {
        path: Quickshell.env("HOME") + "/.config/hyperlab-workspace/desks.json"
        watchChanges: true
        printErrors: false

        onFileChanged: state.refreshModel()
    }

    // The binding on `counts` reads each workspace's IPC object, so it
    // follows the refreshed objects as Hyprland answers; the revision only
    // covers a list that changed without any object changing.
    Timer {
        id: countsRefresh

        interval: 60
        onTriggered: {
            Hyprland.refreshWorkspaces();
            state.countsRevision += 1;
        }
    }

    Connections {
        target: Hyprland

        function onRawEvent(event) {
            const name = String(event.name);
            if (name.indexOf("window") >= 0 || name.indexOf("workspace") >= 0)
                countsRefresh.restart();
        }
    }
}
