// HyperLab typed machine operations (V447-C9.3).
//
// One boundary for everything done to a machine, and one boundary for asking
// what may be done to it. This object is transport only: it starts the
// reviewed bridge and reports exactly what came back. The observed answer to
// "what may be done" is ShellState's (applyCapabilityAnswer), and the bridge
// re-derives the same answer from live state before it acts.
//
// Three kinds of traffic, deliberately kept apart:
//
//   capabilities   one short-lived runner per request, each carrying its own
//                  immutable serial and machine, so a late or cancelled reply
//                  can never be mistaken for the current one;
//   lifecycle      a short dispatch, then per-machine durable operation
//                  records polled through the same typed bridge;
//   connections    console, SSH, Looking Glass: the bridge becomes the client
//                  process and lives as long as the connection does, so each
//                  open connection has its own runner and never blocks
//                  lifecycle, capability reads or a connection to another
//                  machine.
//
// Managed lifecycle is recovered from private operation records. The terminal
// belongs to a separate user unit. Inventory alone verifies machine state.

import Quickshell
import Quickshell.Io
import QtQuick

Scope {
    id: machineActions

    readonly property string bridge:
        "/usr/local/bin/privatestack-machine-actions"

    readonly property var verbs: [
        "start",
        "shutdown",
        "reboot",
        "console",
        "ssh",
        "looking-glass",
        "restart-capture",
        "force-stop"
    ]

    // Presentation order inside the selected machine, grouped by the decision
    // an operator is actually making.
    readonly property var connectVerbs: ["console", "ssh", "looking-glass"]
    // A Linux guest's Looking Glass capture, restarted without the guest.
    readonly property var streamVerbs: ["restart-capture"]
    readonly property var powerVerbs: ["start", "shutdown", "reboot"]
    readonly property var advancedVerbs: ["force-stop"]

    // Enough for real use; a runaway loop cannot fork unbounded clients.
    readonly property int connectionLimit: 6

    property alias machineInventory: operationState.inventory
    property alias inventoryObservedAt: operationState.inventoryObservedAt
    signal operationChanged(var record)
    signal inventoryRefreshRequested()

    OperationTracker {
        id: operationState
        onChanged: record => machineActions.operationChanged(record)
        onRefreshRequested: machineActions.inventoryRefreshRequested()
    }

    // Reopen the observer window of a still-running operation. Closing that
    // window never stopped the operation; this only attaches again.
    function activeOperationFor(machine) {
        return operationState.activeFor(String(machine));
    }
    function viewOperation(machine) {
        const record = operationState.activeFor(String(machine));
        if (record === null || operationView.running)
            return false;
        operationView.command = [machineActions.bridge, "operation-view", record.id];
        operationView.running = true;
        return true;
    }
    Process {
        id: operationView
    }

    function busyFor(machine) {
        return machineActions.pendingMachine === String(machine)
            || operationState.busyFor(String(machine));
    }

    signal accepted(string verb, string machine)
    signal settled(string verb, string machine, string phase, string detail)

    // Capability traffic. ShellState correlates and validates the answer.
    signal capabilityRequested(int serial, string machine, int generation)
    signal capabilityAnswered(
        int serial,
        string machine,
        string raw,
        int exitCode,
        string detail
    )
    signal capabilitiesCleared()

    function labelFor(verb) {
        switch (String(verb)) {
        case "start":
            return "Start";
        case "shutdown":
            return "Shut down";
        case "reboot":
            return "Reboot guest";
        case "console":
            return "Console";
        case "ssh":
            return "SSH";
        case "looking-glass":
            return "Looking Glass";
        case "restart-capture":
            return "Restart capture";
        case "force-stop":
            return "Force stop";
        case "power-cycle":
            return "Power cycle";
        case "reset":
            return "Reset";
        case "provision":
            return "Provision";
        case "seal":
            return "Seal";
        case "clipboard":
            return "Send clipboard";
        case "usb-allow":
            return "Allow USB device";
        default:
            return "Operation";
        }
    }

    function destructive(verb) {
        return machineActions.advancedVerbs.indexOf(String(verb)) >= 0;
    }

    function isConnection(verb) {
        return machineActions.connectVerbs.indexOf(String(verb)) >= 0;
    }

    // ------------------------------------------------------- capabilities

    property int capabilitySerial: 0
    // Inventory and per-verb registry reads each have a 15 s backend bound.
    // Keep a total budget for the whole sequence, not one CLI invocation.
    readonly property int capabilityTimeoutMs: 180000
    readonly property int capabilityStartTimeoutMs: 5000
    property var capabilityRunner: null

    function cancelCapabilityProbe() {
        const runner = machineActions.capabilityRunner;
        if (runner === null)
            return;
        machineActions.capabilityRunner = null;
        runner.answered = true;
        runner.deadline.stop();
        runner.startDeadline.stop();
        if (runner.running)
            runner.signal(9);
        else
            runner.destroy();
    }

    function probe(machine, generation) {
        const name = String(machine);

        if (name.length === 0) {
            machineActions.clearCapabilities();
            return false;
        }

        machineActions.capabilitySerial += 1;
        machineActions.cancelCapabilityProbe();

        const serial = machineActions.capabilitySerial;
        const observed = typeof generation === "number" ? generation : -1;

        machineActions.capabilityRequested(serial, name, observed);

        const runner = capabilityComponent.createObject(machineActions, {
            "serial": serial,
            "machine": name,
            "command": [machineActions.bridge, "capabilities", name]
        });

        if (runner === null) {
            machineActions.capabilityAnswered(
                serial,
                name,
                "",
                -1,
                "The machine bridge could not be started"
            );
            return false;
        }

        machineActions.capabilityRunner = runner;
        runner.deadline.start();
        runner.startDeadline.start();
        runner.running = true;
        return true;
    }

    // Supersedes any request in flight: its reply no longer matches.
    function clearCapabilities() {
        machineActions.capabilitySerial += 1;
        machineActions.cancelCapabilityProbe();
        machineActions.capabilitiesCleared();
    }

    Component {
        id: capabilityComponent

        Process {
            id: probeRunner

            // Set once at creation and never changed for the life of this
            // runner, so its reply always names the request it answers.
            property int serial: -1
            property string machine: ""

            property string buffer: ""
            property string detail: ""
            property bool answered: false

            function answer(raw, code, reason) {
                if (probeRunner.answered)
                    return;
                probeRunner.answered = true;
                probeRunner.deadline.stop();
                probeRunner.startDeadline.stop();
                if (machineActions.capabilityRunner === probeRunner)
                    machineActions.capabilityRunner = null;
                machineActions.capabilityAnswered(probeRunner.serial,
                    probeRunner.machine, raw, code, reason);
            }

            property Timer startDeadline: Timer {
                interval: machineActions.capabilityStartTimeoutMs
                onTriggered: {
                    // Failed QProcess starts do not emit exited.
                    if (probeRunner.running || probeRunner.answered)
                        return;
                    probeRunner.answer("", -1, "The machine bridge could not start at "
                        + machineActions.bridge + "; check installation and execute permission");
                    probeRunner.destroy();
                }
            }

            property Timer deadline: Timer {
                interval: machineActions.capabilityTimeoutMs
                onTriggered: {
                    probeRunner.answer("", -1, "The machine bridge timed out while reading capabilities");
                    if (probeRunner.running)
                        probeRunner.signal(9);
                    else
                        probeRunner.destroy();
                }
            }

            stdout: StdioCollector {
                onStreamFinished: {
                    probeRunner.buffer = String(this.text);
                }
            }

            stderr: StdioCollector {
                onStreamFinished: {
                    probeRunner.detail = String(this.text).trim();
                }
            }

            onExited: (exitCode, exitStatus) => {
                probeRunner.answer(probeRunner.buffer,
                    exitStatus === 0 ? exitCode : -1,
                    exitStatus === 0 ? probeRunner.detail : "The machine bridge was interrupted");
                probeRunner.destroy();
            }
        }
    }

    // --------------------------------------------------------- diagnostics

    // Independent of short capability/dispatch traffic and open connections.
    // The collector has 660 s; allow short identity reads and cleanup as well.
    readonly property int diagnosticsTimeoutMs: 750000
    readonly property int diagnosticsStartTimeoutMs: 5000
    property int diagnosticsSerial: 0
    property var diagnosticsRunner: null
    readonly property bool diagnosticsBusy: machineActions.diagnosticsRunner !== null
    signal diagnosticsRequested(string requestId, string machine)
    signal diagnosticsAnswered(string requestId, string machine, string raw, int exitCode, string detail)

    function collectDiagnostics(machine) {
        const name = String(machine);
        if (machineActions.diagnosticsBusy || !/^[a-z0-9][a-z0-9-]{1,30}$/.test(name))
            return false;
        machineActions.diagnosticsSerial += 1;
        const requestId = "diagnostics-" + machineActions.diagnosticsSerial;
        const runner = diagnosticsComponent.createObject(machineActions, {
            "requestId": requestId, "machine": name,
            "command": [machineActions.bridge, "diagnostics", name, requestId]
        });
        machineActions.diagnosticsRequested(requestId, name);
        if (runner === null) {
            machineActions.diagnosticsAnswered(requestId, name, "", -1,
                "Diagnostics could not be started");
            return false;
        }
        machineActions.diagnosticsRunner = runner;
        runner.deadline.start();
        runner.startDeadline.start();
        runner.running = true;
        return true;
    }

    function finishDiagnostics(runner, exitCode, exitStatus) {
        if (machineActions.diagnosticsRunner !== runner)
            return;
        runner.deadline.stop();
        runner.startDeadline.stop();
        runner.killDeadline.stop();
        machineActions.diagnosticsRunner = null;
        if (!runner.answered) {
            runner.answered = true;
            const interrupted = exitStatus !== 0;
            machineActions.diagnosticsAnswered(runner.requestId, runner.machine,
                exitCode === 0 && !interrupted ? runner.buffer : "",
                interrupted ? -1 : exitCode,
                interrupted ? "Diagnostics collection was interrupted"
                : exitCode !== 0 ? "Diagnostics could not be collected" : "");
        }
        runner.destroy();
    }

    function expireDiagnostics(runner) {
        if (machineActions.diagnosticsRunner !== runner || runner.answered)
            return;
        runner.answered = true;
        machineActions.diagnosticsAnswered(runner.requestId, runner.machine, "", -1,
            "Diagnostics collection timed out");
        if (runner.running) {
            // The bridge terminates and reaps its collector's process group.
            runner.signal(15);
            runner.killDeadline.start();
        } else {
            machineActions.finishDiagnostics(runner, -1, 0);
        }
    }

    Component {
        id: diagnosticsComponent
        Process {
            id: collectionRunner
            // Set once at creation. Selection never changes these fields.
            property string requestId: ""
            property string machine: ""
            property string buffer: ""
            property bool answered: false
            stdout: StdioCollector {
                onStreamFinished: collectionRunner.buffer = String(this.text)
            }
            // No stderr or raw collector contents reach a presentation signal.
            stderr: StdioCollector {}
            onExited: (exitCode, exitStatus) =>
                machineActions.finishDiagnostics(collectionRunner, exitCode, exitStatus)
            // A failed QProcess start need not emit exited. Inspect actual
            // running state once, without shortening a running collection.
            property Timer startDeadline: Timer {
                interval: machineActions.diagnosticsStartTimeoutMs
                onTriggered: {
                    if (machineActions.diagnosticsRunner !== collectionRunner
                            || collectionRunner.running || collectionRunner.answered)
                        return;
                    collectionRunner.answered = true;
                    machineActions.diagnosticsAnswered(collectionRunner.requestId,
                        collectionRunner.machine, "", -1, "Diagnostics could not be started");
                    machineActions.finishDiagnostics(collectionRunner, -1, 0);
                }
            }
            property Timer deadline: Timer {
                id: collectionDeadline
                interval: machineActions.diagnosticsTimeoutMs
                onTriggered: machineActions.expireDiagnostics(collectionRunner)
            }
            property Timer killDeadline: Timer {
                id: collectionKill
                interval: 5000
                onTriggered: {
                    collectionRunner.signal(9);
                    machineActions.finishDiagnostics(collectionRunner, -1, 1);
                }
            }
        }
    }

    // ------------------------------------------------------- stream health

    // Read only, one runner per request, each with its own serial: ShellState
    // adopts only the answer to the question it last asked (ADR 0045).
    property int streamHealthSerial: 0

    signal streamHealthRequested(int serial, string machine)
    signal streamHealthAnswered(
        int serial,
        string machine,
        string raw,
        int exitCode,
        string detail
    )

    function checkStream(machine) {
        const name = String(machine);

        if (name.length === 0)
            return false;

        machineActions.streamHealthSerial += 1;

        const serial = machineActions.streamHealthSerial;

        machineActions.streamHealthRequested(serial, name);

        const runner = streamHealthComponent.createObject(machineActions, {
            "serial": serial,
            "machine": name,
            "command": [machineActions.bridge, "stream-health", name]
        });

        if (runner === null) {
            machineActions.streamHealthAnswered(
                serial,
                name,
                "",
                -1,
                "The machine bridge could not be started"
            );
            return false;
        }

        runner.running = true;
        return true;
    }

    Component {
        id: streamHealthComponent

        Process {
            id: healthRunner

            property int serial: -1
            property string machine: ""

            property string buffer: ""
            property string detail: ""

            stdout: StdioCollector {
                onStreamFinished: {
                    healthRunner.buffer = String(this.text);
                }
            }

            stderr: StdioCollector {
                onStreamFinished: {
                    healthRunner.detail = String(this.text).trim();
                }
            }

            onExited: (exitCode, exitStatus) => {
                machineActions.streamHealthAnswered(
                    healthRunner.serial,
                    healthRunner.machine,
                    healthRunner.buffer,
                    exitCode,
                    healthRunner.detail
                );
                healthRunner.destroy();
            }
        }
    }

    // ---------------------------------------------------------- lifecycle

    property string pendingVerb: ""
    property string pendingMachine: ""
    property string pendingMode: ""
    property string pendingPhase: ""

    // Lifecycle only. An open connection never makes this true.
    readonly property bool busy: machineActions.pendingVerb.length > 0

    function invoke(verb, machine) {
        const operation = String(verb);
        const name = String(machine);

        if (
            (machineActions.verbs.indexOf(operation) < 0
                && machineActions.workbenchVerbs.indexOf(operation) < 0)
            || name.length === 0
        ) {
            return false;
        }

        if (machineActions.isConnection(operation))
            return machineActions.openConnection(operation, name);

        if (operationRunner.running || machineActions.busyFor(name))
            return false;

        return machineActions.dispatch(operation, name,
            [machineActions.bridge, operation, name]);
    }

    // One short dispatch through the bridge; what it answers is tracked by
    // applyOperationLine against this verb and target.
    function dispatch(operation, target, command) {
        machineActions.pendingVerb = operation;
        machineActions.pendingMachine = target;
        machineActions.pendingMode = "";
        machineActions.pendingPhase = "";
        operationRunner.failureDetail = "";
        operationRunner.command = command;
        operationRunner.running = true;
        return true;
    }

    function parseLine(raw) {
        try {
            const parsed = JSON.parse(String(raw).trim());

            return parsed !== null
                && typeof parsed === "object"
                && !Array.isArray(parsed)
                ? parsed
                : null;
        } catch (error) {
            return null;
        }
    }

    function applyOperationLine(raw) {
        const parsed = machineActions.parseLine(raw);

        if (parsed === null)
            return;

        if (operationState.valid(parsed)) {
            if (parsed.machine !== machineActions.pendingMachine
                || operationState.actionVerbs[parsed.action_id] !== machineActions.pendingVerb)
                return;
            machineActions.pendingPhase = "dispatched";
            machineActions.pendingMode = "operation";
            operationState.apply(parsed, parsed.operation_id);
            return;
        }

        if (parsed.phase === "accepted") {
            machineActions.pendingPhase = "accepted";
            machineActions.pendingMode = String(parsed.mode);
            machineActions.accepted(
                machineActions.pendingVerb,
                machineActions.pendingMachine
            );
            return;
        }

        if (parsed.phase === "refused") {
            const usb = machineActions.pendingVerb === "usb-allow";

            machineActions.pendingPhase = "refused";
            // A USB refusal names its reason (a keyboard, a device that is
            // no longer blocked); the operator has nothing else to act on.
            operationRunner.failureDetail = parsed.reason === "operation-in-progress"
                ? "An operation is already in progress for this "
                    + (usb ? "device" : "machine")
                : usb && String(parsed.reason || "").length > 0
                ? String(parsed.reason).slice(0, 300)
                : "The machine operation was refused";
        }
    }

    Process {
        id: operationRunner

        property string failureDetail: ""

        stdout: SplitParser {
            onRead: data => {
                machineActions.applyOperationLine(data);
            }
        }

        onExited: (exitCode, exitStatus) => {
            const verb = machineActions.pendingVerb;
            const machine = machineActions.pendingMachine;
            const mode = machineActions.pendingMode;

            let phase = "failed";
            let detail = operationRunner.failureDetail;

            if (machineActions.pendingPhase === "refused") {
                phase = "refused";
            } else if (exitCode === 0 && machineActions.pendingPhase === "accepted") {
                phase = "completed";
                detail = "";
            } else if (detail.length === 0) {
                detail =
                    exitCode === 0
                    ? "The machine bridge did not report an outcome"
                    : "The machine bridge reported exit " + exitCode;
            }

            machineActions.pendingVerb = "";
            machineActions.pendingMachine = "";
            machineActions.pendingMode = "";
            machineActions.pendingPhase = "";
            operationRunner.failureDetail = "";

            if (mode !== "operation")
                machineActions.settled(verb, machine, phase, detail);
        }
    }

    // Also covers failed-to-start, where QProcess may never emit exited.
    Timer {
        interval: 90000
        running: machineActions.pendingVerb.length > 0
        repeat: false
        onTriggered: {
            if (operationRunner.running) {
                operationRunner.signal(9);
                return;
            }
            const verb = machineActions.pendingVerb;
            const machine = machineActions.pendingMachine;
            machineActions.pendingVerb = "";
            machineActions.pendingMachine = "";
            machineActions.pendingMode = "";
            machineActions.pendingPhase = "";
            machineActions.settled(verb, machine, "failed", "Machine bridge unavailable");
        }
    }

    // One snapshot poll in flight. A bridge failure preserves unresolved busy
    // state, and disables new lifecycle requests until discovery recovers.
    Process {
        id: operationStatus
        command: [machineActions.bridge, "operations"]
        property string buffer: ""
        onStarted: { buffer = ""; statusDeadline.restart(); }
        stdout: StdioCollector {
            onStreamFinished: operationStatus.buffer = String(this.text)
        }
        onExited: (exitCode, exitStatus) => {
            statusDeadline.stop();
            if (exitCode !== 0)
                operationState.known = false;
            else
                operationState.snapshot(machineActions.parseLine(operationStatus.buffer));
        }
    }
    Timer {
        id: statusDeadline
        interval: 15000
        onTriggered: {
            operationState.known = false;
            operationStatus.signal(9);
        }
    }
    Timer {
        interval: 2000
        running: true
        triggeredOnStart: true
        repeat: true
        onTriggered: {
            operationState.now = Date.now();
            if (!operationStatus.running && !statusDeadline.running) {
                // Arm before starting: failed-to-start has no onStarted.
                statusDeadline.start();
                operationStatus.running = true;
            }
            if (operationState.records.some(r => r.phase === "verifying"))
                machineActions.inventoryRefreshRequested();
            // An allowed device is verified only by a fresh USB reading,
            // whether or not the USB devices view is open.
            if (operationState.records.some(r => r.phase === "verifying" && r.verb === "usb-allow"))
                machineActions.requestUsb();
        }
    }

    // ---------------------------------------------------------- clipboard
    //
    // One host-to-guest send to one named Machine (ADR 0020). The bridge
    // reads the host clipboard itself and pipes it over the pinned SSH
    // channel; the text never passes through the shell. The outcome is
    // reported through settled() like a lifecycle verb.

    property string clipboardMachine: ""
    property string clipboardPhase: ""
    property string clipboardDetail: ""

    function sendClipboard(machine) {
        const name = String(machine);

        if (
            clipboardRunner.running
            || machineActions.clipboardMachine.length > 0
            || !/^[A-Za-z0-9][A-Za-z0-9_.-]{0,62}$/.test(name)
        )
            return false;

        machineActions.clipboardMachine = name;
        machineActions.clipboardPhase = "";
        machineActions.clipboardDetail = "";
        clipboardRunner.command = [machineActions.bridge, "clipboard", name];
        clipboardRunner.running = true;
        return true;
    }

    Process {
        id: clipboardRunner

        stdout: SplitParser {
            onRead: data => {
                const parsed = machineActions.parseLine(data);

                if (parsed === null)
                    return;
                if (parsed.phase === "accepted")
                    machineActions.clipboardPhase = "accepted";
                else if (parsed.phase === "refused") {
                    machineActions.clipboardPhase = "refused";
                    machineActions.clipboardDetail = String(parsed.reason || "").slice(0, 300);
                }
            }
        }

        stderr: StdioCollector {
            onStreamFinished: {
                const text = String(this.text).trim();

                if (text.length > 0 && machineActions.clipboardDetail.length === 0)
                    machineActions.clipboardDetail = text.split("\n").pop().slice(0, 300);
            }
        }

        onExited: (exitCode, exitStatus) => {
            const machine = machineActions.clipboardMachine;
            const phase =
                machineActions.clipboardPhase === "refused" ? "refused"
                : machineActions.clipboardPhase === "accepted" && exitCode === 0 ? "completed"
                : "failed";
            const detail =
                phase === "completed" ? ""
                : machineActions.clipboardDetail.length > 0 ? machineActions.clipboardDetail
                : "The clipboard send reported exit " + exitCode;

            machineActions.clipboardMachine = "";
            machineActions.settled("clipboard", machine, phase, detail);
        }
    }

    // ----------------------------------------------------------- creation
    //
    // Two short requests (ADR 0017). create-plan reports what the factory
    // allows; ShellState validates it. create hands positional values to the
    // bridge, which records and projects the Machine and launches its durable
    // provisioning operation; the record that comes back is tracked like any
    // other operation. No password crosses here: the provisioner asks for it
    // in the operation window.

    signal createPlanRequested()
    signal createPlanAnswered(string raw, int exitCode, string detail)

    property string createMachine: ""
    property string createPhase: ""
    property string createDetail: ""
    property bool creating: false

    function requestCreatePlan() {
        if (createPlanRunner.running)
            return false;
        machineActions.createPlanRequested();
        createPlanRunner.buffer = "";
        createPlanRunner.detail = "";
        createPlanRunner.running = true;
        return true;
    }

    // args: [TEMPLATE, NAME, LIFECYCLE, NETWORK, PROFILE, (MEMORY, VCPUS,
    // DISK)], built by ShellState.createArguments; the bridge validates them
    // again.
    function submitCreate(args) {
        if (
            machineActions.creating
            || !Array.isArray(args)
            || (args.length !== 5 && args.length !== 8)
            || !args.every(value => typeof value === "string"
                && /^[a-z0-9][a-z0-9-]{0,63}$/.test(value))
        )
            return false;

        machineActions.createMachine = args[1];
        machineActions.creating = true;
        machineActions.createPhase = "pending";
        machineActions.createDetail = "";
        createRunner.command = [machineActions.bridge, "create"].concat(args);
        createRunner.running = true;
        return true;
    }

    function applyCreateLine(raw) {
        const parsed = machineActions.parseLine(raw);

        if (parsed === null)
            return;

        if (
            operationState.valid(parsed)
            && parsed.action_id === "machine.provision"
            && parsed.machine === machineActions.createMachine
        ) {
            operationState.apply(parsed, parsed.operation_id);
            machineActions.createPhase =
                parsed.phase === "failed" ? "failed" : "dispatched";
            machineActions.createDetail =
                parsed.phase === "failed"
                ? "The provisioning operation could not start"
                : "";
            return;
        }

        if (parsed.phase === "refused") {
            machineActions.createPhase = "refused";
            machineActions.createDetail =
                parsed.reason === "operation-in-progress"
                ? "An operation is already in progress for this Machine"
                : String(parsed.reason || "The bridge refused the request").slice(0, 400);
        }
    }

    Process {
        id: createPlanRunner

        property string buffer: ""
        property string detail: ""

        command: [machineActions.bridge, "create-plan"]

        stdout: StdioCollector {
            onStreamFinished: createPlanRunner.buffer = String(this.text)
        }

        stderr: StdioCollector {
            onStreamFinished: createPlanRunner.detail = String(this.text).trim()
        }

        onExited: (exitCode, exitStatus) => {
            machineActions.createPlanAnswered(
                createPlanRunner.buffer,
                exitCode,
                createPlanRunner.detail
            );
        }
    }

    Process {
        id: createRunner

        stdout: SplitParser {
            onRead: data => machineActions.applyCreateLine(data)
        }

        onExited: (exitCode, exitStatus) => {
            machineActions.creating = false;
            if (machineActions.createPhase === "pending") {
                machineActions.createPhase = "failed";
                machineActions.createDetail =
                    "The machine bridge reported exit " + exitCode;
            }
        }
    }

    // Also covers failed-to-start, where QProcess may never emit exited.
    Timer {
        interval: 120000
        running: machineActions.creating
        repeat: false
        onTriggered: {
            if (createRunner.running) {
                createRunner.signal(9);
                return;
            }
            machineActions.creating = false;
            if (machineActions.createPhase === "pending") {
                machineActions.createPhase = "failed";
                machineActions.createDetail = "Machine bridge unavailable";
            }
        }
    }

    // ----------------------------------------------------------- Workbench

    // Golden Image candidates (ADR 0015), never product Machines. The list
    // is presentation only: the bridge checks a seal again against the
    // registry and live state before it hands it to the operation runner,
    // and the tracker verifies a seal only against a fresh reading of it.
    readonly property var workbenchVerbs: ["seal"]
    property var workbenchCandidates: []
    property var workbenchErrors: []
    // unknown until the bridge answers; ready, empty or unavailable after.
    property string workbenchState: "unknown"
    property string workbenchDetail: ""

    function requestWorkbench() {
        if (workbenchRunner.running)
            return false;
        workbenchRunner.buffer = "";
        workbenchRunner.detail = "";
        workbenchRunner.running = true;
        return true;
    }

    function validCandidate(row) {
        return row !== null && typeof row === "object"
            && typeof row.domain === "string" && /^[a-z0-9][a-z0-9-]{0,62}$/.test(row.domain)
            && typeof row.image_id === "string" && /^[a-z0-9][a-z0-9-]{0,62}$/.test(row.image_id)
            && ["candidate", "captured"].indexOf(row.state) >= 0
            && typeof row.runtime === "string" && row.runtime.length <= 32
            && (row.sha256 === null || (typeof row.sha256 === "string" && /^[0-9a-f]{64}$/.test(row.sha256)));
    }

    function applyWorkbench(text, exitCode, detail) {
        let parsed = null;
        try {
            parsed = JSON.parse(String(text));
        } catch (error) {
            parsed = null;
        }
        if (
            exitCode !== 0 || parsed === null || parsed.phase !== "workbench"
            || !Array.isArray(parsed.candidates)
            || !parsed.candidates.every(row => machineActions.validCandidate(row))
        ) {
            machineActions.workbenchState = "unavailable";
            machineActions.workbenchDetail = String(detail || "").replace(/^HyperLab: /, "").slice(0, 300)
                || "The Workbench could not be read";
            return false;
        }
        machineActions.workbenchCandidates = parsed.candidates;
        machineActions.workbenchErrors = Array.isArray(parsed.errors)
            ? parsed.errors.map(error => String(error).slice(0, 300)) : [];
        machineActions.workbenchState = parsed.candidates.length ? "ready" : "empty";
        machineActions.workbenchDetail = "";
        operationState.workbench = parsed.candidates;
        operationState.workbenchObservedAt = Date.now();
        return true;
    }

    Process {
        id: workbenchRunner

        property string buffer: ""
        property string detail: ""

        command: [machineActions.bridge, "workbench"]

        stdout: StdioCollector {
            onStreamFinished: workbenchRunner.buffer = String(this.text)
        }

        stderr: StdioCollector {
            onStreamFinished: workbenchRunner.detail = String(this.text).trim()
        }

        onExited: (exitCode, exitStatus) => {
            machineActions.applyWorkbench(workbenchRunner.buffer, exitCode, workbenchRunner.detail);
        }
    }

    // --------------------------------------------------------- USB devices

    // The host's USB devices (ADR 0038), never Machines. The list is
    // presentation only: the bridge reads it again before an allow and
    // refuses a device that is not blocked or presents a keyboard or mouse,
    // and the playbook checks the device once more as root. An allow is a
    // durable operation whose record names the device as
    // usb:PORT:SCOPE:VVVV:PPPP, bound to the vendor:product shown; the
    // tracker verifies it only against a fresh reading of the list.
    readonly property var usbScopes: ["once", "permanent"]
    property var usbDevices: []
    // unknown until the bridge answers; ready, empty or unavailable after.
    property string usbState: "unknown"
    property string usbDetail: ""

    function requestUsb() {
        if (usbRunner.running)
            return false;
        usbRunner.buffer = "";
        usbRunner.detail = "";
        usbRunner.running = true;
        return true;
    }

    function validUsbPort(port) {
        return typeof port === "string" && port.length <= 32
            && /^[0-9]+-[0-9]+(\.[0-9]+)*$/.test(port);
    }

    function validUsbDevice(row) {
        const text = value => value === null || (typeof value === "string" && value.length <= 128);
        return row !== null && typeof row === "object"
            && machineActions.validUsbPort(row.port)
            && typeof row.vendor_id === "string" && /^[0-9a-f]{4}$/.test(row.vendor_id)
            && (row.product_id === null
                || (typeof row.product_id === "string" && /^[0-9a-f]{4}$/.test(row.product_id)))
            && text(row.manufacturer) && text(row.product) && text(row.serial)
            && (row.authorized === 0 || row.authorized === 1 || row.authorized === null)
            && Array.isArray(row.interfaces)
            && row.interfaces.every(value => typeof value === "string" && /^[0-9a-f]{2}$/.test(value))
            && typeof row.hid === "boolean";
    }

    function applyUsb(text, exitCode, detail) {
        let parsed = null;
        try {
            parsed = JSON.parse(String(text));
        } catch (error) {
            parsed = null;
        }
        if (
            exitCode !== 0 || parsed === null || parsed.phase !== "usb"
            || !Array.isArray(parsed.devices)
            || !parsed.devices.every(row => machineActions.validUsbDevice(row))
        ) {
            machineActions.usbState = "unavailable";
            machineActions.usbDetail = String(detail || "").replace(/^HyperLab: /, "").slice(0, 300)
                || "The USB devices could not be read";
            return false;
        }
        machineActions.usbDevices = parsed.devices;
        machineActions.usbState = parsed.devices.length ? "ready" : "empty";
        machineActions.usbDetail = "";
        operationState.usb = parsed.devices;
        operationState.usbObservedAt = Date.now();
        return true;
    }

    // The device the operator saw, as vendor:product. An allow is bound to
    // it, so a different device plugged into the same port is refused.
    function validUsbIdentity(device) {
        return typeof device === "string" && /^[0-9a-f]{4}:[0-9a-f]{4}$/.test(device);
    }

    function usbTarget(port, scope, device) {
        return "usb:" + String(port) + ":" + String(scope) + ":" + String(device);
    }

    // The port a usb:PORT:SCOPE:VVVV:PPPP target names, or "".
    function usbPort(target) {
        const parts = String(target).split(":");
        return parts.length === 5 && parts[0] === "usb" ? parts[1] : "";
    }

    // Any operation still open on this port, whatever its scope or device.
    // Until the operation records are known, every port is busy.
    function usbBusy(port) {
        const name = String(port);
        return !operationState.known
            || machineActions.usbPort(machineActions.pendingMachine) === name
            || operationState.records.some(r => r.verb === "usb-allow"
                && !operationState.terminal(r.phase)
                && machineActions.usbPort(r.machine) === name);
    }

    function allowUsb(port, scope, device) {
        const name = String(port);
        const how = String(scope);

        if (
            !machineActions.validUsbPort(name)
            || machineActions.usbScopes.indexOf(how) < 0
            || !machineActions.validUsbIdentity(device)
            || operationRunner.running
            || machineActions.usbBusy(name)
        )
            return false;

        return machineActions.dispatch("usb-allow", machineActions.usbTarget(name, how, device),
            [machineActions.bridge, "usb-allow", name, how, device]);
    }

    Process {
        id: usbRunner

        property string buffer: ""
        property string detail: ""

        command: [machineActions.bridge, "usb"]

        stdout: StdioCollector {
            onStreamFinished: usbRunner.buffer = String(this.text)
        }

        stderr: StdioCollector {
            onStreamFinished: usbRunner.detail = String(this.text).trim()
        }

        onExited: (exitCode, exitStatus) => {
            machineActions.applyUsb(usbRunner.buffer, exitCode, usbRunner.detail);
        }
    }

    // ------------------------------------------------------ emergency stop

    // The emergency stop (ADR 0047) is engaged by a host key, never from
    // here. This transport only reads it, every few seconds so the shell
    // shows a stop soon after the key, and runs the restore once the shell
    // has had it confirmed. ShellState decides what an answer means.
    signal panicAnswered(string raw, int exitCode, string detail)
    signal panicRestoreRequested()
    signal panicRestoreAnswered(string raw, int exitCode, string detail)

    function requestPanicStatus() {
        if (panicRunner.running || panicRestoreRunner.running)
            return false;
        panicRunner.buffer = "";
        panicRunner.detail = "";
        panicRunner.running = true;
        return true;
    }

    function restorePanic() {
        if (panicRestoreRunner.running)
            return false;
        machineActions.panicRestoreRequested();
        panicRestoreRunner.buffer = "";
        panicRestoreRunner.detail = "";
        panicRestoreRunner.running = true;
        return true;
    }

    Process {
        id: panicRunner

        property string buffer: ""
        property string detail: ""

        command: [machineActions.bridge, "panic-status"]

        stdout: StdioCollector {
            onStreamFinished: panicRunner.buffer = String(this.text)
        }

        stderr: StdioCollector {
            onStreamFinished: panicRunner.detail = String(this.text).trim()
        }

        onExited: (exitCode, exitStatus) => {
            machineActions.panicAnswered(panicRunner.buffer, exitCode, panicRunner.detail);
        }
    }

    Process {
        id: panicRestoreRunner

        property string buffer: ""
        property string detail: ""

        command: [machineActions.bridge, "panic-restore"]

        stdout: StdioCollector {
            onStreamFinished: panicRestoreRunner.buffer = String(this.text)
        }

        stderr: StdioCollector {
            onStreamFinished: panicRestoreRunner.detail = String(this.text).trim()
        }

        onExited: (exitCode, exitStatus) => {
            machineActions.panicRestoreAnswered(
                panicRestoreRunner.buffer, exitCode, panicRestoreRunner.detail);
            // Resumed Machines change state; read the host back.
            machineActions.inventoryRefreshRequested();
        }
    }

    Timer {
        interval: 5000
        running: true
        repeat: true
        triggeredOnStart: true
        onTriggered: machineActions.requestPanicStatus()
    }

    // -------------------------------------------------------- connections

    // One entry per open connection: "<verb>\n<machine>".
    property var connections: []

    function connectionKey(verb, machine) {
        return String(verb) + "\n" + String(machine);
    }

    function connectionActive(machine, verb) {
        return machineActions.connections.indexOf(
            machineActions.connectionKey(verb, machine)
        ) >= 0;
    }

    function openConnection(verb, machine) {
        const key = machineActions.connectionKey(verb, machine);

        // The same transport to the same machine is already open.
        if (machineActions.connections.indexOf(key) >= 0)
            return false;

        if (machineActions.connections.length >= machineActions.connectionLimit)
            return false;

        const runner = connectionComponent.createObject(machineActions, {
            "verb": verb,
            "machine": machine,
            "command": [machineActions.bridge, verb, machine]
        });

        if (runner === null)
            return false;

        machineActions.connections = machineActions.connections.concat([key]);
        runner.running = true;
        return true;
    }

    function releaseConnection(verb, machine) {
        const key = machineActions.connectionKey(verb, machine);

        machineActions.connections =
            machineActions.connections.filter(entry => entry !== key);
    }

    Component {
        id: connectionComponent

        Process {
            id: connectionRunner

            // Set once at creation.
            property string verb: ""
            property string machine: ""

            property string phase: ""
            property string failureDetail: ""

            stdout: SplitParser {
                onRead: data => {
                    const parsed = machineActions.parseLine(data);

                    if (parsed === null)
                        return;

                    if (parsed.phase === "accepted") {
                        connectionRunner.phase = "accepted";
                        machineActions.accepted(
                            connectionRunner.verb,
                            connectionRunner.machine
                        );
                    } else if (parsed.phase === "refused") {
                        connectionRunner.phase = "refused";
                        connectionRunner.failureDetail = String(parsed.reason);
                    }
                }
            }

            stderr: StdioCollector {
                onStreamFinished: {
                    const text = String(this.text).trim();

                    if (
                        text.length > 0
                        && connectionRunner.failureDetail.length === 0
                    )
                        connectionRunner.failureDetail = text;
                }
            }

            onExited: (exitCode, exitStatus) => {
                let phase = "failed";
                let detail = connectionRunner.failureDetail;

                if (connectionRunner.phase === "refused") {
                    phase = "refused";
                } else if (connectionRunner.phase === "accepted" && exitCode === 0) {
                    // The client ran and ended normally: the connection was
                    // closed, which is not the same as an operation completing.
                    phase = "closed";
                    detail = "Connection closed";
                } else if (detail.length === 0) {
                    detail = "The connection client reported exit " + exitCode;
                }

                machineActions.releaseConnection(
                    connectionRunner.verb,
                    connectionRunner.machine
                );
                machineActions.settled(
                    connectionRunner.verb,
                    connectionRunner.machine,
                    phase,
                    detail
                );
                connectionRunner.destroy();
            }
        }
    }
}
