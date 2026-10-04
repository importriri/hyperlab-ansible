#!/usr/bin/env python3
"""Isolated Qt runtime contract for the shared HyperLab shell.

Static contracts cannot tell whether the shell can instantiate. C9.2 shipped a
root that assigned a property the rail does not declare while the component
that required it received none, and every text-matching gate stayed green.

This contract loads the real production QML in an offscreen Qt process with
controlled fixtures and no bridge, service, compositor or hardware access. It
asserts three things:

  1. the tree instantiates and Qt reports nothing on stderr -- a binding
     error, an unknown property or a type error all surface there;
  2. the truth rules hold under adversarial input: an unreadable source never
     looks empty, a default is never published as an observation, and a claim
     is only accepted at its canonical rung;
  3. the behaviour rules hold: every destination opens, selection resolves by
     identifier, confirmation is target-bound and spent exactly once, and
     nothing lands outside a small viewport.

Layer-shell and floating-window hosts are adapted to plain items in a
temporary copy, each given a named output fixture (two outputs, as a laptop
with an external display reports them), so empty output names can never mask
a routing fault. Capability replies are bridge-shaped JSON passed through the
real ShellState correlation and validation.

What this harness does NOT prove, and what therefore remains physical
acceptance: the real shell.qml root under Quickshell (its wiring is pinned by
text in check_root_wiring), native window activation and compositor focus,
real process lifetimes and cancellation ordering, layer-shell keyboard grabs,
and hotplug of real outputs. Nothing here writes to the repository, and no
fixture value ever reaches runtime.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QML = ROOT / "roles/host_desktop_common/files/quickshell/hyperlab"
PALETTE = ROOT / "themes/trust-model/rendered/hyperlab-palette-quickshell.json"
OUT = os.environ.get("HYPERLAB_RENDER_OUT")

# Surfaces whose host is a compositor window in production.
WINDOW_FILES = (
    "HyperLabDesktop.qml",
    "HyperLabBar.qml",
    "OsdSurface.qml",
    "LauncherSurface.qml",
    "SystemPanel.qml",
    "WorkspaceSurface.qml",
)

# Replaced by fixtures: transport, not truth or presentation.
STUBBED = ("ShellActions.qml", "MachineActions.qml", "ShellIpc.qml", "shell.qml")


def strip_blocks(source: str, *type_names: str) -> str:
    """Remove whole `Type { ... }` object blocks, braces balanced."""
    for name in type_names:
        while True:
            match = re.search(r"(?m)^([ \t]*)" + name + r"[ \t]*\{", source)
            if not match:
                break

            index = match.end()
            depth = 1
            while index < len(source) and depth:
                if source[index] == "{":
                    depth += 1
                elif source[index] == "}":
                    depth -= 1
                index += 1

            source = source[:match.start()] + source[index:]

    return source


def adapt_window(source: str) -> str:
    """Adapt a layer-shell or floating window host to a plain rectangle."""
    for line in (
        "import Quickshell.Wayland\n",
        "import Quickshell.Io\n",
        "import Quickshell\n",
    ):
        source = source.replace(line, "")

    floating = "FloatingWindow {" in source

    source = source.replace("PanelWindow {", "Rectangle {")
    source = source.replace("FloatingWindow {", "Rectangle {")
    source = source.replace("    screen: modelData\n", "")

    # Window-host properties are declared rather than stripped, so the
    # bindings that compute them stay under test.
    if floating:
        source = source.replace(
            "Rectangle {\n    id: workspace\n",
            "Rectangle {\n    id: workspace\n\n"
            "    property string title\n"
            "    property var minimumSize\n"
            "    property var screen: null\n",
            1,
        )

    source = re.sub(
        r"    anchors \{\n        top: true\n        bottom: true\n"
        r"        left: true\n        right: true\n    \}\n",
        "    anchors.fill: parent\n",
        source,
    )
    source = re.sub(
        r"    anchors \{\n        top: true\n        left: true\n"
        r"        right: true\n    \}\n",
        "    anchors.left: parent.left\n    anchors.right: parent.right\n"
        "    anchors.top: parent.top\n    height: implicitHeight\n",
        source,
    )
    source = re.sub(
        r"(?m)^\s*WlrLayershell\.keyboardFocus:\n\s+.*\n", "", source
    )
    source = re.sub(
        r"(?m)^\s*(exclusiveZone: .*|WlrLayershell\..*)\n",
        "",
        source,
    )
    source = source.replace("    mask: Region {}\n", "")
    source = re.sub(r"    mask: Region \{.*?\n    \}\n\n", "", source, flags=re.S)

    # A plain item has no output of its own; the harness gives every surface
    # a named screen fixture, exactly as production screens are named, so
    # an empty origin can never silently own a transient surface.
    source = source.replace(
        "    property var modelData\n", "    property var screen: null\n"
    )

    return source


def adapt_state(source: str) -> str:
    """Keep every truth rule; remove only the process and file transport."""
    source = source.replace("import Quickshell\nimport Quickshell.Io\n", "")
    source = source.replace("Scope {", "Item {", 1)
    source = strip_blocks(source, "Process", "FileView", "SystemClock", "Timer")
    source = source.replace(
        "    readonly property alias clock: shellClock\n",
        "    property var clock: QtObject {\n"
        "        readonly property date date: new Date(2026, 8, 22, 9, 41)\n"
        "    }\n",
    )
    source = re.sub(r"(?m)^\s+(themeStateFile|keyboardStateFile"
                    r"|wallpaperModeStateFile|rgbModeStateFile|reducedMotionStateFile"
                    r"|paletteFile)\.reload\(\);\n", "", source)
    source = re.sub(
        r"    Component\.onCompleted: \{[^}]*\}\n", "", source
    )
    source = re.sub(
        r"(?m)^\s+if \(!\w+Process\.running\)\n\s+\w+Process\.running = true;\n",
        "",
        source,
    )
    return source


def adapt_theme(source: str) -> str:
    source = source.replace("import Quickshell\nimport Quickshell.Io\n", "")
    source = source.replace("Scope {", "QtObject {", 1)
    source = strip_blocks(source, "FileView")
    source = re.sub(r"    Component\.onCompleted: \{.*?\n    \}\n", "", source,
                    flags=re.S)
    source = source.replace("        paletteFile.reload();\n", "")
    source += (
        "\n// Fixture: the reviewed rendered palette, applied directly.\n"
    )
    return source


def stage() -> Path:
    directory = Path(tempfile.mkdtemp(prefix="hyperlab-runtime-"))

    for path in QML.glob("*.qml"):
        if path.name in STUBBED:
            continue

        text = path.read_text(encoding="utf-8")

        if path.name in WINDOW_FILES:
            text = adapt_window(text)
        elif path.name == "ShellState.qml":
            text = adapt_state(text)
        elif path.name == "Theme.qml":
            text = adapt_theme(text)

        (directory / path.name).write_text(text)

    return directory


MACHINE_TEMPLATE = {
    "state": "running",
    "provenance": "clean",
    "gpu": "GPU held",
    "gpu_relation": "held",
    "memory_mb": 8192,
    "vcpus": 4,
    "network": "clean",
    "networks": ["clean"],
    "managed": True,
    "vfio": True,
    "lifecycle": "permanent",
    "device_profile": "vfio",
    "blocked": None,
    "os": "Arch Linux",
}


def machines(count: int) -> list[dict]:
    order = ("clean", "dev", "services", "dirty", "lab", "unclassified")
    states = ("running", "shut off", "paused", "unknown")
    rows = []

    for index in range(count):
        row = dict(MACHINE_TEMPLATE)
        row["name"] = f"fixture-{index:03d}"
        row["provenance"] = order[index % len(order)]
        row["state"] = states[index % len(states)]
        row["gpu_relation"] = "held" if index == 0 else "configured"
        if index % 5 == 0:
            row["os"] = None
            row["networks"] = None
            row["network"] = None
            row["vcpus"] = None
        rows.append(row)

    return rows


HARNESS = """import QtQuick
import QtQuick.Window

