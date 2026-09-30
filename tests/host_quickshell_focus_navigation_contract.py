#!/usr/bin/env python3
"""Pin internal state-only navigation and external compositor raise semantics.

Use the existing offscreen production-QML harness: only transports/windows
are substituted. Observe the real WorkspaceSurface signal-to-action connection.
No compositor, VM, GPU, service or lifecycle operation is executed.
"""
from __future__ import annotations

import re
import shutil

import host_quickshell_runtime_contract as runtime

QML = runtime.QML


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"HyperLab focus navigation contract: {message}")


def check_routes() -> None:
    # New callers must be classified as internal or external during review.
    # Strip comments so prose cannot satisfy the executable route inventory.
    sources = {
        path.name: re.sub(r"//[^\n]*|/\*.*?\*/", "", path.read_text(), flags=re.S)
        for path in QML.glob("*.qml")
    }
    expected = {
        "openWorkspace": {"HyperLabBar.qml": 2, "ShellIpc.qml": 3,
                          "ShellSurfaces.qml": 1},
        "openWorkspacePage": {"HyperLabBar.qml": 2, "LauncherSurface.qml": 1,
                              "SystemPanel.qml": 1, "ShellSurfaces.qml": 3},
        "switchWorkspace": {"WorkspaceSurface.qml": 1},
        "selectMachine": {"MachineStage.qml": 2, "LauncherSurface.qml": 1},
        "workspaceRaiseRequested": {"ShellSurfaces.qml": 1},
        "openSubpage": {"ControlCenterView.qml": 1, "DiagnosticsView.qml": 1},
        "toggleWorkspace": {"HyperLabBar.qml": 1},
        "forceActiveFocus": {"ConfirmationSurface.qml": 2,
                             "LauncherSurface.qml": 1},
        "requestActivate": {},
    }
    for method, owners in expected.items():
        actual = {}
        for name, source in sources.items():
            count = len(re.findall(r"\." + method + r"\s*\(", source))
            if count:
                actual[name] = count
        require(actual == owners, f"unreviewed {method} routes: {actual}")

    invocations = {
        name: len(re.findall(r'\.invoke\("workspace-window-focus"\)', source))
        for name, source in sources.items()
        if re.search(r'\.invoke\("workspace-window-focus"\)', source)
    }
    require(invocations == {"WorkspaceSurface.qml": 1},
            "workspace focus bypassed the single raise-signal receiver")
    require(re.search(
        r'function onWorkspaceRaiseRequested\(\)\s*\{\s*'
        r'workspace.shellActions.invoke\("workspace-window-focus"\);\s*\}',
        sources["WorkspaceSurface.qml"]), "raise receiver changed")
    require(len(re.findall(
        r'selectMachine\(\s*String\(modelData.name\),\s*'
        r'stage.shellState.machinesGeneration,\s*false\s*\)',
        sources["MachineStage.qml"])) == 2,
        "grid or dense selection lost internal no-raise semantics")


