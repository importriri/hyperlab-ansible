// Presentation state only. Execution success never invents a machine state or lifecycle transition.
import QtQuick

QtObject {
    id: tracker
    property var records: []
    property var inventory: []
    property real inventoryObservedAt: 0
    property real now: Date.now()
    property bool known: false
    readonly property int settlingMs: 60000
    readonly property var actionVerbs: ({
        "vm.managed-start": "start", "vm.managed-shutdown": "shutdown",
        "vm.managed-reboot": "reboot", "vm.force-stop": "force-stop",
        "vm.power-cycle": "power-cycle", "vm.reset": "reset"
    })
    signal changed(var record)
    signal refreshRequested()

    function terminal(phase) {
        return ["completed", "failed", "interrupted", "unverified"].indexOf(phase) >= 0;
    }
    function busyFor(machine) {
        return !tracker.known || tracker.records.some(
            r => r.machine === machine && !tracker.terminal(r.phase));
    }
    function activeFor(machine) {
        return tracker.records.find(
            r => r.machine === machine && !tracker.terminal(r.phase)
                && r.phase !== "verifying") || null;
    }
    function valid(record) {
        return record && record.schema === 1
            && typeof record.operation_id === "string"
            && /^[0-9a-f]{32}$/.test(record.operation_id)
            && record.unit === "hyperlab-operation-" + record.operation_id
            && Object.prototype.hasOwnProperty.call(tracker.actionVerbs, record.action_id)
            && typeof record.machine === "string" && record.machine.length > 0
            && record.machine.length <= 255
            && ["requested", "dispatched", "running", "succeeded", "failed", "interrupted"].indexOf(record.phase) >= 0
            && typeof record.updated_at === "number" && Number.isFinite(record.updated_at)
            && typeof record.created_at === "number" && Number.isFinite(record.created_at)
            && record.created_at > 0
            && record.updated_at >= record.created_at
            && (record.phase === "succeeded" ? record.rc === 0
                : record.phase === "failed" ? Number.isInteger(record.rc) && record.rc !== 0
                : record.rc === null);
    }
    function publish(record) {
        tracker.records = tracker.records.filter(r => r.id !== record.id).concat([record]);
        tracker.changed(record);
    }
    function apply(record, expectedId, deferReconcile) {
        if (!tracker.valid(record) || (expectedId && record.operation_id !== expectedId))
            return false;
        const old = tracker.records.find(r => r.id === record.operation_id);
        if (old && (old.machine !== record.machine
            || old.verb !== tracker.actionVerbs[record.action_id]))
            return false;
        if (old && (record.updated_at * 1000 <= old.updated || tracker.terminal(old.phase)))
            return true;
        const phase = record.phase === "succeeded" ? "verifying" : record.phase;
        const detail = phase === "requested" || phase === "dispatched"
            ? "Operation dispatched to its own unit"
            : phase === "running" ? "Running — authenticate in the operation window if prompted"
            : phase === "verifying" ? "Execution finished — verifying machine state"
            : phase === "failed" ? "Operation failed (exit " + record.rc + ")"
            : "Operation interrupted — its unit stopped before finishing";
        tracker.publish({id: record.operation_id, machine: record.machine,
            verb: tracker.actionVerbs[record.action_id], phase: phase,
            updated: record.updated_at * 1000, created: record.created_at * 1000,
            rc: record.rc, detail: detail});
        tracker.refreshRequested();
        if (!deferReconcile)
            tracker.reconcile();
        return true;
    }
    function snapshot(value) {
        if (!value || value.schema !== 1 || !Array.isArray(value.operations)
            || !value.operations.every(r => tracker.valid(r))) {
            tracker.known = false;
            return false;
        }
        // Missing information cannot erase an unresolved operation.
        if (tracker.records.some(r => !tracker.terminal(r.phase)
            && !value.operations.some(v => v.operation_id === r.id))) {
            tracker.known = false;
            return false;
        }
        const ids = value.operations.map(r => r.operation_id);
        if (ids.some((id, index) => ids.indexOf(id) !== index)) {
            tracker.known = false;
            return false;
        }
        tracker.known = true;
        // Load the whole snapshot before checking inventory: an older
        // success must not borrow the state reached by a newer operation.
        for (const record of value.operations.slice().sort((a, b) => a.created_at - b.created_at)) {
            if (!tracker.apply(record, record.operation_id, true)) {
                tracker.known = false;
                return false;
            }
        }
        tracker.reconcile();
        return true;
    }
    function reconcile() {
        if (!tracker.known) return;
        for (const original of tracker.records) {
            if (original.phase !== "verifying") continue;
            const record = Object.assign({}, original);
            const newer = tracker.records.some(r => r.machine === record.machine
                && r.created > record.created);
            const machine = tracker.inventory.find(m => m.name === record.machine);
            const needsTransitionProof =
                ["reboot", "power-cycle"].indexOf(record.verb) >= 0;
            const wanted = record.verb === "start" ? "running" : "shut off";

            // Reboot and power-cycle begin and end in Running. A fresh
            // Running inventory observation therefore cannot prove that the
            // requested lifecycle boundary occurred. Until the backend
            // publishes a typed transition proof, execution success is kept
            // explicit and fails closed as unverified presentation state.
            if (needsTransitionProof) {
                record.phase = "unverified";
                record.detail =
                    "Execution succeeded; lifecycle transition was not independently verified";
            } else if (!newer && machine
                && tracker.inventoryObservedAt >= record.updated
                && tracker.inventoryObservedAt <= record.updated + tracker.settlingMs
                && String(machine.state).toLowerCase() === wanted) {
                record.phase = "completed";
                record.detail =
                    "Execution succeeded; backend state verified: " + wanted;
            } else if (newer || tracker.now - record.updated >= tracker.settlingMs) {
                record.phase = "unverified";
                record.detail =
                    "Execution succeeded; expected machine state was not verified";
            } else {
                continue;
            }
            tracker.publish(record);
            tracker.refreshRequested();
        }
    }
    onInventoryObservedAtChanged: tracker.reconcile()
    onNowChanged: tracker.reconcile()
}