Window {
    id: window

    width: @@WIDTH@@
    height: @@HEIGHT@@
    visible: true
    color: sharedTheme.base

    // This Qt build emits nothing for console output, so the first failing
    // check is reported through the exit code and resolved back to its
    // source text by the harness.
    property int firstFailure: -1

    function check(condition, code) {
        if (!condition && window.firstFailure < 0)
            window.firstFailure = code;
    }

    function find(item, name) {
        if (!item)
            return null;

        if (item.objectName === name)
            return item;

        const children = item.children || [];

        for (let index = 0; index < children.length; index++) {
            const found = find(children[index], name);

            if (found)
                return found;
        }

        return null;
    }

    Tokens { id: sharedTokens }
    Icons { id: sharedIcons }

    Theme {
        id: sharedTheme
        Component.onCompleted: {
            sharedTheme.palette = @@PALETTE@@;
            sharedTheme.paletteAvailable = true;
        }
    }

    // Two named outputs, as a laptop with an external display reports them.
    // activeOutput mirrors the shell root's resolution (pinned statically to
    // shell.qml by main()): the observed focused output when it is live,
    // otherwise the first live output -- never "every output".
    ShellSurfaces {
        id: sharedSurfaces

        liveOutputs: ["eDP-1", "HDMI-A-1"]
        activeOutput: {
            const focused = sharedState.focusedOutput;

            return sharedSurfaces.liveOutputs.indexOf(focused) >= 0
                ? focused
                : (sharedSurfaces.liveOutputs.length > 0
                    ? sharedSurfaces.liveOutputs[0]
                    : "");
        }
    }
    ShellState { id: sharedState }

    // Transport fixtures. They record intent and perform nothing.
    QtObject {
        id: sharedActions

        property var invoked: []
        property var workspaces: []
        property bool busy: false
        // False simulates a full queue: the action layer refuses.
        property bool accepting: true

        function labelFor(action) { return String(action); }

        function invoke(action) {
            if (!accepting)
                return false;
            invoked.push(String(action));
            return true;
        }

        function invokeWorkspace(slot) {
            if (!Number.isInteger(Number(slot)) || slot < 1 || slot > 9)
                return false;
            workspaces.push(Number(slot));
            return true;
        }
    }

    // Transport fixture. The capability reply is bridge-shaped JSON handed to
    // the real ShellState correlation and validation, so what the pane shows
    // is what production validation accepts -- not a hand-written answer.
    QtObject {
        id: sharedMachineActions

        property var operations: []
        property string capabilityState: @@CAPABILITY_STATE@@
        property var capabilityVerbs: @@CAPABILITY_VERBS@@
        property int serial: 0
        property var connections: []
        property bool busy: false

        readonly property var verbs: ["start", "shutdown", "reboot",
            "console", "ssh", "looking-glass", "force-stop"]
        readonly property var connectVerbs: ["console", "ssh", "looking-glass"]
        readonly property var powerVerbs: ["start", "shutdown", "reboot"]
        readonly property var advancedVerbs: ["force-stop"]

        // Active durable operations by machine, shaped like the tracker's
        // presentation records ({id, machine, verb, phase, ...}). Empty means
        // no operation to reattach to; a scenario may add one.
        property var activeOperations: ({})
        property var viewed: []

        function activeOperationFor(machine) {
            return activeOperations[String(machine)] || null;
        }
        function viewOperation(machine) {
            const record = activeOperationFor(machine);
            if (record === null)
                return false;
            viewed = viewed.concat([record.id]);
            return true;
        }

        // Mirrors MachineActions.labelFor so the fixture reads like the
        // product rather than like its verb identifiers.
        function busyFor(machine) { return busy; }
        function labelFor(verb) {
            switch (String(verb)) {
            case "start": return "Start";
            case "shutdown": return "Shut down";
            case "reboot": return "Reboot guest";
            case "console": return "Console";
            case "ssh": return "SSH";
            case "looking-glass": return "Looking Glass";
            case "force-stop": return "Force stop";
            default: return "Operation";
            }
        }

        function destructive(verb) { return String(verb) === "force-stop"; }

        function reply(machine) {
            return JSON.stringify({
                phase: "capabilities",
                machine: { name: String(machine), state: "running",
                           managed: true, vfio: true },
                verbs: capabilityVerbs
            });
        }

        function probe(machine, generation) {
            serial += 1;
            sharedState.beginCapabilityRequest(serial, String(machine), generation);
            if (capabilityState === "ok")
                sharedState.applyCapabilityAnswer(
                    serial, String(machine), reply(machine), 0, "");
            else
                sharedState.applyCapabilityAnswer(
                    serial, String(machine), "", 2, "fixture bridge unavailable");
            return true;
        }
        function clearCapabilities() {
            serial += 1;
            sharedState.clearCapabilities();
        }
        function connectionActive(machine, verb) {
            return connections.indexOf(String(verb) + "\n" + String(machine)) >= 0;
        }
        function invoke(verb, machine) {
            operations.push(String(verb) + ":" + String(machine));
            return true;
        }
    }

    Rectangle { anchors.fill: parent; color: sharedTheme.base }

    HyperLabDesktop {
        id: desktop
        screen: ({ "name": "eDP-1" })
        anchors.fill: parent
        tokens: sharedTokens; theme: sharedTheme; icons: sharedIcons
        shellState: sharedState; shellSurfaces: sharedSurfaces
    }

    WorkspaceSurface {
        id: workspaceSurface
        anchors.fill: parent
        anchors.topMargin: sharedTokens.barHeight
        tokens: sharedTokens; theme: sharedTheme; icons: sharedIcons
        shellState: sharedState; shellActions: sharedActions
        machineActions: sharedMachineActions; shellSurfaces: sharedSurfaces
    }

    HyperLabBar {
        id: rail
        screen: ({ "name": "eDP-1" })
        tokens: sharedTokens; theme: sharedTheme; icons: sharedIcons
        shellState: sharedState; shellActions: sharedActions
        shellSurfaces: sharedSurfaces
    }

    SystemPanel {
        id: systemPanel
        screen: ({ "name": "eDP-1" })
        anchors.fill: parent
        tokens: sharedTokens; theme: sharedTheme; icons: sharedIcons
        shellState: sharedState; shellActions: sharedActions
        shellSurfaces: sharedSurfaces
    }

    OsdSurface {
        id: osd
        screen: ({ "name": "eDP-1" })
        anchors.fill: parent
        tokens: sharedTokens; theme: sharedTheme; icons: sharedIcons
        shellState: sharedState; shellSurfaces: sharedSurfaces
    }

    LauncherSurface {
        id: launcher
        screen: ({ "name": "eDP-1" })
        anchors.fill: parent
        tokens: sharedTokens; theme: sharedTheme; icons: sharedIcons
        shellState: sharedState; shellActions: sharedActions
        shellSurfaces: sharedSurfaces
    }

    // The same surfaces on the second output. Exactly one of each pair may
    // ever be visible.
    SystemPanel {
        id: systemPanelExternal
        screen: ({ "name": "HDMI-A-1" })
        tokens: sharedTokens; theme: sharedTheme; icons: sharedIcons
        shellState: sharedState; shellActions: sharedActions
        shellSurfaces: sharedSurfaces
    }

    OsdSurface {
        id: osdExternal
        screen: ({ "name": "HDMI-A-1" })
        tokens: sharedTokens; theme: sharedTheme; icons: sharedIcons
        shellState: sharedState; shellSurfaces: sharedSurfaces
    }

    LauncherSurface {
        id: launcherExternal
        screen: ({ "name": "HDMI-A-1" })
        tokens: sharedTokens; theme: sharedTheme; icons: sharedIcons
        shellState: sharedState; shellActions: sharedActions
        shellSurfaces: sharedSurfaces
    }

    Component.onCompleted: {
        sharedState.applyMachinePayload(JSON.stringify(@@INVENTORY@@));
        sharedState.applyTrustPayload(JSON.stringify(@@TRUST@@));
        sharedState.applyGpuPayload(JSON.stringify(@@GPU@@));
        sharedState.applyTelemetryPayload(JSON.stringify(@@TELEMETRY@@));
        sharedState.applyWorkspacePayload(JSON.stringify(@@WORKSPACES@@));
        sharedState.applyFocusPayload(JSON.stringify(@@FOCUS@@));
    }

    Timer {
        id: settleTimer

        property var callback: null

        interval: 400
        repeat: false

        onTriggered: if (settleTimer.callback) settleTimer.callback()
    }

    Timer {
        interval: 400
        running: true
        repeat: false

        onTriggered: {
            @@SCENARIO@@
            @@GRAB@@
        }
    }
}
"""


FAILURE_BASE = 40


def number_checks(body: str) -> tuple[str, list[str]]:
    """Replace each check message with an index, keeping the text."""
    messages: list[str] = []
    out: list[str] = []
    index = 0

    while True:
        position = body.find("check(", index)

        if position < 0:
            out.append(body[index:])
            break

        out.append(body[index:position])

        cursor = position + len("check(")
        depth = 1
        comma = -1

        while cursor < len(body) and depth:
            character = body[cursor]

            if character in "([{":
                depth += 1
            elif character in ")]}":
                depth -= 1
            elif character == "," and depth == 1 and comma < 0:
                comma = cursor
            elif character == '"':
                cursor += 1
                while cursor < len(body) and body[cursor] != '"':
                    cursor += 2 if body[cursor] == "\\" else 1

            cursor += 1

        condition = body[position + len("check("):comma].strip()
        message = body[comma + 1:cursor - 1].strip()

        out.append(f"check({condition}, {len(messages)})")
        messages.append(" ".join(message.split()))

        index = cursor

    return "".join(out), messages


def scenario_source(
    width: int,
    height: int,
    inventory: list[dict],
    body: str,
    capability_state: str = '"ok"',
    capability_verbs: str | None = None,
    trust: dict | None = None,
    gpu: dict | None = None,
    out: str = "",
) -> tuple[str, list[str]]:
    verbs = capability_verbs or json.dumps({
        "start": {"available": False, "reason": "machine is already running"},
        "shutdown": {"available": True, "reason": ""},
        "reboot": {"available": True, "reason": ""},
        "console": {"available": True, "reason": ""},
        "ssh": {
            "available": False,
            "reason": "strict runtime SSH inventory is unavailable",
        },
        "looking-glass": {"available": True, "reason": ""},
        "force-stop": {"available": True, "reason": ""},
    })

    exit_call = (
        "Qt.exit(window.firstFailure < 0 ? 0 : "
        + str(FAILURE_BASE)
        + " + window.firstFailure);"
    )

    # A surface that has just opened is mid-animation, so the screenshot
    # waits for the entry transition to settle before grabbing.
    grab = (
        "settleTimer.callback = function() { "
        "window.contentItem.grabToImage(function(result) { "
        f'result.saveToFile("{out}"); {exit_call} }}); }}; '
        "settleTimer.restart();"
        if out else exit_call
    )

    numbered, messages = number_checks(body)

    return (
        HARNESS
        .replace("@@WIDTH@@", str(width))
        .replace("@@HEIGHT@@", str(height))
        .replace("@@PALETTE@@", PALETTE.read_text(encoding="utf-8"))
        .replace("@@CAPABILITY_STATE@@", capability_state)
        .replace("@@CAPABILITY_VERBS@@", verbs)
        .replace(
            "@@INVENTORY@@",
            json.dumps({
                "text": f"{len(inventory)}/{len(inventory)}",
                "class": "ok",
                "machines_available": True,
                "machines": inventory,
            }),
        )
        .replace(
            "@@TRUST@@",
            json.dumps(trust or {
                "text": "clean 3", "tooltip": "GPU claimed for clean",
                "class": "warn", "known": True, "claimed": True,
                "identity": "clean", "level": 3,
            }),
        )
        .replace(
            "@@GPU@@",
            json.dumps(gpu or {
                "text": "fixture-000", "class": "",
                "known": True, "owner": "fixture-000", "bound": True,
            }),
        )
        .replace(
            "@@TELEMETRY@@",
            json.dumps({
                "temperature": {"text": "48°C", "class": "", "detail": "cpu"},
                "network": {
                    "text": "wifi", "class": "", "detail": "wlan0 up",
                    "kind": "wifi",
                },
                "audio": {
                    "text": "110%", "class": "", "detail": "default sink",
                    "percent": 110, "muted": False, "maximum": 125,
                },
                "battery": {
                    "text": "80%", "class": "", "detail": "Discharging",
                    "present": True, "capacity": 80,
                },
            }),
        )
        .replace(
            "@@WORKSPACES@@",
            json.dumps({"active": 2, "output": "eDP-1",
                        "occupied": [1, 2, 5], "urgent": [5]}),
        )
        .replace(
            "@@FOCUS@@", json.dumps({"app_id": "foot", "window_id": "0x1"})
        )
        .replace("@@SCENARIO@@", numbered)
        .replace("@@GRAB@@", grab)
    ), messages


def run(
    runner: str,
    directory: Path,
    name: str,
    source: str,
    messages: list[str],
) -> None:
    scene = directory / "scenario.qml"
    scene.write_text(source)

    try:
        result = subprocess.run(
            [runner, str(scene)],
            capture_output=True,
            text=True,
            timeout=90,
            env={
                **os.environ,
                "QT_QPA_PLATFORM": "offscreen",
                "QT_QUICK_BACKEND": "software",
                # Without a controlling terminal Qt logs to journald, which
                # would hide binding errors from the noise check below.
                "QT_FORCE_STDERR_LOGGING": "1",
            },
            check=False,
        )
    except subprocess.TimeoutExpired:
        # An uncaught JavaScript exception stops the scenario before it can
        # exit, so a hang is a runtime failure, not a slow machine.
        raise SystemExit(
            "HyperLab Quickshell runtime contract: "
            f"{name} never completed -- an uncaught runtime error"
        ) from None

    noise = "\n".join(
        line for line in result.stderr.splitlines()
        if line.strip()
        and "Could not find the Qt platform plugin" not in line
        and "QStandardPaths" not in line
        and not line.startswith("qt.tools.qmlscene.deprecated:")
    )

    code = result.returncode

    if code >= FAILURE_BASE and code - FAILURE_BASE < len(messages):
        raise SystemExit(
            "HyperLab Quickshell runtime contract: "
            f"{name}: {messages[code - FAILURE_BASE]}"
        )

    if code or noise:
        raise SystemExit(
            "HyperLab Quickshell runtime contract: "
            f"{name} failed ({code})\n{noise}\n{result.stdout}"
        )

    print(f"  runtime scenario OK: {name}")


IDLE = """
            check(!sharedSurfaces.workspaceOpen,
                  "startup opened a product workspace");
            check(!workspaceSurface.visible,
                  "the workspace is visible on a quiet desktop");
            check(sharedState.machinesAvailable,
                  "the fixture inventory was rejected");
            check(rail.visible, "the rail is not visible at idle");