SCENARIO = r'''
            function findWhere(item, predicate) {
                if (!item) return null;
                if (predicate(item)) return item;
                for (const child of item.children || []) {
                    const found = findWhere(child, predicate);
                    if (found) return found;
                }
                return null;
            }
            function raises() {
                return sharedActions.invoked.filter(
                    action => action === "workspace-window-focus").length;
            }
            function control(root, label) {
                return findWhere(root, item => item.accessibleName === label
                    && typeof item.activated === "function");
            }

            // Opening a closed window is mapping, not redundant refocusing.
            sharedSurfaces.openWorkspace("machines");
            check(raises() === 0, "first open redundantly refocused");
            sharedSurfaces.openWorkspace("machines");
            check(raises() === 1, "external reopen lost its raise");
            let baseline = raises();

            // Exercise the actual grid/dense delegate signal, not a copied call.
            const card = findWhere(workspaceSurface, item => item.visible
                && item.machine && item.machine.name === "fixture-000"
                && typeof item.activated === "function");
            check(card !== null, "visible machine delegate missing");
            if (card) {
                card.activated();
                card.activated();
            }
            check(sharedSurfaces.selectedMachineId === "fixture-000",
                  "machine delegate failed to select");
            check(raises() === baseline, "machine delegate refocused");
            sharedSurfaces.clearMachineSelection();
            check(raises() === baseline, "clearing selection refocused");

            // Native workspace tabs, including repeated clicks on active tabs.
            for (const label of ["Control Center", "Diagnostics", "Machines"]) {
                const tab = control(workspaceSurface, label);
                check(tab !== null, "workspace tab missing");
                if (tab) { tab.activated(); tab.activated(); }
                check(raises() === baseline, "internal workspace tab refocused");
            }
            for (const view of ["controls", "diagnostics"]) {
                sharedSurfaces.switchWorkspace(view);
                const frame = findWhere(workspaceSurface, item => item.visible
                    && typeof item.sectionRequested === "function");
                check(frame !== null, "subpage frame missing");
                for (const page of sharedSurfaces.subpages[view]) {
                    if (frame) frame.sectionRequested(page);
                    check(sharedSurfaces.subpage === page,
                          "internal section navigation did not reach page");
                    check(raises() === baseline, "internal subpage refocused");
                }
            }
            sharedSurfaces.openWorkspacePage("controls", "audio", false);
            check(raises() === baseline, "internal deep link refocused");
            sharedSurfaces.openSubpage("invalid");
            sharedSurfaces.openWorkspace("invalid");
            sharedSurfaces.selectMachine("", 1);
            check(raises() === baseline, "invalid navigation refocused");

            // Dialog keyboard focus is local to the existing window.
            sharedSurfaces.requestConfirmation({kind: "session",
                actionId: "session-lock", targetId: "host", targetName: "Host",
                title: "Fixture", consequence: "No operation will be run",
                confirmLabel: "Fixture", requiresName: false, generation: -1});
            sharedSurfaces.cancelConfirmation();
            sharedSurfaces.openLauncher("");
            sharedSurfaces.closeLauncher();
            sharedSurfaces.openSystemPanel("");
            sharedSurfaces.closeSystemPanel();
            sharedSurfaces.showOsd("audio", "");
            sharedSurfaces.dismissAll();
            check(raises() === baseline, "transient or confirmation refocused");

            // External deep links and selections still raise exactly once.
            sharedSurfaces.openWorkspacePage("diagnostics", "session");
            check(raises() === ++baseline, "external deep link lost raise");
            sharedSurfaces.selectMachine("fixture-001", 1);
            check(raises() === ++baseline, "external machine selection lost raise");
            sharedSurfaces.openLauncher("");
            launcher.query = "diagnostics";
            launcher.activate(0);
            check(raises() === ++baseline, "launcher destination lost raise");
            sharedSurfaces.openLauncher("");
            launcher.query = "fixture-002";
            let position = -1;
            for (let index = 0; index < launcher.selectable.length; index++) {
                if (launcher.results[launcher.selectable[index]].kind === "machine") {
                    position = index; break;
                }
            }
            check(position >= 0, "launcher machine result missing");
            launcher.activate(position);
            check(raises() === ++baseline, "launcher machine lost raise");
            sharedSurfaces.openSystemPanel("");
            const panelLink = control(systemPanel, "Open the Control Center");
            check(panelLink !== null, "SystemPanel destination missing");
            if (panelLink) panelLink.activated();
            check(raises() === ++baseline, "outside panel destination lost raise");
            check(sharedSurfaces.workspaceView === "controls"
                  && sharedSurfaces.subpage === "session",
                  "SystemPanel deep link lost its page");
            check(sharedMachineActions.operations.length === 0,
                  "navigation performed a machine operation");
'''


def main() -> int:
    check_routes()
    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    require(bool(runner), "Qt runtime is required; focus regression cannot be skipped")
    directory = runtime.stage()
    try:
        for name, count in (("grid-focus", 6), ("dense-focus", 72)):
            source, messages = runtime.scenario_source(
                1920, 1080, runtime.machines(count), SCENARIO)
            runtime.run(runner, directory, name, source, messages)
    finally:
        shutil.rmtree(directory)
    print("HyperLab focus navigation contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
