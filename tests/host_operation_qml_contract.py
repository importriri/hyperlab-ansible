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

            // A Machine created from the shell is provisioned by one durable
            // operation; it is known, busy while it runs, and verified only
            // by a fresh Running observation of the new domain.
            recovery.records = [];
            recovery.inventory = [];
            recovery.inventoryObservedAt = (epoch + 1) * 1000;
            recovery.now = (epoch + 1) * 1000;
            const six = "f".repeat(32);
            check(recovery.snapshot({schema: 1, operations: [
                payload(six, "made-01", "running", 1, null, "machine.provision")]}),
                  "a provisioning record made the operation snapshot unknown");
            check(recovery.known && recovery.busyFor("made-01")
                  && recovery.records[0].verb === "provision",
                  "provisioning was not tracked as its own operation");
            recovery.apply(payload(six, "made-01", "succeeded", 2, 0, "machine.provision"), six);
            check(recovery.records[0].phase === "verifying",
                  "provisioning success claimed a Machine before inventory saw it");
            recovery.inventory = [{name: "made-01", state: "running"}];
            recovery.inventoryObservedAt = (epoch + 3) * 1000;
            check(recovery.records[0].phase === "completed",
                  "fresh Running did not verify the provisioned Machine");

            // A Workbench seal is its own known operation. The domain stays
            // shut off, so only a fresh Workbench registry reading that shows
            // the candidate captured verifies it.
            recovery.records = [];
            recovery.inventory = [];
            recovery.workbench = [{domain: "arch-dev", state: "candidate"}];
            recovery.workbenchObservedAt = (epoch + 1) * 1000;
            recovery.now = (epoch + 1) * 1000;
            const seven = "1".repeat(32);
            check(recovery.snapshot({schema: 1, operations: [
                payload(seven, "arch-dev", "running", 1, null, "workbench.seal")]}),
                  "a seal record made the operation snapshot unknown");
            check(recovery.known && recovery.busyFor("arch-dev")
                  && recovery.records[0].verb === "seal",
                  "the seal was not tracked as its own operation");
            recovery.apply(payload(seven, "arch-dev", "succeeded", 2, 0, "workbench.seal"), seven);
            recovery.inventory = [{name: "arch-dev", state: "shut off"}];
            recovery.inventoryObservedAt = (epoch + 3) * 1000;
            check(recovery.records[0].phase === "verifying",
                  "a shut-off domain was taken as proof of a seal");
            recovery.workbenchObservedAt = (epoch + 3) * 1000;
            check(recovery.records[0].phase === "verifying",
                  "a candidate not yet captured verified the seal");
            recovery.workbench = [{domain: "arch-dev", state: "captured"}];
            recovery.workbenchObservedAt = (epoch + 4) * 1000;
            check(recovery.records[0].phase === "completed" && !recovery.busyFor("arch-dev"),
                  "a captured candidate did not verify the seal");
            recovery.records = [];
            recovery.workbench = [];
            recovery.snapshot({schema: 1, operations: [
                payload(seven, "arch-dev", "succeeded", 2, 0, "workbench.seal")]});
            recovery.now = (epoch + 2 + 61) * 1000;
            check(recovery.records[0].phase === "unverified"
                  && recovery.records[0].detail.indexOf("did not show the capture") >= 0,
                  "an unobserved seal was not reported unverified");

            // A candidate is not in the product inventory: its Start is
            // verified by a fresh Workbench reading showing it running.
            recovery.records = [];
            recovery.inventory = [];
            recovery.workbench = [{domain: "arch-gaming", state: "candidate", runtime: "shut off"}];
            recovery.workbenchObservedAt = (epoch + 1) * 1000;
            recovery.now = (epoch + 1) * 1000;
            const eight = "2".repeat(32);
            recovery.snapshot({schema: 1, operations: [
                payload(eight, "arch-gaming", "succeeded", 2, 0, "vm.managed-start")]});
            check(recovery.records[0].phase === "verifying",
                  "a candidate's Start was verified by a stale reading");
            recovery.workbench = [{domain: "arch-gaming", state: "candidate", runtime: "running"}];
            recovery.workbenchObservedAt = (epoch + 3) * 1000;
            check(recovery.records[0].phase === "completed",
                  "a fresh Workbench reading did not verify the candidate's Start");

            // The Workbench answer is validated by the real transport: a
            // well-formed reading reaches the view and the tracker, anything
            // else is unavailable and never a list of candidates.
            const bench = {phase: "workbench", available: true, errors: [], candidates: [
                {domain: "arch-dev", image_id: "arch-dev-standard", base_image: "arch",
                 profile: "dev", state: "candidate", runtime: "shut off", adopted_at: "",
                 sha256: null}]};
            check(lifecycle.applyWorkbench(JSON.stringify(bench), 0, "")
                  && lifecycle.workbenchState === "ready"
                  && lifecycle.workbenchCandidates.length === 1,
                  "a valid Workbench reading was refused");
            check(lifecycle.trackerFixture.workbench.length === 1
                  && lifecycle.trackerFixture.workbenchObservedAt > 0,
                  "the tracker did not receive the Workbench reading");
            for (const bad of [
                Object.assign({}, bench, {phase: "capabilities"}),
                Object.assign({}, bench, {candidates: [Object.assign({}, bench.candidates[0], {domain: "../etc"})]}),
                Object.assign({}, bench, {candidates: [Object.assign({}, bench.candidates[0], {state: "sealed"})]}),
                Object.assign({}, bench, {candidates: [Object.assign({}, bench.candidates[0], {sha256: "abc"})]})]) {
                check(!lifecycle.applyWorkbench(JSON.stringify(bad), 0, "")
                      && lifecycle.workbenchState === "unavailable",
                      "a malformed Workbench reading was accepted");
            }
            check(!lifecycle.applyWorkbench(JSON.stringify(bench), 2, "HyperLab: registry unreadable")
                  && lifecycle.workbenchDetail === "registry unreadable",
                  "a failed Workbench read did not say why");
            check(lifecycle.applyWorkbench(JSON.stringify(Object.assign({}, bench, {candidates: []})), 0, "")
                  && lifecycle.workbenchState === "empty", "an empty Workbench was not empty");

            // Allowing a USB device (ADR 0038) is its own operation: one per
            // port whatever its scope, its refusal says why, and only a fresh
            // USB reading showing the port authorized verifies it.
            const usbTracker = lifecycle.trackerFixture;
            lifecycle.runnerFixture.running = false;
            lifecycle.pendingVerb = "";
            lifecycle.pendingMachine = "";
            usbTracker.records = [];
            check(usbTracker.snapshot({schema: 1, operations: []}), "the USB fixture snapshot was refused");
            check(!lifecycle.allowUsb("usb1", "once") && !lifecycle.allowUsb("1-2", "always")
                  && !lifecycle.allowUsb("1-2/../x", "once") && !lifecycle.allowUsb("1-2\n", "once"),
                  "a malformed USB allow was dispatched");
            check(lifecycle.allowUsb("1-2", "once"), "a valid USB allow was refused");
            check(JSON.stringify(lifecycle.runnerFixture.command)
                  === JSON.stringify([lifecycle.bridge, "usb-allow", "1-2", "once"]),
                  "the USB allow did not reach the bridge as its port and scope");
            check(!lifecycle.allowUsb("1-2", "permanent"), "a second allow of the same port was dispatched");
            const nine = "9".repeat(32);
            lifecycle.applyOperationLine(JSON.stringify(
                payload(nine, "usb:1-2:once", "dispatched", 0, null, "usb.allow")));
            lifecycle.runnerFixture.running = false;
            lifecycle.runnerFixture.exited(0, 0);
            check(lifecycle.usbBusy("1-2") && !lifecycle.usbBusy("1-3"),
                  "a dispatched USB allow did not hold exactly its own port");
            check(lifecycle.allowUsb("1-3", "permanent"), "another port was held by the first allow");
            lifecycle.applyOperationLine(JSON.stringify({phase: "refused",
                reason: "a device that presents a keyboard or mouse is allowed only from a terminal"}));
            check(lifecycle.runnerFixture.failureDetail.indexOf("keyboard or mouse") >= 0,
                  "a USB refusal lost its reason");
            lifecycle.runnerFixture.running = false;
            lifecycle.runnerFixture.exited(2, 0);
            const usbPhase = () => usbTracker.records.find(r => r.id === nine).phase;
            usbTracker.apply(payload(nine, "usb:1-2:once", "succeeded", 2, 0, "usb.allow"), nine);
            check(usbPhase() === "verifying", "a USB allow claimed success before a reading");
            usbTracker.usb = [{port: "1-2", authorized: 0}];
            usbTracker.usbObservedAt = (epoch + 3) * 1000;
            check(usbPhase() === "verifying", "a device still blocked verified the allow");
            usbTracker.usb = [{port: "1-2", authorized: 1}];
            usbTracker.usbObservedAt = (epoch + 4) * 1000;
            check(usbPhase() === "completed" && !lifecycle.usbBusy("1-2"),
                  "a fresh reading of the allowed device did not verify the allow");

            // The USB answer is validated by the real transport.
            const usbAnswer = {phase: "usb", devices: [
                {port: "1-2", vendor_id: "0781", product_id: "5581", manufacturer: "SanDisk",
                 product: "Ultra", serial: null, authorized: 0, interfaces: ["08"], hid: false}]};
            check(lifecycle.applyUsb(JSON.stringify(usbAnswer), 0, "")
                  && lifecycle.usbState === "ready" && lifecycle.usbDevices.length === 1
                  && usbTracker.usb.length === 1,
                  "a valid USB reading was refused or did not reach the tracker");
            for (const change of [{port: "../1-2"}, {port: "usb1"}, {hid: "no"}, {authorized: 2},
                                  {interfaces: ["3"]}, {vendor_id: "XYZ1"}, {product: 7}]) {
                const bad = {phase: "usb", devices: [Object.assign({}, usbAnswer.devices[0], change)]};
                check(!lifecycle.applyUsb(JSON.stringify(bad), 0, "")
                      && lifecycle.usbState === "unavailable",
                      "a malformed USB reading was accepted");
            }
            check(!lifecycle.applyUsb(JSON.stringify(usbAnswer), 2, "HyperLab: invalid USB device list")
                  && lifecycle.usbDetail === "invalid USB device list",
                  "a failed USB read did not say why");
            check(lifecycle.applyUsb(JSON.stringify({phase: "usb", devices: []}), 0, "")
                  && lifecycle.usbState === "empty", "no USB devices was not empty");


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
