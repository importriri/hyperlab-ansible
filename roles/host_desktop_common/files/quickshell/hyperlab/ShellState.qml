// HyperLab shared shell runtime state (V447-C9.3).
//
// This is the only file that reads host runtime data. Presentation files
// receive plain values and never open a process, a socket or a file.
//
// Every source is a reviewed read-only bridge:
//   privatestack-hyperlab              status, trust claim and inventory
//   privatestack-compositor-adapter    compositor-neutral workspace/focus
//   privatestack-telemetry             host telemetry snapshot
//   ~/.config/hyperlab/<state file>    session state published by helpers
//
// Trust, workspaces and focus are event-driven. Everything else is polled on
// the reviewed 30 second cadence.
//
// Three rules hold everywhere in this file:
//
//   * an observation that has not arrived is "loading", an observation that
//     failed is "unavailable", and an observation that is too old is
//     "stale" — none of them is ever presented as a value;
//   * a default is never published as an observation, so the shell does not
//     claim an Italian keyboard or a green theme it has not seen;
//   * a claim is only accepted when the host names one of the reviewed
//     identities at its canonical rung.

import Quickshell
import Quickshell.Io
import QtQuick

Scope {
    id: state

    readonly property string statusBridge:
        "/usr/local/bin/privatestack-hyperlab"

    readonly property string compositorAdapter:
        "/usr/local/bin/privatestack-compositor-adapter"

    readonly property string telemetryBridge:
        "/usr/local/bin/privatestack-telemetry"

    readonly property alias clock: shellClock

    // Three missed slow polls before an observation stops being current.
    readonly property int slowPollSeconds: 30
    readonly property int staleSeconds: 90

    // Ticks once a minute so every freshness readout re-evaluates without
    // each view owning a timer.
    property real observationNow: Date.now()

    // ---------------------------------------------------------------- state
    // Appearance. Each value is unknown until the host publishes it.

    property var keyboardState: ({ "value": "", "known": false })
    property var themeState: ({ "value": "", "known": false })
    property var wallpaperState: ({ "value": "", "known": false })

    // A real accessibility setting, consumed by every animation in the
    // shell. Absent means motion is enabled.
    property bool reducedMotion: false

    // ------------------------------------------------------- source health

    property string trustSourceState: "loading"
    property string gpuSourceState: "loading"
    property string machinesSourceState: "loading"
    property string telemetrySourceState: "loading"
    property string workspaceSourceState: "loading"
    property string focusSourceState: "loading"
    property string ramSourceState: "loading"

    property real trustObservedAt: 0
    property real gpuObservedAt: 0
    property real machinesObservedAt: 0
    property real telemetryObservedAt: 0
    property real workspaceObservedAt: 0
    property real focusObservedAt: 0
    property real ramObservedAt: 0

    function stale(observedAt) {
        if (observedAt <= 0)
            return false;

        return (state.observationNow - observedAt) / 1000
            > state.staleSeconds;
    }

    // When the shell started. A source that is still "loading" long after
    // start has not answered at all, which is a failure, not a wait.
    readonly property real startedAt: Date.now()

    // One vocabulary for every source: loading, ok, stale, unavailable.
    function sourceState(declared, observedAt) {
        const value = String(declared);

        if (value === "loading")
            return (state.observationNow - state.startedAt) / 1000
                > state.staleSeconds
                ? "unavailable"
                : "loading";

        if (value !== "ok")
            return value;

        return state.stale(observedAt) ? "stale" : "ok";
    }

    function observedText(observedAt) {
        if (observedAt <= 0)
            return "never";

        return Qt.formatDateTime(new Date(observedAt), "HH:mm");
    }

    function observedAge(observedAt) {
        if (observedAt <= 0)
            return "";

        const seconds =
            Math.max(0, Math.round((state.observationNow - observedAt) / 1000));

        if (seconds < 60)
            return seconds + "s ago";

        if (seconds < 3600)
            return Math.round(seconds / 60) + "m ago";

        return Math.round(seconds / 3600) + "h ago";
    }

    readonly property var sourceHealth: [
        {
            "name": "Trust claim",
            "state": state.sourceState(state.trustSourceState, state.trustObservedAt),
            "at": state.trustObservedAt
        },
        {
            "name": "GPU ownership",
            "state": state.sourceState(state.gpuSourceState, state.gpuObservedAt),
            "at": state.gpuObservedAt
        },
        {
            "name": "Machine inventory",
            "state": state.sourceState(state.machinesSourceState, state.machinesObservedAt),
            "at": state.machinesObservedAt
        },
        {
            "name": "Host telemetry",
            "state": state.sourceState(state.telemetrySourceState, state.telemetryObservedAt),
            "at": state.telemetryObservedAt
        },
        {
            "name": "Compositor workspaces",
            "state": state.sourceState(state.workspaceSourceState, state.workspaceObservedAt),
            "at": state.workspaceObservedAt
        },
        {
            "name": "Focused surface",
            "state": state.sourceState(state.focusSourceState, state.focusObservedAt),
            "at": state.focusObservedAt
        },
        {
            "name": "Host memory",
            "state": state.sourceState(state.ramSourceState, state.ramObservedAt),
            "at": state.ramObservedAt
        }
    ]

    readonly property var degradedSources: {
        const out = [];

        for (let index = 0; index < state.sourceHealth.length; index++) {
            const entry = state.sourceHealth[index];

            if (entry.state !== "ok")
                out.push(entry);
        }

        return out;
    }

    // ---------------------------------------------------------- compositor

    property var workspacePayload: ({
        "active": 0,
        "output": "",
        "occupied": [],
        "urgent": []
    })

    // The output the compositor reports as focused, from the same reviewed
    // snapshot as the workspaces. Empty when unknown; the shell root then
    // falls back to a deterministic live output rather than to "all".
    readonly property string focusedOutput:
        state.workspaceSourceState === "ok"
        && typeof state.workspacePayload.output === "string"
        ? state.workspacePayload.output
        : ""

    // The compositor's own identity for the focused surface. This is host
    // metadata about a host process: it names a window, and it is never a
    // provenance or trust decision.
    property var focusPayload: ({
        "app_id": "",
        "window_id": ""
    })

    readonly property string focusedSurface:
        String(state.focusPayload.app_id)

    // Focused-surface provenance is a separate, reviewed resolution from the
    // compositor identity above. No focused-provenance resolver is deployed
    // on this host yet, so the shell reports it as unavailable and shows no
    // identity rather than deriving one from a window name.
    readonly property var focusedProvenance: ({
        "available": false,
        "identity": "",
        "reason": "No reviewed focused-surface provenance resolver is deployed"
    })

    // --------------------------------------------------------------- trust

    property var trustPayload: ({
        "text": "",
        "tooltip": "",
        "class": ""
    })

    // The reviewed GPU handoff ladder. SERVICES is deliberately absent: it
    // sits outside the GPU handoff entirely and can never hold a boot claim.
    readonly property var gpuLadder: ({
        "clean": 3,
        "dev": 2,
        "dirty": 1,
        "lab": 0
    })

    // Explicit host-owned boot claim. The identity is accepted only when the
    // bridge names a ladder identity at that identity's canonical rung; the
    // shell never parses a claim out of free text, a name or an appearance.
    property var trustClaim: ({
        "claimed": false,
        "identity": "",
        "level": -1
    })

    // The one question every renderer asks before reading `trustClaim`:
    // loading, ok, stale or unavailable. Only "ok" allows "No claim this
    // boot"; any other state keeps the last valid claim, if there was one,
    // and must be presented with that qualifier.
    readonly property string trustClaimState:
        state.sourceState(state.trustSourceState, state.trustObservedAt)

    // Pure schema check, separate from the side effects so it can be tested
    // on its own. Returns the accepted claim, or null for anything that is
    // not an affirmative, internally consistent observation: malformed JSON,
    // arrays, error payloads, missing `known`, an off-ladder identity (which
    // includes SERVICES) or a rung that is not the identity's canonical rung.
    function validTrustObservation(parsed) {
        if (
            parsed === null
            || typeof parsed !== "object"
            || Array.isArray(parsed)
            || parsed.known !== true
            || typeof parsed.claimed !== "boolean"
            || String(parsed.class) === "error"
        )
            return null;

        if (!parsed.claimed) {
            if (
                (parsed.identity !== null && parsed.identity !== undefined)
                || (parsed.level !== null && parsed.level !== undefined)
            )
                return null;

            return {
                "claimed": false,
                "identity": "",
                "level": -1
            };
        }

        const identity =
            typeof parsed.identity === "string" ? parsed.identity : "";
        const rung = state.gpuLadder.hasOwnProperty(identity)
            ? state.gpuLadder[identity]
            : undefined;

        if (rung === undefined || parsed.level !== rung)
            return null;

        return {
            "claimed": true,
            "identity": identity,
            "level": rung
        };
    }

    function applyTrustPayload(raw) {
        const claim = state.validTrustObservation(state.parseJson(raw));

        if (claim === null) {
            // Keep the last valid claim: a restriction that was observed
            // does not disappear because a later read failed. Every renderer
            // qualifies it through trustClaimState.
            state.trustSourceState = "unavailable";
            state.trustPayload = {
                "text": "",
                "tooltip": "Trust claim could not be read",
                "class": "error"
            };
            return;
        }

        state.trustPayload = state.parsePayload(raw, "");
        state.trustClaim = claim;
        state.trustSourceState = "ok";
        state.trustObservedAt = Date.now();
    }

    // ----------------------------------------------------------------- GPU

    property var ramPayload: ({ "text": "", "tooltip": "", "class": "" })
    property var gpuPayload: ({ "text": "", "tooltip": "", "class": "" })

    // Structured GPU facts from the bridge. `known` separates "the host
    // reported ownership" from "the host could not tell us"; an empty owner
    // inside a known reading means there is no current owner, which is a
    // different fact from an unknown one.
    property var gpuOwnershipObserved: ({
        "known": false,
        "owner": "",
        "bound": false
    })

    // What presentation reads: the observation while it is current, and
    // "unknown" once it is stale or unavailable. An aged reading of an owner
    // is not a current owner.
    readonly property var gpuOwnership:
        state.sourceState(state.gpuSourceState, state.gpuObservedAt) === "ok"
        ? state.gpuOwnershipObserved
        : ({ "known": false, "owner": "", "bound": false })

    readonly property bool gpuHeld:
        state.gpuOwnership.known
        && String(state.gpuOwnership.owner).length > 0

    function applyGpuPayload(raw) {
        const parsed = state.parseJson(raw);

        if (parsed === null) {
            state.gpuSourceState = "unavailable";
            state.gpuOwnershipObserved = {
                "known": false,
                "owner": "",
                "bound": false
            };
            state.gpuPayload = {
                "text": "",
                "tooltip": "GPU ownership could not be read",
                "class": "error"
            };
            return;
        }

        state.gpuPayload = state.parsePayload(raw, "");

        state.gpuOwnershipObserved =
            parsed.known === true
            ? {
                "known": true,
                "owner":
                    typeof parsed.owner === "string" ? parsed.owner : "",
                "bound": parsed.bound === true
              }
            : {
                "known": false,
                "owner": "",
                "bound": false
              };

        state.gpuSourceState = "ok";
        state.gpuObservedAt = Date.now();
    }

    // ------------------------------------------------------------ machines

    property var vmPayload: ({ "text": "", "tooltip": "", "class": "" })

    property var machines: []
    property bool machinesAvailable: false

    // Rises whenever the observed inventory changes, including when it
    // becomes unavailable. A confirmation or capability answer captured
    // against an older generation is invalidated rather than used.
    property int machinesGeneration: 0
    property string machinesSignature: ""

    readonly property int machinesRunning: {
        let running = 0;

        for (let index = 0; index < state.machines.length; index++) {
            if (String(state.machines[index].state) === "running")
                running += 1;
        }

        return running;
    }

    readonly property var provenanceOrder: [
        "clean",
        "dev",
        "services",
        "dirty",
        "lab",
        "unclassified"
    ]

    function machinesWithProvenance(identity) {
        let count = 0;

        for (let index = 0; index < state.machines.length; index++) {
            if (String(state.machines[index].provenance) === String(identity))
                count += 1;
        }

        return count;
    }

    // Selection is an identifier; this resolves it against the current
    // snapshot every time, so a removed machine resolves to null instead of
    // a stale object.
    function machineById(identifier) {
        const name = String(identifier);

        if (name.length === 0)
            return null;

        for (let index = 0; index < state.machines.length; index++) {
            if (String(state.machines[index].name) === name)
                return state.machines[index];
        }

        return null;
    }

    function validMachineRow(row) {
        return row
            && typeof row.name === "string" && row.name.length > 0
            && typeof row.state === "string"
            && typeof row.gpu === "string"
            && state.provenanceOrder.indexOf(row.provenance) >= 0;
    }

    function applyMachinePayload(raw) {
        const parsed = state.parseJson(raw);

        // Clear old observations on failure; never present a stale VM as live.
        if (parsed === null) {
            state.machines = [];
            state.machinesAvailable = false;
            state.machinesSourceState = "unavailable";
            state.vmPayload = {
                "text": "",
                "tooltip": "Machine inventory could not be read",
                "class": "error"
            };
            state.machinesGeneration += 1;
            return;
        }

        state.vmPayload = state.parsePayload(raw, "");

        if (
            parsed.machines_available !== true
            || !Array.isArray(parsed.machines)
            || !parsed.machines.every(row => state.validMachineRow(row))
        ) {
            state.machines = [];
            state.machinesAvailable = false;
            state.machinesSourceState = "unavailable";
            state.machinesGeneration += 1;
            return;
        }

        // The generation moves when what the host reports moves: a machine
        // appears, disappears or changes state or configuration. An
        // identical poll is a fresher observation of the same facts, so an
        // open exact-name confirmation is not thrown away every 30 seconds.
        const signature = JSON.stringify(parsed.machines);
        const changed =
            !state.machinesAvailable
            || signature !== state.machinesSignature;

        state.machines = parsed.machines;
        state.machinesSignature = signature;
        state.machinesAvailable = true;
        state.machinesSourceState = "ok";
        state.machinesObservedAt = Date.now();

        if (changed)
            state.machinesGeneration += 1;
    }

    // -------------------------------------------------------- capabilities
    //
    // What the reviewed machine bridge says may be done to the selected
    // machine, as an observation like any other. MachineActions carries the
    // request and the raw reply; this object decides whether the reply is
    // the answer to the current question. A reply is accepted only when its
    // request serial is the one outstanding, it names the machine that was
    // asked about, and every entry has the reviewed shape. Anything else is
    // discarded (a superseded request) or recorded as unavailable (a broken
    // answer to the current request), never adopted.

    readonly property var capabilityVerbNames: [
        "start",
        "shutdown",
        "reboot",
        "console",
        "ssh",
        "looking-glass",
        "force-stop"
    ]

    property var capabilityRequest: ({
        "serial": 0,
        "machine": "",
        "generation": -1
    })

    property var machineCapabilities: ({
        "machine": "",
        "generation": -1,
        "state": "idle",
        "verbs": ({}),
        "facts": null,
        "detail": "",
        "observedAt": 0
    })

    function beginCapabilityRequest(serial, machine, generation) {
        const name = String(machine);

        state.capabilityRequest = {
            "serial": serial,
            "machine": name,
            "generation": typeof generation === "number" ? generation : -1
        };

        // A different machine never inherits the previous machine's answer.
        // The same machine keeps its answer, bound to its own generation,
        // until the new one arrives.
        if (state.machineCapabilities.machine !== name) {
            state.machineCapabilities = {
                "machine": name,
                "generation": -1,
                "state": "loading",
                "verbs": ({}),
                "facts": null,
                "detail": "",
                "observedAt": 0
            };
        }
    }

    function clearCapabilities() {
        state.capabilityRequest = {
            "serial": -1,
            "machine": "",
            "generation": -1
        };
        state.machineCapabilities = {
            "machine": "",
            "generation": -1,
            "state": "idle",
            "verbs": ({}),
            "facts": null,
            "detail": "",
            "observedAt": 0
        };
    }

    // Pure schema check. Returns clean verbs and facts, or null.
    function validCapabilityAnswer(parsed, machine) {
        if (
            parsed === null
            || typeof parsed !== "object"
            || Array.isArray(parsed)
            || parsed.phase !== "capabilities"
            || parsed.machine === null
            || typeof parsed.machine !== "object"
            || Array.isArray(parsed.machine)
            || parsed.machine.name !== machine
            || parsed.verbs === null
            || typeof parsed.verbs !== "object"
            || Array.isArray(parsed.verbs)
        )
            return null;

        const verbs = {};

        for (const key of Object.keys(parsed.verbs)) {
            const entry = parsed.verbs[key];

            if (
                state.capabilityVerbNames.indexOf(key) < 0
                || entry === null
                || typeof entry !== "object"
                || typeof entry.available !== "boolean"
                || typeof entry.reason !== "string"
            )
                return null;

            verbs[key] = {
                "available": entry.available,
                "reason": entry.reason
            };
        }

        const facts = parsed.machine;

        return {
            "verbs": verbs,
            "facts": {
                "name": machine,
                "state": typeof facts.state === "string" ? facts.state : "unknown",
                "managed": typeof facts.managed === "boolean" ? facts.managed : null,
                "vfio": typeof facts.vfio === "boolean" ? facts.vfio : null
            }
        };
    }

    function applyCapabilityAnswer(serial, machine, raw, exitCode, detail) {
        const request = state.capabilityRequest;

        // Superseded, cancelled or foreign: not an answer to the question
        // currently being asked.
        if (serial !== request.serial || String(machine) !== request.machine)
            return false;

        const answer =
            exitCode === 0
            ? state.validCapabilityAnswer(state.parseJson(raw), request.machine)
            : null;

        if (answer === null) {
            state.machineCapabilities = {
                "machine": request.machine,
                "generation": request.generation,
                "state": "unavailable",
                "verbs": ({}),
                "facts": null,
                "detail":
                    String(detail).length > 0
                    ? String(detail)
                    : "The machine bridge did not answer",
                "observedAt": 0
            };
            return false;
        }

        state.machineCapabilities = {
            "machine": request.machine,
            "generation": request.generation,
            "state": "ok",
            "verbs": answer.verbs,
            "facts": answer.facts,
            "detail": "",
            "observedAt": Date.now()
        };
        return true;
    }

    // The one availability decision presentation consumes. Every fact it
    // depends on must be current: the machine is in a current inventory, and
    // the bridge answered for this machine against this inventory
    // generation. The bridge re-checks at execution regardless.
    function capabilityFor(machine, verb) {
        const name = String(machine);

        if (state.machineById(name) === null) {
            return {
                "available": false,
                "reason": "This machine is no longer in the inventory",
                "known": true
            };
        }

        if (
            state.sourceState(
                state.machinesSourceState,
                state.machinesObservedAt
            ) !== "ok"
        ) {
            return {
                "available": false,
                "reason": "The machine inventory is not current",
                "known": true
            };
        }

        const observed = state.machineCapabilities;

        if (observed.machine !== name || observed.state === "idle") {
            return {
                "available": false,
                "reason": "Capabilities have not been read for this machine",
                "known": false
            };
        }

        if (observed.state === "loading") {
            return {
                "available": false,
                "reason": "Checking what this machine supports",
                "known": false
            };
        }

        if (observed.state === "unavailable") {
            return {
                "available": false,
                "reason": observed.detail,
                "known": true
            };
        }

        if (observed.generation !== state.machinesGeneration) {
            return {
                "available": false,
                "reason": "Re-checking after an inventory change",
                "known": false
            };
        }

        const entry = observed.verbs[String(verb)];

        if (entry === undefined) {
            return {
                "available": false,
                "reason": "The machine bridge did not report this operation",
                "known": false
            };
        }

        return {
            "available": entry.available,
            "reason": entry.reason,
            "known": true
        };
    }

    // ----------------------------------------------------------- telemetry

    // Telemetry is stored as observed and presented through the views
    // below, which only pass an observation through while the telemetry
    // source is current. A failed, stale or never-answered source reads as
    // unavailable everywhere at once -- rail, panel, Control Center and OSD
    // -- instead of each surface showing the last value as if it were live.
    readonly property bool telemetryCurrent:
        state.sourceState(
            state.telemetrySourceState,
            state.telemetryObservedAt
        ) === "ok"

    readonly property var telemetryWithheld: ({
        "text": "",
        "tooltip": "Host telemetry is not current",
        "class": "unavailable",
        "detail": "",
        "kind": ""
    })

    property var temperatureObserved: ({ "text": "", "tooltip": "", "class": "loading" })
    property var networkObserved: ({ "text": "", "tooltip": "", "class": "loading" })
    property var audioObserved: ({ "text": "", "tooltip": "", "class": "loading" })
    property var batteryObserved: ({ "text": "", "tooltip": "", "class": "loading" })

    readonly property var temperaturePayload:
        state.telemetryCurrent ? state.temperatureObserved : state.telemetryWithheld
    readonly property var networkPayload:
        state.telemetryCurrent ? state.networkObserved : state.telemetryWithheld
    readonly property var audioPayload:
        state.telemetryCurrent ? state.audioObserved : state.telemetryWithheld
    readonly property var batteryPayload:
        state.telemetryCurrent ? state.batteryObserved : state.telemetryWithheld

    // Structured audio. The OSD and the panels read these numbers; nothing
    // downstream parses a localized percentage out of display text.
    property var audioLevelObserved: ({
        "known": false,
        "percent": -1,
        "muted": false,
        "maximum": 125
    })

    readonly property var audioLevel:
        state.telemetryCurrent
        ? state.audioLevelObserved
        : ({ "known": false, "percent": -1, "muted": false, "maximum": 125 })

    // A battery the host does not expose is absent; a battery it cannot read
    // is unavailable. They are different sentences.
    property var batteryPresenceObserved: ({
        "present": false,
        "known": false
    })

    readonly property var batteryPresence:
        state.telemetryCurrent
        ? state.batteryPresenceObserved
        : ({ "present": false, "known": false })

    readonly property var secondaryPayloads: [
        state.temperaturePayload,
        state.networkPayload,
        state.batteryPayload
    ]

    // ---------------------------------------------------------- operations

    // Observed operation outcomes, newest first. The action layers publish
    // them; this object only remembers what they reported.
    property var operations: []

    function recordOperation(record) {
        const entry = {
            "id": String(record.id),
            "kind": String(record.kind),
            "label": String(record.label),
            "target": String(record.target),
            "phase": String(record.phase),
            "detail": String(record.detail),
            "at": Qt.formatDateTime(new Date(), "HH:mm:ss")
        };

        const next = [entry];

        for (
            let index = 0;
            index < state.operations.length && next.length < 12;
            index++
        ) {
            if (state.operations[index].id !== entry.id)
                next.push(state.operations[index]);
        }

        state.operations = next;
    }

    function latestOperationFor(target) {
        for (let index = 0; index < state.operations.length; index++) {
            if (state.operations[index].target === String(target))
                return state.operations[index];
        }

        return null;
    }

    // ---------------------------------------------------------- appearance

    function keyboardName() {
        if (!state.keyboardState.known)
            return "Unknown";

        switch (state.keyboardState.value) {
        case "us":
            return "English (US)";
        case "ara":
            return "Arabic";
        case "it":
            return "Italian";
        default:
            return "Unknown";
        }
    }

    function keyboardLabel() {
        if (!state.keyboardState.known)
            return "··";

        switch (state.keyboardState.value) {
        case "us":
            return "EN";
        case "ara":
            return "AR";
        default:
            return "IT";
        }
    }

    function themeLabel() {
        if (!state.themeState.known)
            return "Unknown";

        const value = state.themeState.value;

        return value === "trust-model"
            ? "Trust Model"
            : value.charAt(0).toUpperCase() + value.slice(1);
    }

    function wallpaperLabel() {
        if (!state.wallpaperState.known)
            return "Unknown";

        // An explicit product selection wins over every theme's own pool,
        // exactly as the theme controller resolves it.
        if (state.wallpaperState.value === "product")
            return "HyperLab";

        if (!state.themeState.known)
            return "Unknown";

        if (state.themeState.value === "trust-model")
            return "Trust pool";

        return state.wallpaperState.value === "personal"
            ? "Personal"
            : "Public";
    }

    // ------------------------------------------------------------- parsing

    function parseJson(raw) {
        const source = String(raw).trim();

        if (source.length === 0)
            return null;

        try {
            const parsed = JSON.parse(source);

            if (parsed === null || typeof parsed !== "object")
                return null;

            return parsed;
        } catch (error) {
            return null;
        }
    }

    function parsePayload(raw, fallbackText) {
        const parsed = state.parseJson(raw);

        if (parsed === null) {
            return {
                "text": fallbackText,
                "tooltip": "HyperLab status payload unavailable",
                "class": "error"
            };
        }

        return {
            "text":
                parsed.text !== undefined
                ? String(parsed.text)
                : fallbackText,
            "tooltip":
                parsed.tooltip !== undefined
                ? String(parsed.tooltip)
                : "",
            "class":
                parsed.class !== undefined
                ? String(parsed.class)
                : ""
        };
    }

    function normalizeStatusPayload(candidate, fallbackText) {
        if (
            candidate === undefined
            || candidate === null
            || typeof candidate !== "object"
        ) {
            return {
                "text": fallbackText,
                "tooltip": "",
                "class": "unavailable",
                "detail": ""
            };
        }

        return {
            "text":
                candidate.text !== undefined
                ? String(candidate.text)
                : fallbackText,
            "tooltip":
                candidate.tooltip !== undefined
                ? String(candidate.tooltip)
                : "",
            "class":
                candidate.class !== undefined
                ? String(candidate.class)
                : "",
            "detail":
                candidate.detail !== undefined
                ? String(candidate.detail)
                : "",
            // The structured kind of the reading, where the bridge publishes
            // one. Presentation switches on this, never on display text.
            "kind":
                candidate.kind !== undefined
                ? String(candidate.kind)
                : ""
        };
    }

    function applyWorkspacePayload(raw) {
        const parsed = state.parseJson(raw);

        if (
            parsed === null
            || typeof parsed.active !== "number"
            || !Array.isArray(parsed.occupied)
            || !Array.isArray(parsed.urgent)
        ) {
            state.workspaceSourceState = "unavailable";
            return;
        }

        state.workspacePayload = {
            "active": parsed.active,
            "output": typeof parsed.output === "string" ? parsed.output : "",
            "occupied": parsed.occupied,
            "urgent": parsed.urgent
        };
        state.workspaceSourceState = "ok";
        state.workspaceObservedAt = Date.now();
    }

    function applyFocusPayload(raw) {
        const parsed = state.parseJson(raw);

        if (parsed === null) {
            state.focusSourceState = "unavailable";
            return;
        }

        state.focusPayload = {
            "app_id":
                typeof parsed.app_id === "string" ? parsed.app_id : "",
            "window_id":
                typeof parsed.window_id === "string" ? parsed.window_id : ""
        };

        state.focusSourceState = "ok";
        state.focusObservedAt = Date.now();
    }

    function applyTelemetryPayload(raw) {
        const parsed = state.parseJson(raw);

        if (parsed === null) {
            state.telemetrySourceState = "unavailable";
            return;
        }

        state.temperatureObserved =
            state.normalizeStatusPayload(parsed.temperature, "");
        state.networkObserved =
            state.normalizeStatusPayload(parsed.network, "");
        state.audioObserved =
            state.normalizeStatusPayload(parsed.audio, "");
        state.batteryObserved =
            state.normalizeStatusPayload(parsed.battery, "");

        const audio = parsed.audio;

        state.audioLevelObserved =
            audio && typeof audio.percent === "number"
            ? {
                "known": true,
                "percent": audio.percent,
                "muted": audio.muted === true,
                "maximum":
                    typeof audio.maximum === "number" ? audio.maximum : 125
              }
            : {
                "known": false,
                "percent": -1,
                "muted": false,
                "maximum": 125
              };

        const battery = parsed.battery;

        state.batteryPresenceObserved =
            battery && typeof battery.present === "boolean"
            ? { "present": battery.present, "known": true }
            : { "present": false, "known": false };

        state.telemetrySourceState = "ok";
        state.telemetryObservedAt = Date.now();
    }

    function applyRamPayload(raw) {
        const parsed = state.parseJson(raw);

        if (parsed === null) {
            state.ramSourceState = "unavailable";
            state.ramPayload = {
                "text": "",
                "tooltip": "Host memory could not be read",
                "class": "error"
            };
            return;
        }

        state.ramPayload = state.parsePayload(raw, "");
        state.ramSourceState = "ok";
        state.ramObservedAt = Date.now();
    }

    function applyKeyboardLayout(raw) {
        const candidate = String(raw).trim();

        if (
            candidate === "it"
            || candidate === "us"
            || candidate === "ara"
        ) {
            state.keyboardState = { "value": candidate, "known": true };
            return;
        }

        // Unreadable or unrecognised content is not the previous value.
        state.keyboardState = { "value": "", "known": false };
    }

    function applyWallpaperMode(raw) {
        const candidate = String(raw).trim();

        if (
            candidate === "public"
            || candidate === "personal"
            || candidate === "product"
        ) {
            state.wallpaperState = { "value": candidate, "known": true };
            return;
        }

        // Unreadable or unrecognised content is not the previous value.
        state.wallpaperState = { "value": "", "known": false };
    }

    function applyThemeName(raw) {
        const candidate = String(raw).trim();

        if (
            candidate === "green"
            || candidate === "violet"
            || candidate === "blue"
            || candidate === "red"
            || candidate === "trust-model"
        ) {
            state.themeState = { "value": candidate, "known": true };
            return;
        }

        // Unreadable or unrecognised content is not the previous value.
        state.themeState = { "value": "", "known": false };
    }

    function applyReducedMotion(raw) {
        const candidate = String(raw).trim();

        state.reducedMotion = candidate === "1" || candidate === "true";
    }

    // ------------------------------------------------------------ refresh

    // A poll that never returns is a failure, not a pending answer: past
    // this bound it is stopped, its collector delivers what it has (usually
    // nothing), and the source reads unavailable instead of silently keeping
    // the previous snapshot while every later refresh is skipped.
    readonly property int pollTimeoutMs: 45000

    function startPoll(process) {
        if (process.running) {
            if (Date.now() - process.startedAt > state.pollTimeoutMs)
                process.running = false;

            return;
        }

        process.startedAt = Date.now();
        process.running = true;
    }

    function refreshSlowMetrics() {
        state.startPoll(ramProcess);
        state.startPoll(gpuProcess);
        state.startPoll(vmProcess);
        state.startPoll(telemetryProcess);
    }

    function refreshTelemetry() {
        state.startPoll(telemetryProcess);
    }

    function refreshInventory() {
        state.startPoll(vmProcess);
        state.startPoll(gpuProcess);
    }

    function refreshAppearanceState() {
        themeStateFile.reload();
        wallpaperModeStateFile.reload();
        reducedMotionStateFile.reload();
    }

    // A completed session action publishes its result through the same state
    // files the helpers own. The shell re-reads them instead of assuming the
    // action succeeded.
    function settleAction(action) {
        switch (String(action)) {
        case "keyboard-cycle":
            keyboardStateFile.reload();
            break;
        case "wallpaper-mode-toggle":
        case "theme-cycle":
            // The theme controller publishes one coalesced appearance
            // refresh only after its complete transaction has settled.
            break;
        case "audio-mute-toggle":
        case "audio-volume-up":
        case "audio-volume-down":
            state.refreshTelemetry();
            break;
        default:
            break;
        }
    }

    Component.onCompleted: {
        state.applyThemeName(themeStateFile.text());
        state.applyKeyboardLayout(keyboardStateFile.text());
        state.applyWallpaperMode(wallpaperModeStateFile.text());
        state.applyReducedMotion(reducedMotionStateFile.text());
    }

    SystemClock {
        id: shellClock
        precision: SystemClock.Minutes
    }

    FileView {
        id: themeStateFile

        path:
            Quickshell.env("HOME")
            + "/.config/hyperlab/"
            + "theme"

        onTextChanged: {
            state.applyThemeName(this.text());
        }
    }

    FileView {
        id: keyboardStateFile

        path:
            Quickshell.env("HOME")
            + "/.config/hyperlab/"
            + "keyboard-layout"

        watchChanges: true

        onFileChanged: reload()

        onTextChanged: {
            state.applyKeyboardLayout(this.text());
        }
    }

    FileView {
        id: wallpaperModeStateFile

        path:
            Quickshell.env("HOME")
            + "/.config/hyperlab/"
            + "wallpaper-mode"

        onTextChanged: {
            state.applyWallpaperMode(this.text());
        }
    }

    // Accessibility. Absent means motion is enabled; the file is the only
    // authority, and nothing in presentation writes it.
    FileView {
        id: reducedMotionStateFile

        path:
            Quickshell.env("HOME")
            + "/.config/hyperlab/"
            + "reduced-motion"

        // Absence is the reviewed default: normal motion remains enabled.
        // Suppress FileView's generic warning for that expected state while
        // preserving an explicit warning for every other read failure.
        printErrors: false
        watchChanges: true

        onFileChanged: reload()

        onLoadFailed: error => {
            state.applyReducedMotion("");

            if (error !== FileViewError.FileNotFound) {
                console.warn(
                    "HyperLab reduced-motion state read failed: "
                    + FileViewError.toString(error)
                );
            }
        }

        onTextChanged: {
            state.applyReducedMotion(this.text());
        }
    }

    // Workspace state is compositor-neutral in QML. The adapter owns
    // translation to Sway or Hyprland and emits one JSON snapshot per event.
    Process {
        id: workspaceProcess

        running: true

        command: [
            state.compositorAdapter,
            "workspace-watch"
        ]

        stdout: SplitParser {
            onRead: data => {
                state.applyWorkspacePayload(data);
            }
        }

        onRunningChanged: {
            if (!running) {
                state.workspaceSourceState = "unavailable";
                workspaceRestart.start();
            }
        }
    }

    Timer {
        id: workspaceRestart
        interval: 2000
        repeat: false

        onTriggered: {
            if (!workspaceProcess.running)
                workspaceProcess.running = true;
        }
    }

    // The focused host surface, as the compositor names it. Host metadata
    // about a host process; never a provenance or trust decision.
    Process {
        id: focusProcess

        running: true

        command: [
            state.compositorAdapter,
            "focused-window-watch"
        ]

        stdout: SplitParser {
            onRead: data => {
                state.applyFocusPayload(data);
            }
        }

        onRunningChanged: {
            if (!running) {
                state.focusSourceState = "unavailable";
                focusRestart.start();
            }
        }
    }

    Timer {
        id: focusRestart
        interval: 2000
        repeat: false

        onTriggered: {
            if (!focusProcess.running)
                focusProcess.running = true;
        }
    }

    // Trust remains event-driven through hyperlabctl.
    Process {
        id: trustProcess

        running: true

        command: [
            state.statusBridge,
            "watch",
            "trust"
        ]

        stdout: SplitParser {
            onRead: data => {
                state.applyTrustPayload(data);
            }
        }

        onRunningChanged: {
            if (!running) {
                state.trustSourceState = "unavailable";
                trustRestart.start();
            }
        }
    }

    Timer {
        id: trustRestart
        interval: 2000
        repeat: false

        onTriggered: {
            if (!trustProcess.running)
                trustProcess.running = true;
        }
    }

    Process {
        id: ramProcess

        property real startedAt: 0

        command: [
            state.statusBridge,
            "ram"
        ]

        stdout: StdioCollector {
            onStreamFinished: {
                state.applyRamPayload(this.text);
            }
        }
    }

    Process {
        id: gpuProcess

        property real startedAt: 0

        command: [
            state.statusBridge,
            "gpu"
        ]

        stdout: StdioCollector {
            onStreamFinished: {
                state.applyGpuPayload(this.text);
            }
        }
    }

    Process {
        id: vmProcess

        property real startedAt: 0

        command: [
            state.statusBridge,
            "vms"
        ]

        stdout: StdioCollector {
            onStreamFinished: {
                state.applyMachinePayload(this.text);
            }
        }
    }

    Process {
        id: telemetryProcess

        property real startedAt: 0

        command: [
            state.telemetryBridge,
            "snapshot"
        ]

        stdout: StdioCollector {
            onStreamFinished: {
                state.applyTelemetryPayload(this.text);
            }
        }
    }

    Timer {
        interval: 30000
        repeat: true
        running: true
        triggeredOnStart: true

        onTriggered: state.refreshSlowMetrics()
    }

    // Freshness is observed, not assumed: this is the only clock that turns
    // an old observation into a stale one.
    Timer {
        interval: 15000
        repeat: true
        running: true

        onTriggered: state.observationNow = Date.now()
    }
}