"""

DESTINATIONS = """
            for (const destination of ["machines", "controls", "diagnostics"]) {
                check(sharedSurfaces.openWorkspace(destination),
                      "destination refused: " + destination);
                check(sharedSurfaces.workspaceOpen,
                      "destination did not open: " + destination);
                check(sharedSurfaces.workspaceView === destination,
                      "destination did not stick: " + destination);
                check(workspaceSurface.visible,
                      "workspace hidden on: " + destination);
            }

            for (const page of ["overview", "isolation", "inventory",
                                "session"]) {
                check(sharedSurfaces.openSubpage(page),
                      "diagnostics subpage refused: " + page);
            }

            check(!sharedSurfaces.openSubpage("machines"),
                  "a foreign subpage was accepted");
            check(!sharedSurfaces.openWorkspace("nonsense"),
                  "an unknown destination was accepted");

            sharedSurfaces.closeWorkspace();
            check(!sharedSurfaces.workspaceOpen, "the workspace did not close");
"""

SELECTION = """
            sharedSurfaces.openWorkspace("machines");
            check(sharedSurfaces.selectMachine("fixture-001", 1),
                  "selection refused");
            check(sharedSurfaces.selectedMachineId === "fixture-001",
                  "selection is not an identifier");
            check(sharedState.machineById("fixture-001") !== null,
                  "identifier did not resolve against the snapshot");
            check(sharedState.machineById("gone") === null,
                  "a removed identifier resolved to something");
            check(sharedState.machineCapabilities.machine === "fixture-001",
                  "capabilities were not requested for the selection");
            check(sharedState.capabilityFor("fixture-001", "shutdown").available
                  === (sharedMachineActions.capabilityState === "ok"),
                  "the validated bridge answer did not reach presentation");

            // Selecting never operates.
            check(sharedMachineActions.operations.length === 0,
                  "selection performed an operation");
"""

CONFIRMATION = """
            sharedSurfaces.openWorkspace("machines");
            sharedSurfaces.selectMachine("fixture-001", 1);

            check(sharedSurfaces.requestConfirmation({
                kind: "machine", actionId: "force-stop",
                targetId: "fixture-001", targetName: "fixture-001",
                title: "t", consequence: "c", confirmLabel: "Force stop",
                requiresName: true, generation: 1
            }), "confirmation refused");
            check(sharedSurfaces.confirmation !== null,
                  "confirmation was not armed");
            check(sharedMachineActions.operations.length === 0,
                  "arming executed the operation");

            // Arm A, select B: the dialog must not survive to be redirected.
            sharedSurfaces.selectMachine("fixture-002", 1);
            check(sharedSurfaces.confirmation === null,
                  "a confirmation survived a changed selection");

            // Arm, then leave the destination.
            sharedSurfaces.selectMachine("fixture-001", 1);
            sharedSurfaces.requestConfirmation({
                kind: "machine", actionId: "force-stop",
                targetId: "fixture-001", targetName: "fixture-001",
                title: "t", consequence: "c", confirmLabel: "Force stop",
                requiresName: true, generation: 1
            });
            sharedSurfaces.openWorkspace("diagnostics");
            check(sharedSurfaces.confirmation === null,
                  "a confirmation survived leaving its destination");

            // Arm, then a new inventory generation.
            sharedSurfaces.openWorkspace("machines");
            sharedSurfaces.selectMachine("fixture-001", 7);
            sharedSurfaces.requestConfirmation({
                kind: "machine", actionId: "force-stop",
                targetId: "fixture-001", targetName: "fixture-001",
                title: "t", consequence: "c", confirmLabel: "Force stop",
                requiresName: true, generation: 7
            });
            sharedSurfaces.invalidateConfirmation(8);
            check(sharedSurfaces.confirmation === null,
                  "a confirmation survived a changed inventory generation");

            // Submit spends the record exactly once.
            sharedSurfaces.requestConfirmation({
                kind: "machine", actionId: "force-stop",
                targetId: "fixture-001", targetName: "fixture-001",
                title: "t", consequence: "c", confirmLabel: "Force stop",
                requiresName: true, generation: 7
            });
            const captured = sharedSurfaces.submitConfirmation();
            check(captured !== null, "submit returned nothing");
            check(captured.targetId === "fixture-001",
                  "submit returned a different target");
            check(sharedSurfaces.submitConfirmation() === null,
                  "a spent confirmation submitted twice");

            function arm(kind, action, target, generation) {
                return sharedSurfaces.requestConfirmation({
                    kind: kind, actionId: action,
                    targetId: target, targetName: target,
                    title: "t", consequence: "c", confirmLabel: "Go",
                    requiresName: kind === "machine", generation: generation
                });
            }

            // Summoning the launcher or panel over a dialog abandons it --
            // session confirmations included, which carry no generation.
            sharedSurfaces.openWorkspacePage("controls", "session");
            check(arm("session", "session-poweroff", "host", -1),
                  "a session confirmation could not be armed");
            sharedSurfaces.openLauncher("");
            check(sharedSurfaces.confirmation === null,
                  "a confirmation survived opening the launcher");
            sharedSurfaces.closeLauncher();

            arm("session", "session-reboot", "host", -1);
            sharedSurfaces.openSystemPanel("");
            check(sharedSurfaces.confirmation === null,
                  "a confirmation survived opening the system panel");
            sharedSurfaces.closeSystemPanel();

            // Locking the session withdraws anything armed.
            arm("session", "session-logout", "host", -1);
            sharedSurfaces.sessionLocking();
            check(sharedSurfaces.confirmation === null,
                  "a confirmation survived the session locking");

            // Closing the workspace withdraws it; nothing can be armed with
            // no workspace to present it in.
            arm("session", "session-logout", "host", -1);
            sharedSurfaces.closeWorkspace();
            check(sharedSurfaces.confirmation === null,
                  "a confirmation survived leaving the workspace");
            check(!arm("session", "session-logout", "host", -1),
                  "a confirmation was armed with no workspace open");

            // An identical inventory poll is not a change: the dialog stays.
            sharedSurfaces.openWorkspace("machines");
            sharedSurfaces.selectMachine("fixture-001", sharedState.machinesGeneration);
            arm("machine", "force-stop", "fixture-001", sharedState.machinesGeneration);
            const unchanged = JSON.stringify({ machines_available: true,
                machines: sharedState.machines });
            sharedState.applyMachinePayload(unchanged);
            check(sharedSurfaces.confirmation !== null,
                  "an unchanged inventory poll threw the dialog away");

            // The target's state changes: it is withdrawn.
            const moved = sharedState.machines.map(row => Object.assign({}, row));
            moved[1].state = moved[1].state === "running" ? "paused" : "running";
            sharedState.applyMachinePayload(JSON.stringify(
                { machines_available: true, machines: moved }));
            check(sharedSurfaces.confirmation === null,
                  "a confirmation survived its target changing state");

            // The target disappears: withdrawn.
            sharedSurfaces.selectMachine("fixture-001", sharedState.machinesGeneration);
            arm("machine", "force-stop", "fixture-001", sharedState.machinesGeneration);
            sharedState.applyMachinePayload(JSON.stringify({
                machines_available: true,
                machines: moved.filter(row => row.name !== "fixture-001")
            }));
            check(sharedSurfaces.confirmation === null,
                  "a confirmation survived its target disappearing");
