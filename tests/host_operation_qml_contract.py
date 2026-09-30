#!/usr/bin/env python3
"""Execute production operation tracking and dispatch gates with inert transport."""
import shutil

import host_quickshell_runtime_contract as runtime

BODY = r'''
            const state = lifecycle.trackerFixture;
            let refreshed = 0;
            let changes = [];
            state.refreshRequested.connect(() => { refreshed += 1; });
            state.changed.connect(record => { changes.push(record); });
            const one = "a".repeat(32), two = "b".repeat(32), three = "c".repeat(32),
                  four = "d".repeat(32), five = "e".repeat(32);
            const epoch = Date.now() / 1000;
            function payload(id, machine, phase, offset, rc, actionId) {
                return {schema: 1, operation_id: id, machine: machine,
                    action_id: actionId || "vm.managed-start", phase: phase,
                    unit: "hyperlab-operation-" + id,
                    created_at: epoch, updated_at: epoch + offset, rc: rc};
            }
            function phase(id) { return state.records.find(r => r.id === id).phase; }
            check(lifecycle.busyFor("one"), "undiscovered state allowed lifecycle");
            state.snapshot({schema: 1, operations: []});
            check(lifecycle.invoke("start", "one"), "initial request refused");
            check(!lifecycle.invoke("start", "one"), "double click dispatched twice");
            const dispatched = payload(one, "one", "dispatched", 0, null);
            lifecycle.applyOperationLine(JSON.stringify(dispatched));
            lifecycle.runnerFixture.running = false;
            lifecycle.runnerFixture.exited(0, 0);
            check(phase(one) === "dispatched" && lifecycle.busyFor("one"),
                  "dispatch was treated as final");
            check(!lifecycle.busyFor("two"), "busy leaked to another machine");
            check(lifecycle.activeOperationFor("one") !== null
                  && lifecycle.activeOperationFor("one").id === one,
                  "dispatched operation cannot be reattached");
            check(lifecycle.activeOperationFor("two") === null,
                  "reattach offered for a machine without an operation");
            check(!state.apply(payload(two, "two", "running", 1, null), one),
                  "mismatched operation response was accepted");
            state.apply(payload(one, "one", "running", 1, null), one);
            state.apply(dispatched, one);
            check(phase(one) === "running", "stale reply regressed operation");
            state.inventory = [{name: "one", state: "shut off"}];
            state.inventoryObservedAt = (epoch + 3) * 1000;
            state.apply(payload(one, "one", "succeeded", 2, 0), one);
            check(phase(one) === "verifying" && lifecycle.busyFor("one"),
                  "rc zero fabricated Running/completion");
            check(lifecycle.activeOperationFor("one") === null,
                  "finished execution still offered an operation window");
            state.inventory = [{name: "one", state: "running"}];
            state.inventoryObservedAt = (epoch + 4) * 1000;
            check(phase(one) === "completed" && !lifecycle.busyFor("one"),
                  "fresh inventory Running did not verify Start");
            state.apply(payload(one, "one", "running", 8, null), one);
            check(phase(one) === "completed", "late reply revived final operation");
            check(refreshed >= 4, "meaningful transitions did not refresh inventory");
            state.apply(payload(two, "one", "failed", 9, 7), two);
            check(phase(two) === "failed" && phase(one) === "completed",
                  "new result overwrote old operation id");
            check(state.records.find(r => r.id === two).detail.indexOf("7") >= 0,
                  "failure exit code missing");
            state.apply(payload(three, "two", "interrupted", 10, null), three);
            check(phase(three) === "interrupted" && !lifecycle.busyFor("two"),
                  "interruption did not settle safely");
            check(!state.snapshot({schema: 1, operations: [{}]}),
                  "malformed recovery snapshot was accepted");
            check(lifecycle.busyFor("one"), "unknown status silently allowed a duplicate");

            // A fresh shell has no in-memory history: recover the active id.
            recovery.snapshot({schema: 1, operations: [dispatched]});
            check(recovery.busyFor("one") && !recovery.busyFor("two"),
                  "restart failed to rehydrate per-machine busy");
            recovery.inventory = [{name: "one", state: "shut off"}];
            recovery.inventoryObservedAt = (epoch + 5) * 1000;
            recovery.apply(payload(one, "one", "succeeded", 2, 0), one);
            recovery.now = (epoch + 63) * 1000;
            check(recovery.records[0].phase === "unverified",
                  "settling timeout claimed completion or never ended");
            check(!recovery.busyFor("one"), "unverified terminal state stayed busy");
            recovery.records = [];
            recovery.inventory = [{name: "one", state: "running"}];
            recovery.inventoryObservedAt = (epoch + 10) * 1000;
            const later = payload(two, "one", "running", 4, null);
            later.created_at = epoch + 3;
            let falseSuccess = false;
            recovery.changed.connect(r => {
                if (r.id === one && r.phase === "completed") falseSuccess = true;
            });
            recovery.snapshot({schema: 1, operations: [
                payload(one, "one", "succeeded", 2, 0), later]});
            check(!falseSuccess && recovery.busyFor("one"),
                  "recovery verified old success before seeing newer operation");
            check(!recovery.snapshot({schema: 1, operations: [later, later]}),
                  "duplicate operation IDs were accepted");
            recovery.records = [];
            recovery.inventoryObservedAt = (epoch + 90) * 1000;
            recovery.now = (epoch + 90) * 1000;
            recovery.snapshot({schema: 1, operations: [
                payload(one, "one", "succeeded", 2, 0)]});
            check(recovery.records[0].phase === "unverified",
                  "late restart borrowed Running after the verification deadline");

            // Reboot and power-cycle both start and finish in Running.
            // Fresh inventory must not manufacture transition proof.
            recovery.records = [];
            recovery.inventory = [{name: "one", state: "running"}];
            recovery.inventoryObservedAt = (epoch + 4) * 1000;
            recovery.now = (epoch + 4) * 1000;
            recovery.snapshot({schema: 1, operations: [
                payload(four, "one", "succeeded", 2, 0,
                        "vm.managed-reboot")]});
            check(recovery.records.length === 1
                  && recovery.records[0].phase === "unverified",
                  "fresh Running falsely verified Reboot");
            check(recovery.records[0].detail.indexOf(
                      "lifecycle transition was not independently verified") >= 0,
                  "Reboot did not explain missing transition proof");
            check(!recovery.busyFor("one"),
                  "unverified Reboot remained busy");

            recovery.records = [];
            recovery.inventory = [{name: "one", state: "running"}];
            recovery.inventoryObservedAt = (epoch + 4) * 1000;
            recovery.now = (epoch + 4) * 1000;
            recovery.snapshot({schema: 1, operations: [
                payload(five, "one", "succeeded", 2, 0,
                        "vm.power-cycle")]});
            check(recovery.records.length === 1
                  && recovery.records[0].phase === "unverified",
                  "fresh Running falsely verified Power cycle");
            check(recovery.records[0].detail.indexOf(
                      "lifecycle transition was not independently verified") >= 0,
                  "Power cycle did not explain missing transition proof");
            check(!recovery.busyFor("one"),
                  "unverified Power cycle remained busy");


'''


