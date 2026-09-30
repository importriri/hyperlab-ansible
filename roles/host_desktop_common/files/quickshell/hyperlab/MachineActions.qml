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
        "force-stop"
    ]

    // Presentation order inside the selected machine, grouped by the decision
    // an operator is actually making.
    readonly property var connectVerbs: ["console", "ssh", "looking-glass"]
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
        case "force-stop":
            return "Force stop";
        case "power-cycle":
            return "Power cycle";
        case "reset":
            return "Reset";
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

    function probe(machine, generation) {
        const name = String(machine);

        if (name.length === 0) {
            machineActions.clearCapabilities();
            return false;
        }

        machineActions.capabilitySerial += 1;

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

        runner.running = true;
        return true;
    }

    // Supersedes any request in flight: its reply no longer matches.
    function clearCapabilities() {
        machineActions.capabilitySerial += 1;
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
                machineActions.capabilityAnswered(
                    probeRunner.serial,
                    probeRunner.machine,
                    probeRunner.buffer,
                    exitCode,
                    probeRunner.detail
                );
                probeRunner.destroy();
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
            machineActions.verbs.indexOf(operation) < 0
            || name.length === 0
        ) {
            return false;
        }

        if (machineActions.isConnection(operation))
            return machineActions.openConnection(operation, name);

        if (operationRunner.running || machineActions.busyFor(name))
            return false;

        machineActions.pendingVerb = operation;
        machineActions.pendingMachine = name;
        machineActions.pendingMode = "";
        machineActions.pendingPhase = "";
        operationRunner.failureDetail = "";
        operationRunner.command = [machineActions.bridge, operation, name];
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
            machineActions.pendingPhase = "refused";
            operationRunner.failureDetail = parsed.reason === "operation-in-progress"
                ? "An operation is already in progress for this machine"
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
        }
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