"""

LAUNCHER = """
            // SUPER+SPACE / IPC: no origin. It must appear on the focused
            // output -- a named output, not an empty-string match.
            sharedSurfaces.openLauncher("");
            check(sharedSurfaces.launcherOpen, "the launcher did not open");
            check(launcher.visible, "the launcher is not visible on its output");
            check(!launcherExternal.visible,
                  "the launcher appeared on more than one output");

            // Focus moves to the external output: the next request follows.
            sharedSurfaces.closeLauncher();
            sharedState.applyWorkspacePayload(JSON.stringify(
                { active: 3, output: "HDMI-A-1", occupied: [3], urgent: [] }));
            sharedSurfaces.openLauncher("");
            check(launcherExternal.visible && !launcher.visible,
                  "an IPC launcher did not follow the focused output");

            // That output is unplugged: the launcher is dismissed, not orphaned.
            sharedSurfaces.liveOutputs = ["eDP-1"];
            check(!sharedSurfaces.launcherOpen,
                  "a launcher survived the removal of its output");

            // Unknown focused output: deterministic first live output.
            sharedState.applyWorkspacePayload(JSON.stringify(
                { active: 2, output: "", occupied: [2], urgent: [] }));
            sharedSurfaces.openLauncher("");
            check(launcher.visible, "an unknown focus did not fall back to a live output");
            sharedSurfaces.liveOutputs = ["eDP-1", "HDMI-A-1"];
            sharedSurfaces.closeLauncher();

            // The pointer names its own output.
            sharedSurfaces.openLauncher("HDMI-A-1");
            check(launcherExternal.visible && !launcher.visible,
                  "a pointer-summoned launcher ignored its output");
            sharedSurfaces.closeLauncher();

            sharedSurfaces.openLauncher("");
            check(launcher.results.length > 0, "the launcher has no results");

            // An empty query favours navigation, not the whole inventory.
            let machineRows = 0;
            for (const row of launcher.results)
                if (row.kind === "machine") machineRows += 1;
            check(machineRows === 0,
                  "an empty query listed machines before destinations");

            // A destination never travels through the action bridge.
            const before = sharedActions.invoked.length;
            launcher.query = "diagnostics";
            launcher.activate(0);
            check(sharedActions.invoked.length === before,
                  "a destination reached the action bridge");
            check(sharedSurfaces.workspaceView === "diagnostics",
                  "the destination did not open");

            // An alias resolves to the destination it means.
            sharedSurfaces.openLauncher("");
            launcher.query = "workstation controls";
            check(launcher.results.length >= 2,
                  "an alias produced no destination");
            launcher.activate(0);
            check(sharedSurfaces.workspaceView === "controls",
                  "the alias did not resolve to the Control Center");

            // A machine result selects an identifier.
            sharedSurfaces.openLauncher("");
            launcher.query = "fixture-002";
            let position = -1;
            for (let index = 0; index < launcher.selectable.length; index++) {
                if (launcher.results[launcher.selectable[index]].kind
                    === "machine") {
                    position = index;
                    break;
                }
            }
            check(position >= 0, "a machine query produced no machine result");
            launcher.activate(position);
            check(sharedSurfaces.selectedMachineId === "fixture-002",
                  "the machine result did not select its identifier");

            // A reviewed command reaches the bridge, and only by identifier.
            sharedSurfaces.openLauncher("");
            launcher.query = "cycle theme";
            for (let index = 0; index < launcher.selectable.length; index++) {
                if (launcher.results[launcher.selectable[index]].kind
                    === "command") {
                    launcher.activate(index);
                    break;
                }
            }
            check(sharedActions.invoked.indexOf("theme-cycle") >= 0,
                  "a reviewed command did not reach the bridge");
"""

TRANSIENTS = """
            // A keyboard/IPC request carries no output: it lands on the
            // observed focused output, and only there.
            sharedSurfaces.openSystemPanel("");
            check(systemPanel.visible, "the system panel did not open");
            check(!systemPanelExternal.visible,
                  "the system panel opened on a second output too");
            check(!sharedSurfaces.launcherOpen,
                  "the panel left the launcher open");

            // Plain OSD: the host's current value, on the focused output.
            sharedSurfaces.showOsd("audio", "");
            check(osd.shown, "the OSD did not appear");
            check(!osdExternal.shown, "the OSD appeared on a second output too");
            check(osd.value === "110%",
                  "the OSD did not read the structured audio level");
            check(!sharedSurfaces.showOsd("nonsense", ""),
                  "the OSD accepted an unknown kind");

            // Action OSD: pending until that action's own result.
            sharedSurfaces.showActionOsd("audio", "audio-volume-up", true, "");
            check(osd.value === "Applying…",
                  "an in-flight action showed the previous value as current");
            sharedSurfaces.settleActionOsd("theme-cycle", false, "unrelated");
            check(osd.value === "Applying…",
                  "an unrelated action's failure settled this OSD");
            sharedSurfaces.settleActionOsd("audio-volume-up", false, "bridge refused");
            check(osd.value === "Failed",
                  "a failed action still read as a value");
            sharedSurfaces.showActionOsd("audio", "audio-volume-up", true, "");
            sharedSurfaces.settleActionOsd("audio-volume-up", true, "");
            check(osd.value === "110%",
                  "a settled action did not show the read-back value");

            // A refused request (full queue) is a failure now, not a card
            // waiting for a result that will never come.
            sharedSurfaces.showActionOsd("theme", "theme-cycle", false, "");
            check(osd.value === "Failed",
                  "a refused host action was shown as pending or applied");

            // Showing the OSD never moves the panel.
            sharedSurfaces.showOsd("keyboard", "HDMI-A-1");
            check(osdExternal.shown && !osd.shown,
                  "an explicit OSD origin was ignored");
            check(systemPanel.visible && !systemPanelExternal.visible,
                  "showing the OSD moved the system panel");

            // Workspace chips leave through the reviewed operation only.
            check(sharedActions.invokeWorkspace(3),
                  "a valid workspace slot was refused");
            check(!sharedActions.invokeWorkspace(0),
                  "workspace slot 0 was accepted");
            check(!sharedActions.invokeWorkspace(12),
                  "workspace slot 12 was accepted");
"""

TRUTH = """
            // An unreadable inventory is never an empty one.
            sharedState.applyMachinePayload("not json");
            check(!sharedState.machinesAvailable,
                  "a malformed inventory looked available");
            check(sharedState.machines.length === 0,
                  "a malformed inventory kept stale rows");
            check(sharedState.machinesSourceState === "unavailable",
                  "a malformed inventory did not report unavailable");

            sharedState.applyMachinePayload(JSON.stringify(
                { machines_available: true, machines: [] }));
            check(sharedState.machinesAvailable,
                  "an empty inventory looked failed");

            sharedState.applyMachinePayload(JSON.stringify({
                machines_available: true,
                machines: [{ name: "x", state: "running", gpu: "",
                             provenance: "root" }]
            }));
            check(!sharedState.machinesAvailable,
                  "an invalid provenance was accepted");

            // Raw libvirt domains are a Diagnostics observation only. A
            // domain that matches a product Machine is not listed again, and
            // nothing observed here ever joins the Machines inventory.
            sharedState.applyMachinePayload(JSON.stringify({
                machines_available: true,
                machines: [{ name: "development-01", state: "not-created",
                             gpu: "Runtime not created",
                             provenance: "unclassified" }]
            }));
            sharedState.applyOutsideDomainsPayload(JSON.stringify({
                machines_available: true,
                machines: [
                    { name: "development-01", state: "running",
                      managed: true },
                    { name: "arch-dev-vfio", state: "running",
                      managed: true },
                    { name: "external-01", state: "shut off",
                      managed: false }
                ]
            }));
            check(sharedState.outsideDomainsAvailable,
                  "an observed domain list looked unavailable");
            check(sharedState.outsideDomains.length === 2
                  && sharedState.outsideDomains[0].name === "arch-dev-vfio"
                  && sharedState.outsideDomains[1].name === "external-01",
                  "outside domains did not exclude the product Machine");
            check(sharedState.machines.length === 1
                  && sharedState.machines[0].name === "development-01",
                  "an observed fixture joined the product inventory");
            check(sharedState.outsideDomainKind(
                      sharedState.outsideDomains[0]) === "HyperLab fixture"
                  && sharedState.outsideDomainKind(
                      sharedState.outsideDomains[1]) === "External domain",
                  "outside domain kinds were misclassified");

            sharedState.applyOutsideDomainsPayload("not json");
            check(!sharedState.outsideDomainsAvailable
                  && sharedState.outsideDomains.length === 0,
                  "a malformed domain observation kept stale rows");

            // A boot claim is accepted only from an affirmative, internally
            // consistent observation, and every failure is visibly a failure:
            // never "No claim this boot", never a silent rail.
            sharedSurfaces.openWorkspacePage("diagnostics", "isolation");
            const claimText = window.find(workspaceSurface, "boot-claim-text");
            const badge = window.find(rail, "gpu-badge");
            check(claimText !== null, "the boot claim readout is not rendered");
            check(badge !== null, "the rail GPU badge is not rendered");

            // Nobody holds the GPU, so the badge speaks only about the claim.
            sharedState.applyGpuPayload(JSON.stringify(
                { known: true, owner: "", bound: true }));

            const valid = [
                { payload: { known: true, claimed: true, identity: "dev", level: 2,
                             class: "warn" },
                  claimed: true, label: "· rung 2 until reboot" },
                { payload: { known: true, claimed: false, identity: null, level: null,
                             class: "ok" },
                  claimed: false, label: "No claim this boot" }
            ];
            for (const entry of valid) {
                sharedState.applyTrustPayload(JSON.stringify(entry.payload));
                check(sharedState.trustClaimState === "ok",
                      "a valid claim observation was rejected");
                check(sharedState.trustClaim.claimed === entry.claimed,
                      "a valid claim was misread");
                check(claimText.text === entry.label,
                      "valid claim rendered as: " + claimText.text);
            }
            check(!badge.visible, "a known idle GPU with no claim was not quiet");

            const broken = [
                "{}",
                "[]",
                "garbage",
                "",
                JSON.stringify({ claimed: false, identity: null, level: null }),
                JSON.stringify({ known: true, claimed: false, class: "error" }),
                JSON.stringify({ known: false, claimed: false }),
                JSON.stringify({ known: true, claimed: "no" }),
                JSON.stringify({ known: true, claimed: true, identity: "dev", level: 3 }),
                JSON.stringify({ known: true, claimed: true, identity: "services", level: 2 }),
                JSON.stringify({ known: true, claimed: true, identity: "root", level: 9 }),
                JSON.stringify({ known: true, claimed: false, identity: "clean", level: 3 })
            ];
            for (const raw of broken) {
                // Recover to a valid unclaimed reading, then break it.
                sharedState.applyTrustPayload(JSON.stringify(
                    { known: true, claimed: false, identity: null, level: null }));
                sharedState.applyTrustPayload(raw);
                check(sharedState.trustClaimState === "unavailable",
                      "a broken claim reading looked healthy: " + raw);
                check(claimText.text.indexOf("No claim this boot") < 0,
                      "a broken claim reading said No claim: " + raw);
                check(badge.visible && badge.stateText === "Claim unknown",
                      "a broken claim reading was silent on the rail: " + raw);
            }

            // A restriction that was seen is kept, qualified, when the next
            // read fails -- it never silently disappears.
            sharedState.applyTrustPayload(JSON.stringify(
                { known: true, claimed: true, identity: "dirty", level: 1 }));
            sharedState.applyTrustPayload("garbage");
            check(sharedState.trustClaim.claimed
                  && sharedState.trustClaim.identity === "dirty",
                  "a failed read dropped a previously observed restriction");
            check(claimText.text.indexOf("last seen") >= 0,
                  "a retained claim was not qualified: " + claimText.text);
            check(badge.stateText.indexOf("last seen") >= 0,
                  "the rail did not qualify a retained claim");

            // Recovery restores a normal reading.
            sharedState.applyTrustPayload(JSON.stringify(
                { known: true, claimed: true, identity: "dirty", level: 1 }));
            check(claimText.text === "· rung 1 until reboot",
                  "a recovered claim did not read normally");

            // Unknown ownership and no current owner are different facts.
            sharedState.applyGpuPayload(JSON.stringify(
                { known: true, owner: "", bound: false }));
            check(sharedState.gpuOwnership.known && !sharedState.gpuHeld,
                  "no current owner was confused with unknown");
            sharedState.applyGpuPayload(JSON.stringify({ known: false }));
            check(!sharedState.gpuOwnership.known,
                  "unknown ownership was confused with free");
            sharedState.applyGpuPayload("");
            check(sharedState.gpuSourceState === "unavailable",
                  "an unreadable GPU source looked healthy");

            // A default is never published as an observation.
            check(sharedState.keyboardName() === "Unknown",
                  "an unobserved keyboard layout was invented");
            check(sharedState.themeLabel() === "Unknown",
                  "an unobserved theme was invented");
            check(sharedState.wallpaperLabel() === "Unknown",
                  "an unobserved wallpaper source was invented");
            sharedState.applyKeyboardLayout("us");
            check(sharedState.keyboardName() === "English (US)",
                  "an observed keyboard layout was not adopted");
            sharedState.applyKeyboardLayout("klingon");
            check(sharedState.keyboardName() === "Unknown",
                  "an invalid keyboard layout kept or adopted a value");

            // Keyboard lighting: absent is the reviewed default, off; an
            // unrecognised value is unknown, never the previous mode.
            sharedState.applyRgbMode("");
            check(sharedState.rgbModeLabel() === "Off",
                  "an absent RGB mode was not the reviewed default");
            sharedState.applyRgbMode("focus-trust");
            check(sharedState.rgbModeLabel() === "Focused window",
                  "an observed RGB mode was not adopted");
            sharedState.applyRgbMode("rainbow");
            check(sharedState.rgbModeLabel() === "Unknown",
                  "an invalid RGB mode kept or adopted a value");

            // Focused-surface provenance is never derived in the shell.
            check(sharedState.focusedProvenance.available === false,
                  "the shell claimed a focused provenance resolution");

            // Battery absence and battery unreadability stay distinct.
            sharedState.applyTelemetryPayload(JSON.stringify({
                battery: { text: "—", class: "unavailable", present: false }
            }));
            check(sharedState.batteryPresence.known
                  && !sharedState.batteryPresence.present,
                  "an absent battery was not reported as absent");
            sharedState.applyTelemetryPayload(JSON.stringify({
                battery: { text: "—", class: "unavailable" }
            }));
            check(!sharedState.batteryPresence.known,
                  "an unreadable battery was reported as absent");