def main():
    runner = shutil.which('qmlscene', path='/usr/lib/qt6/bin') or shutil.which('qmlscene6')
    if not runner:
        raise SystemExit('Qt runtime required for lifecycle contract')
    directory = runtime.stage()
    try:
        source = (runtime.QML / 'MachineActions.qml').read_text()
        source = source.replace('import Quickshell\nimport Quickshell.Io\n', '')
        source = source.replace('Scope {', 'Item {', 1)
        # Keep the production dispatch-exit handler while substituting only
        # the transport. A short bridge exit must not settle managed work.
        start = source.index('        onExited:', source.index('id: operationRunner'))
        end = source.index('\n    }', start)
        exit_handler = source[start:end]
        source = runtime.strip_blocks(source, 'Component', 'Process', 'Timer')
        source = source.replace('    id: machineActions', '''    id: machineActions
    property alias trackerFixture: operationState
    property alias runnerFixture: operationRunner
    QtObject {
        id: operationRunner
        property bool running: false
        property string failureDetail: ""
        property var command: []
        signal exited(int exitCode, int exitStatus)
        @@EXIT_HANDLER@@
    }'''.replace('@@EXIT_HANDLER@@', exit_handler))
        (directory / 'MachineActions.qml').write_text(source)
        source, messages = runtime.scenario_source(1920, 1080, runtime.machines(3), BODY)
        source = source.replace('    ShellState { id: sharedState }', '''    ShellState { id: sharedState }
    MachineActions { id: lifecycle }
    OperationTracker { id: recovery }''')
        runtime.run(runner, directory, 'operation-lifecycle', source, messages)
    finally:
        shutil.rmtree(directory)
    print('HyperLab operation QML contract: OK')


if __name__ == '__main__':
    main()
