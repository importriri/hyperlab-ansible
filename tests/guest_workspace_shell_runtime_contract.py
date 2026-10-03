#!/usr/bin/env python3
"""Offscreen runtime contract for the guest HyperLab Workspace Shell.

The real production QML is staged into a temporary directory and loaded by a
plain Qt 6 qmlscene against the Quickshell stand-ins in tests/quickshell_stubs.
Layer-shell windows become items placed by their anchors, so one scene holds
the whole desktop; processes and files answer from fixtures.

Each scenario asserts that:

  1. the tree instantiates and Qt prints nothing unexpected on stderr;
  2. every readout comes from its fixture source, and a missing source hides
     the readout instead of inventing a value;
  3. Desks, projects and the active place follow the helper's model and the
     compositor's workspace, and every change goes back through the helper;
  4. a refused or unreadable Desk configuration is said, not hidden;
  5. the launcher ranks, sections and executes as designed, and leaving the
     session or powering off needs a second Enter.

With HYPERLAB_RENDER_OUT set, each scenario also saves a 1920x1080 capture,
which is how the shell is reviewed visually without a guest.

Not proven here, and therefore physical acceptance on a guest: the real
Quickshell runtime and its API series, layer-shell keyboard focus, Hyprland
IPC events, PipeWire, and real process lifetimes.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from jinja2 import Environment, StrictUndefined

ROOT = Path(__file__).resolve().parents[1]
SHELL = ROOT / "roles/guest_desktop_hyprland/files/quickshell/hyperlab-workspace"
STUBS = ROOT / "tests/quickshell_stubs"
WALLPAPER = ROOT / "roles/guest_desktop_hyprland/templates/bootstrap-wallpaper.svg.j2"
OUT = os.environ.get("HYPERLAB_RENDER_OUT")

PALETTE = {
    "background": "05070b",
    "foreground": "e6ebf5",
    "surface": "0a0e16",
    "accent": "5b8cff",
    "accent_alt": "8fb0ff",
    "urgent": "ff5c7a",
}

MODEL = {
    "version": 1,
    "source": "user",
    "path": "/home/test/.config/hyperlab-workspace/desks.json",
    "errors": [],
    "desks": [
        {"index": 1, "name": "Programming",
         "blurb": "Code, repositories and the terminals around them.",
         "projects": [
             {"slot": 1, "name": "HyperLab", "cwd": "~/src/hyperlab-ansible", "launch": ["kitty"]},
             {"slot": 2, "name": "Doppiari site", "cwd": "~/doppiari-site", "launch": ["kitty"]},
             {"slot": 3, "name": "School", "cwd": "~/school", "launch": ["kitty"]},
         ]},
        {"index": 2, "name": "3D Design",
         "blurb": "Blender and CAD, with the GPU when the machine has one.",
         "projects": [
             {"slot": 1, "name": "Blender renders", "cwd": "~/renders", "launch": ["blender"]},
             {"slot": 2, "name": "CAD parts", "cwd": "~/cad", "launch": ["kitty"]},
         ]},
        {"index": 3, "name": "Research", "blurb": "Reading, notes and documentation.",
         "projects": [
             {"slot": 1, "name": "Technical research", "cwd": "~/notes", "launch": ["kitty"]},
             {"slot": 2, "name": "Documentation", "cwd": "~/docs", "launch": ["kitty"]},
         ]},
        {"index": 4, "name": "Systems", "blurb": "Ansible, networking and infrastructure work.",
         "projects": [
             {"slot": 1, "name": "Ansible", "cwd": "~/ansible", "launch": ["kitty"]},
         ]},
    ],
}

PROC_STAT = [
    "cpu  1000 0 500 8000 100 0 0 0 0 0\ncpu0 1 1 1 1 1 1 1 1 1 1\n",
    "cpu  1100 0 540 8800 110 0 0 0 0 0\ncpu0 1 1 1 1 1 1 1 1 1 1\n",
    "cpu  1180 0 560 9600 120 0 0 0 0 0\ncpu0 1 1 1 1 1 1 1 1 1 1\n",
]
MEMINFO = "MemTotal:       16252928 kB\nMemFree:  1000 kB\nMemAvailable:   12992512 kB\n"
ROUTE = (
    "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask\n"
    "enp1s0\t00000000\t0100A8C0\t0003\t0\t0\t100\t00000000\n"
)

PRELUDE = r"""
import QtQuick
import Quickshell
import Quickshell.Hyprland
import Quickshell.Services.Pipewire