"""

GEOMETRY = """
            sharedSurfaces.openWorkspace("machines");
            sharedSurfaces.selectMachine("fixture-001", 1);

            function within(item, name) {
                if (!item || !item.visible) return;
                const point = item.mapToItem(window.contentItem, 0, 0);
                check(point.x >= -1 && point.y >= -1,
                      name + " starts off screen");
                check(point.x + item.width <= window.width + 1,
                      name + " runs past the right edge");
                check(point.y + item.height <= window.height + 1,
                      name + " runs past the bottom edge");
            }

            within(rail, "the rail");
            within(workspaceSurface, "the workspace");

            sharedSurfaces.openWorkspace("controls");
            within(workspaceSurface, "the Control Center");
            sharedSurfaces.openWorkspace("diagnostics");
            within(workspaceSurface, "Diagnostics");

            check(sharedSurfaces.subpage === "overview",
                  "a destination did not open on its first subpage");

            const chip = window.find(workspaceSurface, "chip-overview");
            const otherChip = window.find(workspaceSurface, "chip-inventory");
            check(chip === null || chip.selected === true,
                  "the open section is not marked in the compact navigation");
            check(otherChip === null || otherChip.selected === false,
                  "a closed section is marked in the compact navigation");

            sharedSurfaces.openLauncher("");
            check(launcher.visible, "the launcher did not become visible");
            within(launcher, "the launcher");
            sharedSurfaces.closeLauncher();

            sharedSurfaces.openSystemPanel("");
            check(systemPanel.visible,
                  "the system panel did not become visible");
            within(systemPanel, "the system panel");
"""


CAPABILITIES = """
            // Replies are bound to the request that is outstanding: its serial
            // and the machine it named. Everything else is discarded or, for
            // the current request, recorded as unavailable -- never adopted.
            const good = JSON.stringify({
                phase: "capabilities",
                machine: { name: "fixture-001", state: "running",
                           managed: true, vfio: true },
                verbs: { shutdown: { available: true, reason: "" },
                         start: { available: false, reason: "already running" } }
            });

            sharedState.beginCapabilityRequest(10, "fixture-001",
                                               sharedState.machinesGeneration);
            // A -> B: B asked after A.
            sharedState.beginCapabilityRequest(11, "fixture-002",
                                               sharedState.machinesGeneration);
            // A's late reply arrives while B is outstanding.
            check(!sharedState.applyCapabilityAnswer(10, "fixture-001", good, 0, ""),
                  "a superseded reply was accepted");
            check(sharedState.machineCapabilities.machine === "fixture-002"
                  && sharedState.machineCapabilities.state === "loading",
                  "a superseded reply replaced the current request's state");

            // A reply for the current serial that names a different machine.
            check(!sharedState.applyCapabilityAnswer(11, "fixture-001", good, 0, ""),
                  "a reply naming a different machine was accepted");
            // The current request answered with the wrong machine inside.
            sharedState.applyCapabilityAnswer(11, "fixture-002", good, 0, "");
            check(sharedState.machineCapabilities.state === "unavailable",
                  "an answer about another machine was adopted");
            check(!sharedState.capabilityFor("fixture-002", "shutdown").available,
                  "a mismatched answer made an operation available");

            // B -> A: A asked again and answered correctly.
            sharedState.beginCapabilityRequest(12, "fixture-001",
                                               sharedState.machinesGeneration);
            check(sharedState.applyCapabilityAnswer(12, "fixture-001", good, 0, ""),
                  "a correct answer to the current request was refused");
            check(sharedState.capabilityFor("fixture-001", "shutdown").available,
                  "a validated capability did not reach presentation");
            check(!sharedState.capabilityFor("fixture-001", "force-stop").available,
                  "an unreported operation was treated as available");

            // Malformed answers to the current request.
            const malformed = [
                JSON.stringify({ phase: "capabilities",
                    machine: { name: "fixture-001" }, verbs: null }),
                JSON.stringify({ phase: "capabilities",
                    machine: { name: "fixture-001" }, verbs: [] }),
                JSON.stringify({ phase: "capabilities",
                    machine: { name: "fixture-001" },
                    verbs: { shutdown: { available: "yes", reason: "" } } }),
                JSON.stringify({ phase: "capabilities",
                    machine: { name: "fixture-001" },
                    verbs: { "rm -rf": { available: true, reason: "" } } }),
                JSON.stringify({ phase: "operation",
                    machine: { name: "fixture-001" }, verbs: {} }),
                "not json"
            ];
            let serial = 20;
            for (const raw of malformed) {
                serial += 1;
                sharedState.beginCapabilityRequest(serial, "fixture-001",
                                                   sharedState.machinesGeneration);
                sharedState.applyCapabilityAnswer(serial, "fixture-001", raw, 0, "");
                check(sharedState.machineCapabilities.state === "unavailable",
                      "a malformed capability answer was adopted: " + raw);
                check(!sharedState.capabilityFor("fixture-001", "shutdown").available,
                      "a malformed answer enabled an operation: " + raw);
            }

            // A bridge failure is unavailable with its reason, not a guess.
            serial += 1;
            sharedState.beginCapabilityRequest(serial, "fixture-001",
                                               sharedState.machinesGeneration);
            sharedState.applyCapabilityAnswer(serial, "fixture-001", "", 2,
                                              "bridge unavailable");
            check(sharedState.capabilityFor("fixture-001", "shutdown").reason
                  === "bridge unavailable",
                  "a bridge failure lost its reason");

            // An answer bound to an older inventory generation is not used.
            serial += 1;
            sharedState.beginCapabilityRequest(serial, "fixture-001",
                                               sharedState.machinesGeneration);
            sharedState.applyCapabilityAnswer(serial, "fixture-001", good, 0, "");
            const moved = sharedState.machines.map(row => Object.assign({}, row));
            moved[2].state = moved[2].state === "running" ? "paused" : "running";
            sharedState.applyMachinePayload(JSON.stringify(
                { machines_available: true, machines: moved }));
            check(!sharedState.capabilityFor("fixture-001", "shutdown").available,
                  "an answer from an older inventory generation was used");

            // The target disappears.
            sharedState.applyMachinePayload(JSON.stringify({
                machines_available: true,
                machines: moved.filter(row => row.name !== "fixture-001")
            }));
            check(sharedState.capabilityFor("fixture-001", "shutdown").reason
                  === "This machine is no longer in the inventory",
                  "a vanished machine kept its operations");

            // Cleared: nothing answers for anything.
            sharedState.clearCapabilities();
            check(!sharedState.applyCapabilityAnswer(serial, "fixture-001", good, 0, ""),
                  "a reply after clearing was accepted");
