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
//   lifecycle      start, shutdown, reboot, force stop: one serialized
//                  runner, so two conflicting power operations are never in
//                  flight at once;
//   connections    console, SSH, Looking Glass: the bridge becomes the client
//                  process and lives as long as the connection does, so each
//                  open connection has its own runner and never blocks
//                  lifecycle, capability reads or a connection to another
//                  machine.
//
// Nothing here is optimistic. A managed operation launches in its own
// terminal and outlives this process, so it is reported as `accepted`. A
// foreground operation reports `completed` only when the process it became
// actually finished; a connection reports `closed` when its client exits
// cleanly. A non-zero exit is a failure, never a success with a different
// colour.

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

        if (operationRunner.running)
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
            operationRunner.failureDetail = String(parsed.reason);
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

        stderr: StdioCollector {
            onStreamFinished: {
                const text = String(this.text).trim();

                if (text.length > 0 && operationRunner.failureDetail.length === 0)
                    operationRunner.failureDetail = text;
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
            } else if (mode === "detached" && exitCode === 0) {
                // The operation is running in its own terminal. Accepted is
                // the most this layer can truthfully say.
                phase = "accepted";
                detail = "Running in its own HyperLab operation terminal";
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

            machineActions.settled(verb, machine, phase, detail);
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