Item {
    id: root

    width: 1920
    height: 1080

    property int failures: 0
    property int stepIndex: 0
    property var steps: []

    function walk(item, visit) {
        if (!item)
            return;
        visit(item);
        const kids = item.children || [];
        for (let i = 0; i < kids.length; i++)
            walk(kids[i], visit);
    }

    function texts() {
        const out = [];
        walk(shellLoader.item, item => {
            if (item.text !== undefined && typeof item.text === "string"
                    && item.visible && item.text.length && item.font !== undefined)
                out.push(item.text);
        });
        return out;
    }

    function visibleText(value) {
        return texts().indexOf(value) >= 0;
    }

    function findWith(property) {
        let found = null;
        walk(shellLoader.item, item => {
            if (!found && item[property] !== undefined)
                found = item;
        });
        return found;
    }

    function check(condition, message) {
        if (!condition) {
            console.log("CONTRACT-FAIL: " + message);
            failures += 1;
        }
    }

    function ran(command) {
        return QsHarness.commands.indexOf(command) >= 0;
    }

    function capture(name, next) {
        if (!"@@OUT@@".length) {
            next();
            return;
        }
        root.grabToImage(result => {
            result.saveToFile("@@OUT@@/" + name + ".png");
            next();
        });
    }

    function advance() {
        if (stepIndex >= steps.length) {
            Qt.exit(failures === 0 ? 0 : 3);
            return;
        }
        const step = steps[stepIndex];
        stepIndex += 1;
        pause.interval = step.wait;
        pause.action = step.run;
        pause.restart();
    }

    Timer {
        id: pause

        property var action: null

        onTriggered: action(() => root.advance())
    }

    Timer {
        interval: 30000
        running: true
        onTriggered: {
            console.log("CONTRACT-FAIL: scenario timed out at step " + root.stepIndex);
            Qt.exit(4);
        }
    }

    Image {
        anchors.fill: parent
        source: "wallpaper.svg"
        sourceSize: Qt.size(1920, 1080)
    }

    // Two stand-in windows where Hyprland would tile them, for the capture.
    Repeater {
        model: [
            { "x": 12, "w": 940, "title": "kitty — ~/src/hyperlab-ansible",
              "body": "sid@arch-dev-vfio ~/src/hyperlab-ansible (main) $ ./verify.sh\n== static contract                     OK\n== schemas                             OK\n== guest workspace shell runtime       OK\n== bats                                OK\n\nVERIFY: ALL GREEN\nsid@arch-dev-vfio ~/src/hyperlab-ansible (main) $ _" },
            { "x": 964, "w": 944, "title": "docs/guest-workspace-shell.md — nvim",
              "body": "# Guest Workspace Shell\n\nA Desk groups projects and their windows inside\none guest. It is organisation, never isolation.\n\n    Desk d    workspaces d*10+1 .. d*10+9\n    slot s    workspace  d*10+s" }
        ]

        Rectangle {
            required property var modelData

            x: modelData.x
            y: 60 + 12
            width: modelData.w
            height: 1080 - 60 - 76 - 24
            radius: 10
            color: "#f00a0e16"
            border.width: 2
            border.color: modelData.x < 100 ? "#5b8cff" : "#2a3954"

            Text {
                x: 18; y: 12
                text: parent.modelData.title
                color: "#9fb0cc"
                font.family: "IBM Plex Sans"
                font.pixelSize: 13
            }

            Text {
                x: 18; y: 48
                text: parent.modelData.body
                color: "#c9d6ee"
                font.family: "IBM Plex Mono"
                font.pixelSize: 14
                lineHeight: 1.5
            }
        }
    }

    Loader {
        id: shellLoader

        anchors.fill: parent
        active: false
        source: "shell/shell.qml"
    }

    function baseFixtures() {
        QsHarness.processes = {
            "hyperlab-desk model": { "stdout": @@MODEL@@, "code": 0 },
            "sh -c*": { "stdout": "8, 47\n", "code": 0 },
            "hyperlab-desk project-open*": { "stdout": "{}", "code": 0 },
            "hyperlab-desk project-new*": { "stdout": "{}", "code": 0 }
        };
        QsHarness.files = {
            "/proc/stat": @@PROC_STAT@@,
            "/proc/meminfo": @@MEMINFO@@,
            "/proc/net/route": @@ROUTE@@
        };
        DesktopEntries.applications.values = [
            { "name": "Blender", "genericName": "3D modeller", "icon": "blender",
              "keywords": ["3d", "render"], "noDisplay": false,
              "execute": function() { QsHarness.record(["launch", "blender"]); } },
            { "name": "kitty", "genericName": "Terminal", "icon": "kitty",
              "keywords": ["shell"], "noDisplay": false,
              "execute": function() { QsHarness.record(["launch", "kitty"]); } },
            { "name": "Thunar", "genericName": "File Manager", "icon": "thunar",
              "keywords": [], "noDisplay": false,
              "execute": function() { QsHarness.record(["launch", "thunar"]); } },
            { "name": "Hidden helper", "genericName": "", "icon": "",
              "keywords": [], "noDisplay": true,
              "execute": function() {} }
        ];
        Hyprland.focusedWorkspace = { "id": 11 };
        Hyprland.workspaces.values = [
            { "id": 11, "lastIpcObject": { "windows": 3 } },
            { "id": 12, "lastIpcObject": { "windows": 2 } },
            { "id": 31, "lastIpcObject": { "windows": 1 } }
        ];
    }

    Component.onCompleted: {
        baseFixtures();
        scenario();
        shellLoader.active = true;
        root.advance();
    }
"""


SCENARIOS = {
    "desktop": r"""
    function scenario() {
        steps = [
            { "wait": 4600, "run": done => {
                check(shellLoader.status === Loader.Ready, "shell did not load");
                check(ran("hyperlab-desk model"), "Desk model was not read from the helper");
                for (const value of ["WORKSTATION", "Programming", "HyperLab", "GPU", "8%",
                                     "CPU", "RAM", "VOL", "65%", "NET", "enp1s0",
                                     "Sat 3 Oct  ·  16:52", "3D Design", "Research",
                                     "Systems", "ALT+1", "ALT+Space"])
                    check(visibleText(value), "missing on the desktop: " + value);
                check(texts().some(t => /^\d+%$/.test(t) && t !== "8%" && t !== "65%"),
                      "CPU percentage never appeared");
                check(visibleText("3.1 / 15.5 G"), "memory readout is wrong");
                capture("desktop", done);
            } },
            { "wait": 50, "run": done => {
                Hyprland.focusedWorkspace = { "id": 21 };
                done();
            } },
            { "wait": 400, "run": done => {
                check(visibleText("DESK 2  ·  BLENDER RENDERS"), "Desk OSD did not announce Desk 2: " + texts());
                check(visibleText("Blender renders"), "context island did not follow the workspace");
                capture("desk-switch", done);
            } },
            { "wait": 50, "run": done => {
                // A workspace outside every Desk is said as a workspace.
                Hyprland.focusedWorkspace = { "id": 5 };
                done();
            } },
            { "wait": 300, "run": done => {
                check(visibleText("Workspace 5"), "a non-Desk workspace was not named");
                done();
            } }
        ];
    }
""",
    "no-gpu": r"""
    function scenario() {
        QsHarness.processes = Object.assign({}, QsHarness.processes,
            { "sh -c*": { "stdout": "", "code": 127 } });
        QsHarness.files = { "/proc/stat": "garbage", "/proc/meminfo": "", "/proc/net/route": "Iface\n" };
        steps = [
            { "wait": 2600, "run": done => {
                check(!visibleText("GPU"), "GPU readout shown without a driver");
                check(!visibleText("CPU"), "CPU readout shown from an unreadable source");
                check(!visibleText("RAM"), "RAM readout shown from an unreadable source");
                check(visibleText("offline"), "missing default route is not said");
                done();
            } }
        ];
    }
""",
    "overview": r"""
    function scenario() {
        steps = [
            { "wait": 900, "run": done => {
                check(QsHarness.ipc.workspace !== undefined, "IPC target workspace missing");
                check(QsHarness.ipc.workspace.overview() === "open", "overview did not open");
                done();
            } },
            { "wait": 700, "run": done => {
                for (const value of ["DESKS · THIS MACHINE", "Where do you want to work?",
                                     "3 windows", "2 windows", "1 window", "closed",
                                     "YOU ARE HERE · 5 OPEN", "1 WINDOW OPEN", "QUIET",
                                     "Doppiari site", "Blender renders", "+  New project"])
                    check(visibleText(value), "missing in the overview: " + value);
                check(texts().some(t => t.indexOf("organisation, not isolation") >= 0),
                      "the overview no longer says a Desk is not isolation");
                capture("overview", done);
            } },
            { "wait": 50, "run": done => {
                const overview = findWith("selectedDesk");
                check(overview !== null, "overview surface not found");
                check(overview.selectedDesk === 1, "overview did not start on the current Desk");
                overview.move(0, 1);
                overview.move(0, 1);
                check(overview.selectedRow === 1, "row selection did not move");
                overview.activate();
                check(ran("hyperlab-desk project-open 1 2"), "Enter on a project did not open it");
                check(!overview.open, "overview stayed open after opening a project");
                QsHarness.ipc.workspace.overview();
                overview.move(1, 0);
                overview.activate();
                check(ran("hyperlab-desk desk 2"), "Enter on a Desk did not go there");
                QsHarness.ipc.workspace.newProject();
                done();
            } },
            { "wait": 300, "run": done => {
                const overview = findWith("selectedDesk");
                check(overview.creating, "ALT+N did not start a new project");
                capture("new-project", () => {
                    overview.finishCreating(true, "Renders 2");
                    done();
                });
            } },
            { "wait": 300, "run": done => {
                check(ran("hyperlab-desk project-new 1 Renders 2"), "new project did not reach the helper");
                check(visibleText("Project Renders 2 added to Programming"), "helper success was not reported");
                QsHarness.ipc.workspace.close();
                done();
            } }
        ];
    }
""",
    "launcher": r"""
    function scenario() {
        steps = [
            { "wait": 900, "run": done => {
                check(QsHarness.ipc.workspace.launcher() === "open", "launcher did not open");
                done();
            } },
            { "wait": 400, "run": done => {
                const launcher = findWith("results");
                check(launcher !== null, "launcher surface not found");
                const field = (() => {
                    let input = null;
                    walk(launcher, item => {
                        if (!input && item.cursorPosition !== undefined && item.maximumLength === 32767)
                            input = item;
                    });
                    return input;
                })();
                check(field !== null, "search field not found");
                field.text = "blen";
                check(launcher.query === "blen", "the query did not follow the field");
                const titles = launcher.results.map(r => r.section + ":" + r.title);
                check(titles[0] === "APPLICATIONS:Blender", "Blender is not the first result: " + titles);
                check(titles.indexOf("PROJECTS:Blender renders") >= 0, "project missing: " + titles);
                check(titles.indexOf("ACTIONS:New project “blen” in Programming") >= 0,
                      "new-project action missing: " + titles);
                check(!titles.some(t => t.indexOf("Hidden helper") >= 0), "a NoDisplay entry was listed");
                check(visibleText("APPLICATIONS") && visibleText("PROJECTS") && visibleText("ACTIONS"),
                      "section titles are not drawn");
                capture("launcher", done);
            } },
            { "wait": 50, "run": done => {
                const launcher = findWith("results");
                launcher.activate(0);
                check(ran("launch blender"), "Enter did not launch the application");
                check(!launcher.open, "launcher stayed open after launching");
                QsHarness.ipc.workspace.launcher();
                done();
            } },
            { "wait": 300, "run": done => {
                const launcher = findWith("results");
                launcher.query = "power";
                const index = launcher.results.findIndex(r => r.id === "poweroff");
                check(index >= 0, "power off action missing");
                launcher.activate(index);
                check(!ran("systemctl poweroff"), "power off ran on the first Enter");
                check(launcher.armed === "poweroff", "power off was not armed");
                launcher.activate(index);
                check(ran("systemctl poweroff"), "power off did not run on the second Enter");
                QsHarness.ipc.workspace.launcher();
                done();
            } },
            { "wait": 300, "run": done => {
                const launcher = findWith("results");
                launcher.query = "renders";
                const index = launcher.results.findIndex(r => r.kind === "project");
                launcher.activate(index);
                check(ran("hyperlab-desk project-open 2 1"), "a project result did not open its project");
                done();
            } }
        ];
    }
""",
    "refused-config": r"""
    function scenario() {
        const refused = JSON.parse(@@MODEL@@);
        refused.source = "builtin";
        refused.errors = ["/home/test/.config/hyperlab-workspace/desks.json: Desk 'programming' appears twice"];
        QsHarness.processes = Object.assign({}, QsHarness.processes,
            { "hyperlab-desk model": { "stdout": JSON.stringify(refused), "code": 0 } });
        steps = [
            { "wait": 900, "run": done => {
                QsHarness.ipc.workspace.overview();
                done();
            } },
            { "wait": 600, "run": done => {
                check(texts().some(t => t.indexOf("Your desks.json was refused") === 0),
                      "a refused configuration was not reported");
                capture("refused-config", done);
            } }
        ];
    }
""",
    "helper-missing": r"""
    function scenario() {
        QsHarness.processes = Object.assign({}, QsHarness.processes,
            { "hyperlab-desk model": { "stdout": "", "stderr": "not found", "code": 127 } });
        steps = [
            { "wait": 900, "run": done => {
                check(!visibleText("Programming"), "Desks were invented without a helper");
                QsHarness.ipc.workspace.overview();
                done();
            } },
            { "wait": 600, "run": done => {
                check(visibleText("The Desk helper could not be run (exit 127)."),
                      "a missing helper was not reported");
                done();
            } }
        ];
    }
""",
}


def stage(directory: Path) -> None:
    shell = directory / "shell"
    shutil.copytree(SHELL, shell)
    for path in shell.glob("*.qml"):
        source = path.read_text()
        if "PanelWindow {" in source:
            source = re.sub(r"(?m)^    anchors \{", "    edges {", source)
            source = re.sub(r"(?m)^\s*WlrLayershell\.[^\n]*\n", "", source)
        path.write_text(source)

    wallpaper = Environment(undefined=StrictUndefined).from_string(WALLPAPER.read_text())
    (directory / "wallpaper.svg").write_text(wallpaper.render(
        guest_theme_name="hyperlab-workstation",
        guest_theme_surface="desktop",
        guest_theme_palette=PALETTE,
    ))


def scene(name: str) -> str:
    out = str(Path(OUT).resolve()) if OUT else ""
    source = PRELUDE + SCENARIOS[name] + "}\n"
    replacements = {
        "@@OUT@@": out,
        "@@MODEL@@": json.dumps(json.dumps(MODEL)),
        "@@PROC_STAT@@": json.dumps(PROC_STAT),
        "@@MEMINFO@@": json.dumps(MEMINFO),
        "@@ROUTE@@": json.dumps(ROUTE),
    }
    for key, value in replacements.items():
        source = source.replace(key, value)
    return source


def harmless(line: str) -> bool:
    return (
        not line.strip()
        or "Could not find the Qt platform plugin" in line
        or "QStandardPaths" in line
        or line.startswith("qt.tools.qmlscene.deprecated:")
        or "propagateSizeHints" in line
    )


def run(runner: str, directory: Path, name: str) -> None:
    path = directory / f"{name}.qml"
    path.write_text(scene(name))
    try:
        result = subprocess.run(
            [runner, str(path)],
            capture_output=True,
            text=True,
            timeout=90,
            env={
                **os.environ,
                "QML_IMPORT_PATH": str(STUBS),
                "QT_QPA_PLATFORM": "offscreen",
                "QT_QUICK_BACKEND": "software",
                "QT_FORCE_STDERR_LOGGING": "1",
            },
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise SystemExit(f"guest workspace shell runtime: {name} never completed") from None

    lines = (result.stderr + result.stdout).splitlines()
    failures = [line for line in lines if "CONTRACT-FAIL:" in line]
    noise = [line for line in lines if not harmless(line) and "CONTRACT-FAIL:" not in line]
    if failures or noise or result.returncode != 0:
        detail = "\n".join(failures + noise) or f"exit {result.returncode}"
        raise SystemExit(f"guest workspace shell runtime: {name} failed\n{detail}")
    print(f"  {name}: OK")


def main() -> int:
    runner = (
        shutil.which("qmlscene", path="/usr/lib/qt6/bin")
        or shutil.which("qmlscene6")
    )
    if not runner:
        if os.environ.get("HYPERLAB_REQUIRE_QML_RUNTIME") == "1":
            raise SystemExit(
                "guest workspace shell runtime: Qt 6 qmlscene is required but not installed"
            )
        print("HyperLab guest workspace shell runtime contract: SKIPPED (no Qt 6 qmlscene)")
        return 0

    if OUT:
        Path(OUT).mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="hyperlab-guest-shell-") as temporary:
        directory = Path(temporary)
        stage(directory)
        for name in SCENARIOS:
            run(runner, directory, name)

    print("HyperLab guest workspace shell runtime contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