"""

FRESHNESS = """
            // Healthy sources, then time passes with no observation at all.
            check(sharedState.telemetryCurrent, "fixture telemetry not current");
            check(sharedState.audioLevel.known, "fixture audio not known");
            sharedSurfaces.openWorkspace("machines");
            sharedSurfaces.selectMachine("fixture-000", sharedState.machinesGeneration);
            check(sharedState.capabilityFor("fixture-000", "shutdown").available,
                  "fixture capability not available");

            sharedState.observationNow = Date.now() + 200000;

            // Stale telemetry is withheld everywhere at once.
            check(!sharedState.telemetryCurrent, "stale telemetry still current");
            check(!sharedState.audioLevel.known,
                  "a stale audio level was presented as known");
            check(!sharedState.batteryPresence.known,
                  "a stale battery reading was presented as known");
            check(sharedState.audioPayload.class === "unavailable",
                  "a stale audio readout kept its old value");

            // A stale GPU owner is not a current owner.
            const badge = window.find(rail, "gpu-badge");
            check(badge !== null && badge.visible
                  && badge.stateText === "Stale reading",
                  "a stale GPU owner was presented as current");
            check(!sharedState.gpuOwnership.known,
                  "a stale ownership reading still reads as known");

            // Operations that depend on a stale inventory are disabled.
            check(!sharedState.capabilityFor("fixture-000", "shutdown").available,
                  "an operation stayed enabled on a stale inventory");

            // A source that never answered is unavailable, not loading.
            check(sharedState.sourceState("loading", 0) === "unavailable",
                  "a source that never answered still reads as loading");

            // Fresh observations restore normal operation.
            sharedState.applyTelemetryPayload(JSON.stringify({
                audio: { text: "40%", class: "", percent: 40, muted: false }
            }));
            sharedState.observationNow = Date.now();
            check(sharedState.audioLevel.known && sharedState.audioLevel.percent === 40,
                  "a fresh telemetry reading was not restored");

            // Malformed telemetry after success is unavailable, not old data.
            sharedState.applyTelemetryPayload("not json");
            check(!sharedState.audioLevel.known,
                  "malformed telemetry left the previous level presented");
"""

MODAL = """
            sharedSurfaces.openWorkspace("machines");
            sharedSurfaces.selectMachine("fixture-001", sharedState.machinesGeneration);
            sharedSurfaces.requestConfirmation({
                kind: "machine", actionId: "force-stop",
                targetId: "fixture-001", targetName: "fixture-001",
                title: "Force stop this machine?", consequence: "c",
                confirmLabel: "Force stop", requiresName: true,
                generation: sharedState.machinesGeneration
            });

            const background = window.find(workspaceSurface, "workspace-background");
            const field = window.find(workspaceSurface, "confirmation-name");
            const cancel = window.find(workspaceSurface, "confirmation-cancel");
            const confirm = window.find(workspaceSurface, "confirmation-confirm");

            check(background !== null && !background.enabled,
                  "the workspace behind the dialog is still enabled");
            check(cancel !== null && cancel.activeFocus,
                  "Cancel is not the default focus");
            check(confirm !== null && !confirm.enabled,
                  "confirm is enabled before the exact name is typed");

            function within(item, root) {
                for (let node = item; node; node = node.parent)
                    if (node === root)
                        return true;
                return false;
            }

            function inDialog(item) {
                for (let node = item; node; node = node.parent)
                    if (node.objectName === "confirmation-footer"
                        || node === field)
                        return true;
                return false;
            }

            // Tab order never reaches the workspace behind the dialog: every
            // item on the focus chain from Cancel, in both directions, is in
            // the dialog. (In production the rail and transients are other
            // windows with their own chains; the harness hosts them in one
            // window, so items outside the workspace are not background.)
            let dialogStops = 0;
            for (const forward of [true, false]) {
                let item = cancel;
                for (let step = 0; step < 12; step++) {
                    item = item.nextItemInFocusChain(forward);
                    check(item !== null, "the focus chain broke");
                    if (item === null)
                        break;
                    check(inDialog(item) || !within(item, workspaceSurface),
                          "Tab reached a workspace control behind the dialog");
                    if (inDialog(item))
                        dialogStops += 1;
                }
            }
            check(dialogStops > 0, "the dialog's own controls are not on the focus chain");
            check(cancel.KeyNavigation.tab === field,
                  "Tab from Cancel does not reach the name field while confirm is disabled");

            // A partial or wrong name never enables the destructive button.
            field.text = "fixture-00";
            check(!confirm.enabled, "a partial name enabled confirm");
            field.text = "fixture-001 ";
            check(!confirm.enabled, "a padded name enabled confirm");
            field.text = "fixture-001";
            check(confirm.enabled, "the exact name did not enable confirm");
            check(cancel.KeyNavigation.tab === confirm,
                  "Tab from Cancel does not reach confirm once it is enabled");

            // A replacement record starts clean: empty name, Cancel focused.
            sharedSurfaces.requestConfirmation({
                kind: "machine", actionId: "force-stop",
                targetId: "fixture-002", targetName: "fixture-002",
                title: "Force stop this machine?", consequence: "c",
                confirmLabel: "Force stop", requiresName: true,
                generation: sharedState.machinesGeneration
            });
            check(field.text === "", "a replaced record kept the typed name");
            check(cancel.activeFocus, "a replaced record did not reset focus");

            // Exact name, submit once: exactly one operation on the captured
            // target, and a repeated activation does nothing.
            field.text = "fixture-002";
            confirm.activate();
            confirm.activate();
            check(sharedMachineActions.operations.length === 1
                  && sharedMachineActions.operations[0] === "force-stop:fixture-002",
                  "confirm did not run exactly one operation on the captured target: "
                  + sharedMachineActions.operations.join(","));
            check(sharedSurfaces.confirmation === null,
                  "the dialog stayed open after submission");
            check(background.enabled,
                  "the workspace stayed disabled after the dialog closed");

            // A target that vanished between arming and submission is
            // refused at submission, never redirected.
            sharedSurfaces.requestConfirmation({
                kind: "machine", actionId: "force-stop",
                targetId: "ghost", targetName: "ghost",
                title: "t", consequence: "c", confirmLabel: "Force stop",
                requiresName: true, generation: -1
            });
            field.text = "ghost";
            confirm.activate();
            check(sharedMachineActions.operations.length === 1,
                  "a vanished target was executed");
            check(sharedState.latestOperationFor("ghost") !== null
                  && sharedState.latestOperationFor("ghost").phase === "refused",
                  "a vanished target was not reported as refused");

            // Escape cancels.
            sharedSurfaces.requestConfirmation({
                kind: "machine", actionId: "force-stop",
                targetId: "fixture-001", targetName: "fixture-001",
                title: "t", consequence: "c", confirmLabel: "Force stop",
                requiresName: true, generation: sharedState.machinesGeneration
            });
            sharedSurfaces.cancelConfirmation();
            check(sharedSurfaces.confirmation === null && background.enabled,
                  "cancelling did not restore the workspace");
"""

def backend_trust_payloads() -> dict[str, str]:
    """Trust payloads produced by the real backend path.

    Context.read_text -> TrustProvider -> document.build -> waybar_field,
    exactly as `hyperlabctl watch --field trust` publishes them. Read
    failures are injected at Path.read_text for the trust file only; nothing
    outside the fixture's temporary directory is read.
    """
    import errno
    import sys
    from unittest import mock

    sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))
    sys.path.insert(0, str(ROOT / "tools/hyperlabctl/tests"))

    import world
    from hyperlabctl import document
    from hyperlabctl.render import waybar_field

    def payload(trust, error=None):
        ctx = world.build(trust=trust)
        target = str(ctx.config.gpu_handoff_state)
        real = Path.read_text

        def read_text(self, *args, **kwargs):
            if error is not None and str(self) == target:
                raise error
            return real(self, *args, **kwargs)

        with mock.patch.object(Path, "read_text", read_text):
            built = document.build(ctx, only={"trust"})
        return json.dumps(waybar_field(built, "trust"))

    return {
        "dev": payload(2),
        "absent": payload(None),
        "permission": payload(2, PermissionError(errno.EACCES, "Permission denied")),
        "io": payload(2, OSError(errno.EIO, "Input/output error")),
        "malformed": payload("garbage"),
    }


def resolver_answers() -> dict[str, dict]:
    """Provenance answers produced by the real reviewed resolver.

    HOST for an unregistered host process, DEV for a verified Looking Glass
    registration, and fail-closed for an unregistered Looking Glass surface.
    The reviewed executable is bound to a fixture binary for the DEV case
    only; nothing outside the fixture's temporary directory is read.
    """
    import hashlib
    import importlib.util

    import yaml

    spec = importlib.util.spec_from_file_location(
        "surface_provenance_runtime_fixture",
        ROOT / "tools/surface_provenance.py",
    )
    assert spec is not None and spec.loader is not None
    resolver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(resolver)

    with tempfile.TemporaryDirectory(prefix="hyperlab-provenance-") as name:
        temp = Path(name)
        repo = temp / "repo"
        (repo / "vm-specs").mkdir(parents=True)
        spec_path = repo / "vm-specs/arch-dev-vfio.yml"
        spec_path.write_text(yaml.safe_dump({
            "name": "arch-dev-vfio",
            "device_profile": "vfio",
            "network_profile": "dev",
            "looking_glass": True,
        }), encoding="utf-8")

        transport = temp / "looking-glass-client"
        transport.write_text("#!/bin/sh\n", encoding="utf-8")
        resolver.EXPECTED_EXECUTABLES["looking-glass"] = str(transport.resolve())

        proc = temp / "proc" / "901"
        proc.mkdir(parents=True)
        (proc / "stat").write_text(
            "901 (looking-glass) S " + "0 " * 18 + "4242 0 0\n",
            encoding="utf-8",
        )
        (proc / "exe").symlink_to(transport)

        registry = {"version": 1, "entries": [{
            "pid": 901,
            "process_start_ticks": "4242",
            "executable": str(transport.resolve()),
            "surface_kind": "looking-glass",
            "domain": "arch-dev-vfio",
            "spec_sha256": hashlib.sha256(spec_path.read_bytes()).hexdigest(),
            "registered_by": "hyperlabctl",
        }]}

        def answer(pid: int, app_id: str) -> dict:
            return resolver.resolve(
                repo=repo,
                surface={"pid": pid, "app_id": app_id, "window_id": "0x1"},
                registry=registry,
                proc_root=temp / "proc",
            )

        return {
            "host": answer(900, "foot"),
            "dev": answer(901, "looking-glass-client"),
            "unresolved": answer(902, "looking-glass-client"),
        }


PROVENANCE = """
            const real = @@PROVENANCE@@;
            const badge = window.find(rail, "provenance-badge");

            function answer(provenance, request) {
                sharedState.applyProvenancePayload(JSON.stringify({
                    "schema": 1,
                    "status": "ok",
                    "request": request === undefined
                        ? sharedState.provenanceRequest : request,
                    "provenance": provenance
                }));
            }

            function focus(pid, app, windowId) {
                sharedState.applyFocusPayload(JSON.stringify({
                    "pid": pid, "app_id": app, "window_id": windowId,
                    "title": "CLEAN trusted title"
                }));
            }

            function forged(change) {
                const value = JSON.parse(JSON.stringify(real.dev));
                change(value);
                return value;
            }

            check(badge !== null, "the rail provenance badge is not rendered");

            // Host-native: HOST from the resolver, context unchanged.
            focus(900, "foot", "0x10");
            check(sharedState.focusedProvenance.state === "resolving"
                  && sharedState.focusedProvenance.identity === "",
                  "a newly focused surface did not start without an identity");
            const sent = JSON.parse(sharedState.provenanceRequestLine);
            check(sent.surface.pid === 900
                  && sent.request === sharedState.provenanceRequest,
                  "the focused PID did not reach the resolver request");
            check(sharedState.provenanceRequestLine.indexOf("title") < 0
                  && sharedState.provenanceRequestLine.indexOf("CLEAN") < 0,
                  "the window title reached the resolver request");
            const hostRequest = sharedState.provenanceRequest;
            answer(real.host);
            check(sharedState.focusedProvenance.available
                  && sharedState.focusedProvenance.identity === "host"
                  && sharedState.focusedProvenance.source === "host-native",
                  "a host-native answer did not present HOST");
            check(badge.resolved && badge.identity === "host",
                  "the rail badge did not present HOST");
            check(sharedState.focusedSurface === "foot",
                  "compositor context changed with provenance");

            // Managed DEV: the previous identity is dropped at once, and a
            // late answer to an older request is ignored.
            focus(901, "looking-glass-client", "0x11");
            check(!sharedState.focusedProvenance.available
                  && sharedState.focusedProvenance.identity === "",
                  "the previous identity stayed attached to a new surface");
            answer(real.host, hostRequest);
            check(sharedState.focusedProvenance.state === "resolving",
                  "an answer to an older request was applied");
            answer(real.dev);
            check(sharedState.focusedProvenance.available
                  && sharedState.focusedProvenance.identity === "dev"
                  && sharedState.focusedProvenance.domain === "arch-dev-vfio"
                  && sharedState.focusedProvenance.source
                     === "host-owned-vm-spec",
                  "a verified managed surface did not present DEV");
            check(sharedState.focusedSurface === "looking-glass-client",
                  "provenance replaced the compositor context");
            check(badge.identity === "dev", "the rail badge did not present DEV");

            for (const identity of ["clean", "services"]) {
                focus(901, "looking-glass-client", "0x11");
                answer(forged(v => {
                    v.trust = identity;
                    v.presentation_identity = identity;
                    v.network_profile = identity;
                }));
                check(sharedState.focusedProvenance.identity === identity,
                      "a reviewed identity was lost in presentation");
            }
            check(sharedState.gpuLadder.services === undefined,
                  "SERVICES entered the GPU ladder");

            // An identical tuple still needs revalidation (PID reuse).
            focus(901, "looking-glass-client", "0x11");
            check(sharedState.focusedProvenance.identity === "",
                  "an identical tuple retained stale provenance");

            // Back to a host window: DEV never follows it.
            focus(900, "foot", "0x10");
            check(sharedState.focusedProvenance.identity === "",
                  "DEV stayed attached to a host window");
            answer(real.dev);
            check(sharedState.focusedProvenance.state === "unavailable"
                  && sharedState.focusedProvenance.reasonCode
                     === "resolver-invalid",
                  "an answer about another process was accepted");

            // Unregistered managed transport: fail closed, visibly.
            focus(902, "looking-glass-client", "0x12");
            answer(real.unresolved);
            check(sharedState.focusedProvenance.state === "unresolved"
                  && !sharedState.focusedProvenance.available
                  && sharedState.focusedProvenance.identity === ""
                  && sharedState.focusedProvenance.reasonCode
                     === "managed-surface-not-registered",
                  "an unregistered managed surface did not fail closed");
            check(badge.unresolved && !badge.resolved,
                  "the rail badge hid a fail-closed surface");

            // Every inconsistent shape is rejected, never presented.
            const invalid = [
                forged(v => { v.network_profile = "clean"; }),
                forged(v => { v.trust = "host"; }),
                forged(v => { v.presentation_identity = "clean"; }),
                forged(v => { v.trust_source = "guest"; }),
                forged(v => { v.guest_metadata_authoritative = true; }),
                forged(v => { v.reason = "guest-says-so"; }),
                forged(v => { v.domain = ""; }),
                forged(v => { v.schema = 2; }),
                forged(v => { v.surface_class = "guest"; }),
                forged(v => { v.resolved = "yes"; }),
                forged(v => { v.resolved = false; }),
                forged(v => { v.reason = "unregistered-host-process"; }),
                forged(v => { v.spec_sha256 = "bad"; }),
                forged(v => { v.surface_kind = "guest"; }),
                forged(v => { v.wallpaper_allowed = false; })
            ];
            for (let index = 0; index < invalid.length; index++) {
                focus(901, "looking-glass-client", "0x2" + index);
                answer(invalid[index]);
                check(sharedState.focusedProvenance.state === "unavailable"
                      && sharedState.focusedProvenance.identity === "",
                      "an inconsistent provenance answer was presented");
            }

            focus(901, "looking-glass-client", "0x11");
            sharedState.applyProvenancePayload(JSON.stringify({
                "schema": 1, "status": "unavailable",
                "request": sharedState.provenanceRequest,
                "reason": "surface registry mode must be exactly 0600"
            }));
            check(sharedState.focusedProvenance.state === "unavailable"
                  && sharedState.focusedProvenance.reasonCode
                     === "resolver-refused",
                  "a resolver refusal was not reported as unavailable");

            focus(901, "looking-glass-client", "0x11");
            sharedState.applyProvenancePayload(JSON.stringify({
                "schema": 2, "status": "ok",
                "request": sharedState.provenanceRequest,
                "provenance": real.dev
            }));
            check(sharedState.focusedProvenance.reasonCode === "resolver-schema",
                  "an unknown answer schema was accepted");

            // Lifecycle: a silent or stopped resolver is unavailable.
            focus(901, "looking-glass-client", "0x11");
            check(sharedState.provenanceTimedOut() === true
                  && sharedState.focusedProvenance.reasonCode
                     === "resolver-timeout",
                  "an unanswered request did not time out");
            check(sharedState.provenanceTimedOut() === false,
                  "a timeout fired without an outstanding request");
            answer(real.dev);
            check(sharedState.focusedProvenance.reasonCode === "resolver-timeout",
                  "a late answer restored trust after timeout");
            sharedState.provenanceStopped();
            answer(real.dev);
            check(sharedState.focusedProvenance.state === "unavailable"
                  && sharedState.focusedProvenance.reasonCode
                     === "resolver-stopped",
                  "a stopped resolver kept its last answer");
            focus(901, "looking-glass-client", "0x11");
            check(sharedState.focusedProvenance.state === "resolving",
                  "an answer from a stopped resolver was reused");

            // Invalid snapshots must never be recast as a host desktop.
            for (const pid of ["901", true, -1, 0]) {
                focus(pid, "foot", "0x13");
                check(sharedState.focusedProvenance.state === "unavailable"
                      && !sharedState.provenancePending,
                      "a malformed PID was forwarded to the resolver");
            }

            focus(901, "looking-glass-client", "0x11");
            sharedState.applyProvenancePayload("not json");
            check(sharedState.focusedProvenance.state === "unavailable",
                  "a malformed answer did not invalidate provenance");
            answer(real.dev);
            check(sharedState.focusedProvenance.state === "unavailable",
                  "a second answer replaced a rejected answer");

            focus(901, "looking-glass-client", "0x11");
            const oldDev = sharedState.provenanceRequest;
            focus(900, "firefox", "0x10");
            answer(real.host);
            answer(real.dev, oldDev);
            check(sharedState.focusedProvenance.identity === "host",
                  "a late DEV answer replaced Firefox HOST");

            // A failed focus source makes provenance unavailable.
            sharedState.applyFocusPayload("not json");
            check(sharedState.focusedProvenance.state === "unavailable"
                  && sharedState.focusedProvenance.reasonCode
                     === "focus-unavailable",
                  "provenance outlived its focus source");

            focus(902, "looking-glass-client", "0x12");
            answer(real.unresolved);
            sharedSurfaces.openWorkspacePage("diagnostics", "session");
            check(sharedSurfaces.subpage === "session",
                  "Diagnostics did not open on Session");
"""

TRUST_PROVIDER_PATH = """
            // Real backend payloads (see backend_trust_payloads): a read
            // failure must never become an affirmative "unclaimed", and must
            // never erase the previously observed restriction.
            const payloads = @@TRUST_PAYLOADS@@;
            sharedSurfaces.openWorkspacePage("diagnostics", "isolation");
            const claimText = window.find(workspaceSurface, "boot-claim-text");
            const badge = window.find(rail, "gpu-badge");
            sharedState.applyGpuPayload(JSON.stringify(
                { known: true, owner: "", bound: true }));

            sharedState.applyTrustPayload(payloads.dev);
            check(sharedState.trustClaimState === "ok"
                  && sharedState.trustClaim.identity === "dev"
                  && sharedState.trustClaim.level === 2,
                  "a valid backend DEV/2 claim was not accepted");

            for (const failure of ["permission", "io", "malformed"]) {
                sharedState.applyTrustPayload(payloads[failure]);
                check(sharedState.trustClaimState === "unavailable",
                      "a backend read failure looked healthy: " + failure);
                check(sharedState.trustClaim.claimed
                      && sharedState.trustClaim.identity === "dev"
                      && sharedState.trustClaim.level === 2,
                      "a backend read failure erased the observed claim: " + failure);
                check(claimText.text.indexOf("No claim this boot") < 0
                      && claimText.text.indexOf("last seen") >= 0,
                      "a backend read failure rendered as: " + claimText.text);
                check(badge.visible && badge.stateText.indexOf("last seen") >= 0,
                      "the rail hid a backend read failure: " + failure);

                // Recovery accepts the next valid observation.
                sharedState.applyTrustPayload(payloads.dev);
                check(sharedState.trustClaimState === "ok"
                      && claimText.text === "· rung 2 until reboot",
                      "recovery after a read failure was not accepted: " + failure);
            }

            // A genuine absence is still reported as unclaimed.
            sharedState.applyTrustPayload(payloads.absent);
            check(sharedState.trustClaimState === "ok"
                  && !sharedState.trustClaim.claimed
                  && claimText.text === "No claim this boot",
                  "a genuine unclaimed observation was hidden");

            // A failure after a genuine unclaimed reading is unknown, and
            // invents neither a claim nor a GPU owner.
            sharedState.applyTrustPayload(payloads.io);
            check(!sharedState.trustClaim.claimed
                  && claimText.text.indexOf("Unknown") === 0,
                  "a read failure after unclaimed was not shown as unknown");
            check(sharedState.gpuOwnership.known
                  && sharedState.gpuOwnership.owner === "",
                  "a trust read failure changed GPU ownership");
"""


LONG_TARGET = "x" * 255

LONG_CONFIRM = """
            sharedSurfaces.openWorkspace("machines");
            sharedSurfaces.requestConfirmation({
                kind: "machine", actionId: "force-stop",
                targetId: "@@LONG@@", targetName: "@@LONG@@",
                title: "Force stop this machine?",
                consequence: "Force stop cuts power to the guest without "
                    + "asking it to shut down. Unsaved guest data is lost, "
                    + "and a VFIO guest may need its devices re-attached.",
                confirmLabel: "Force stop", requiresName: true, generation: -1
            });
            const footer = window.find(workspaceSurface, "confirmation-footer");
            const confirm = window.find(workspaceSurface, "confirmation-confirm");
            check(footer !== null && footer.visible, "the dialog footer is missing");
            const point = footer.mapToItem(window.contentItem, 0, 0);
            check(point.y >= 0 && point.y + footer.height <= window.height,
                  "the dialog buttons fell outside a short window");
            check(point.x + footer.width <= window.width,
                  "the dialog buttons fell past the right edge");
            check(confirm !== null && confirm.width > 0,
                  "the confirm button collapsed");
""".replace("@@LONG@@", LONG_TARGET)


# Presentation scenarios: each one leaves a surface open so the optional
# screenshot output shows the state an operator would actually see.
CONTROL_CENTER = """
            sharedState.applyKeyboardLayout("it");
            sharedState.applyThemeName("trust-model");
            sharedState.applyWallpaperMode("product");
            sharedSurfaces.openWorkspacePage("controls", "session");
            check(sharedSurfaces.subpage === "session",
                  "the Control Center did not open on Session");
"""

CONTROL_CENTER_APPEARANCE = """
            sharedState.applyKeyboardLayout("it");
            sharedState.applyThemeName("trust-model");
            sharedState.applyWallpaperMode("product");
            sharedSurfaces.openWorkspacePage("controls", "appearance");
            check(sharedSurfaces.subpage === "appearance",
                  "the Control Center did not open on appearance");
"""

DIAGNOSTICS_OVERVIEW = """
            sharedSurfaces.openWorkspacePage("diagnostics", "overview");
            check(sharedSurfaces.subpage === "overview",
                  "Diagnostics did not open on Overview");
"""

DIAGNOSTICS_ISOLATION = """
            sharedSurfaces.openWorkspacePage("diagnostics", "isolation");
            check(sharedSurfaces.subpage === "isolation",
                  "Diagnostics did not open on Isolation and GPU");

            const chosen = window.find(workspaceSurface, "section-isolation");
            const other = window.find(workspaceSurface, "section-inventory");
            check(chosen !== null, "the section navigation is not rendered");
            check(chosen !== null && chosen.current === true,
                  "the open section is not marked current in the navigation");
            check(other !== null && other.current === false,
                  "a section that is not open is marked current");
"""

LAUNCHER_OPEN = """
            sharedSurfaces.openLauncher("");
            launcher.query = "f";
            check(launcher.visible, "the launcher is not visible");
"""

PANEL_OPEN = """
            sharedState.applyKeyboardLayout("it");
            sharedState.applyThemeName("trust-model");
            sharedState.applyWallpaperMode("product");
            sharedSurfaces.openSystemPanel("");
            check(systemPanel.visible, "the system panel is not visible");
"""

CONFIRM_OPEN = """
            sharedSurfaces.openWorkspace("machines");
            sharedSurfaces.selectMachine("fixture-001", 1);
            sharedSurfaces.requestConfirmation({
                kind: "machine", actionId: "force-stop",
                targetId: "fixture-001", targetName: "fixture-001",
                title: "Force stop this machine?",
                consequence: "Force stop cuts power to the guest without "
                    + "asking it to shut down. Unsaved guest data is lost, "
                    + "and a VFIO guest may need its devices re-attached.",
                confirmLabel: "Force stop",
                requiresName: true, generation: 1
            });
            check(sharedSurfaces.confirmation !== null,
                  "the confirmation is not armed");
"""


# shell.qml is stubbed in the harness, so the root wiring the harness mirrors
# is pinned here: keyboard/IPC transients resolve through the observed focused
# output, capability replies go through ShellState's correlation, and only the
# result of the action an OSD reports on can settle it.
ROOT_WIRING = (
    "activeOutput: {",
    "const focused = sharedState.focusedOutput;",
    "liveOutputs: Quickshell.screens.map(screen => String(screen.name))",
    "sharedState.beginCapabilityRequest(serial, machine, generation);",
    "sharedState.applyCapabilityAnswer(",
    "onCapabilitiesCleared: sharedState.clearCapabilities()",
    "sharedSurfaces.settleActionOsd(action, ok, detail);",
    'if (action === "session-lock")',
)


def check_root_wiring() -> None:
    root = (QML / "shell.qml").read_text(encoding="utf-8")
    missing = [marker for marker in ROOT_WIRING if marker not in root]

    if missing:
        raise SystemExit(
            "HyperLab Quickshell runtime contract: shell.qml wiring "
            f"mirrored by the harness is missing: {missing}"
        )


def main() -> int:
    check_root_wiring()

    runner = (
        shutil.which("qmlscene", path="/usr/lib/qt6/bin")
        or shutil.which("qmlscene6")
    )

    if not runner:
        # The acceptance runner sets this: there, a missing Qt runtime is a
        # failure, not a pass.
        if os.environ.get("HYPERLAB_REQUIRE_QML_RUNTIME") == "1":
            raise SystemExit(
                "HyperLab Quickshell runtime contract: Qt 6 qmlscene is "
                "required on this runner but not installed"
            )

        print(
            "HyperLab Quickshell runtime contract: SKIPPED "
            "(Qt 6 qmlscene is not installed on this host)"
        )
        return 0

    if OUT:
        Path(OUT).mkdir(parents=True, exist_ok=True)

    directory = stage()

    try:
        populated = machines(6)

        cases = [
            ("idle", 1920, 1080, populated, IDLE),
            ("destinations", 1920, 1080, populated, DESTINATIONS),
            ("selection", 1920, 1080, populated, SELECTION),
            ("confirmation", 1920, 1080, populated, CONFIRMATION),
            ("launcher", 1920, 1080, populated, LAUNCHER),
            ("transients", 1920, 1080, populated, TRANSIENTS),
            ("truth", 1920, 1080, populated, TRUTH),
            ("capabilities", 1920, 1080, populated, CAPABILITIES),
            ("trust-provider-path", 1920, 1080, populated,
             TRUST_PROVIDER_PATH.replace(
                 "@@TRUST_PAYLOADS@@",
                 json.dumps(backend_trust_payloads()),
             )),
            ("freshness", 1920, 1080, populated, FRESHNESS),
            ("provenance", 1920, 1080, populated,
             PROVENANCE.replace(
                 "@@PROVENANCE@@",
                 json.dumps(resolver_answers()),
             )),
            ("modal", 1920, 1080, populated, MODAL),
            ("long-confirmation-short", 800, 480, populated, LONG_CONFIRM),
            ("long-confirmation-laptop", 1366, 768, populated, LONG_CONFIRM),
            ("empty-inventory", 1920, 1080, [], DESTINATIONS),
            ("single-machine", 1920, 1080, machines(1), DESTINATIONS),
            ("large-inventory", 1920, 1080, machines(200), DESTINATIONS),
            ("laptop", 1366, 768, populated, GEOMETRY),
            ("narrow", 800, 600, populated, GEOMETRY),
            ("short", 1280, 720, populated, GEOMETRY),
            ("control-center", 1920, 1080, populated, CONTROL_CENTER),
            ("control-appearance", 1920, 1080, populated,
             CONTROL_CENTER_APPEARANCE),
            ("diagnostics-overview", 1920, 1080, populated,
             DIAGNOSTICS_OVERVIEW),
            ("diagnostics-isolation", 1920, 1080, populated,
             DIAGNOSTICS_ISOLATION),
            ("launcher-open", 1920, 1080, populated, LAUNCHER_OPEN),
            ("system-panel", 1920, 1080, populated, PANEL_OPEN),
            ("confirmation-open", 1920, 1080, populated, CONFIRM_OPEN),
            ("machines-dense", 1920, 1080, machines(24), SELECTION),
        ]

        for name, width, height, inventory, body in cases:
            out = str(Path(OUT) / f"{name}.png") if OUT else ""
            source, messages = scenario_source(
                width, height, inventory, body, out=out
            )
            run(runner, directory, name, source, messages)

        # Capabilities the bridge could not read must disable operations and
        # say why, never fall back to a guess.
        source, messages = scenario_source(
            1920, 1080, machines(3), SELECTION,
            capability_state='"unavailable"',
            capability_verbs="({})",
        )
        run(runner, directory, "capabilities-unavailable", source, messages)

        # An unclaimed, unknown-owner host must still render every surface.
        source, messages = scenario_source(
            1920, 1080, machines(3), DESTINATIONS,
            trust={"text": "unclaimed", "class": "ok", "known": True,
                   "claimed": False, "identity": None, "level": None},
            gpu={"text": "free", "class": "", "known": False},
        )
        run(runner, directory, "unclaimed-host", source, messages)
    finally:
        shutil.rmtree(directory, ignore_errors=True)

    print("HyperLab Quickshell runtime contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
