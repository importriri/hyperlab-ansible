#!/usr/bin/env python3
"""Execute the launcher's Send clipboard to mode offscreen (ADR 0020).

The real launcher, surfaces and OSD choose one running Machine and report
the send; the request is recorded from the surfaces signal, never sent.
With HYPERLAB_RENDER_OUT=<dir> each scenario saves a capture.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import host_quickshell_runtime_contract as runtime

ROOT = Path(__file__).resolve().parents[1]
QML = ROOT / "roles/host_desktop_common/files/quickshell/hyperlab"

PICK = """
            const sent = [];
            sharedSurfaces.clipboardSendRequested.connect(machine => sent.push(machine));
            sharedSurfaces.openLauncher("", "clipboard");
            check(launcher.open && launcher.clipboardMode,
                  "the clipboard key did not open the launcher in clipboard mode");
            const rows = launcher.results.filter(row => row.kind === "machine");
            check(rows.length > 0 && rows.every(row => String(row.machine.state) === "running"),
                  "a Machine that is not running was offered as a target");
            check(launcher.results.every(row => row.kind === "section" || row.kind === "machine"),
                  "clipboard mode offered destinations or commands");
            check(launcher.results[0].title === "Send the host clipboard to",
                  "the clipboard target list is not labelled");
            launcher.query = "fixture-004";
            check(launcher.results.filter(row => row.kind === "machine").length === 1,
                  "filtering the targets did not narrow them");
            launcher.query = "";
            const target = rows[0].machine.name;
            launcher.activate(0);
            check(!launcher.open, "the launcher stayed open after choosing a target");
            check(sent.length === 1 && sent[0] === target,
                  "choosing a Machine did not request exactly one send to it");
            check(sharedSurfaces.osdKind === "clipboard" && sharedSurfaces.osdPending,
                  "the send is not reported as pending");
            sharedSurfaces.settleActionOsd("clipboard:" + target, true, "");
            check(!sharedSurfaces.osdPending && sharedSurfaces.osdFailure === ""
                  && osd.label === "Sent to" && osd.value === target,
                  "a completed send is not reported with its target");
            // The ordinary palette is unchanged after a clipboard opening.
            sharedSurfaces.openLauncher("");
            check(!launcher.clipboardMode
                  && launcher.results.some(row => row.kind === "destination"),
                  "the command palette inherited clipboard mode");
            sharedSurfaces.closeLauncher();
            sharedSurfaces.openLauncher("", "clipboard");
"""

REFUSED = """
            const sent = [];
            sharedSurfaces.clipboardSendRequested.connect(machine => sent.push(machine));
            check(!sharedSurfaces.requestClipboardSend("../etc", ""),
                  "a malformed target was accepted");
            check(sent.length === 0, "a malformed target reached the transport");
            sharedSurfaces.requestClipboardSend("fixture-000", "");
            sharedSurfaces.settleActionOsd("clipboard:fixture-000", false,
                "fixture-000 has no clipboard receiver");
            check(sharedSurfaces.osdFailure === "fixture-000 has no clipboard receiver"
                  && osd.value === "Failed",
                  "a refused send is not reported as failed with its reason");
            sharedSurfaces.openLauncher("", "clipboard");
            launcher.query = "no-such-machine";
            check(launcher.results.length === 0, "an unmatched query still offered a target");
"""


def static_checks() -> None:
    launcher = (QML / "LauncherSurface.qml").read_text(encoding="utf-8")
    surfaces = (QML / "ShellSurfaces.qml").read_text(encoding="utf-8")
    hyprland = (ROOT / "roles/host_desktop_hyprland/templates/hyprland.lua.j2").read_text(encoding="utf-8")
    ipc = (QML / "ShellIpc.qml").read_text(encoding="utf-8")
    for text, needle, message in (
        (launcher, "launcher.shellSurfaces.requestClipboardSend(", "the launcher no longer requests one send"),
        (surfaces, "signal clipboardSendRequested(string machine)", "the surfaces lost the send request"),
        (ipc, 'ipc.shellSurfaces.openLauncher("", "clipboard")', "the IPC no longer opens clipboard mode"),
        (hyprland, 'main_mod .. " + SHIFT + V",\n    hl.dsp.exec_cmd(\n        '
                   '"/usr/bin/qs -c hyperlab ipc call launcher clipboard"', "SUPER + SHIFT + V is not the clipboard key"),
    ):
        if needle not in text:
            raise SystemExit(f"Clipboard shell contract: {message}")
    for name in ("LauncherSurface.qml", "ShellSurfaces.qml", "OsdSurface.qml"):
        source = (QML / name).read_text(encoding="utf-8")
        if "Quickshell.Io" in source or "wl-paste" in source or "Process {" in source:
            raise SystemExit(f"Clipboard shell contract: {name} gained a transport")


def main() -> int:
    static_checks()
    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    if not runner:
        if os.environ.get("HYPERLAB_REQUIRE_QML_RUNTIME") == "1":
            raise SystemExit("Clipboard shell contract: Qt 6 qmlscene is required")
        print("Clipboard shell contract: SKIPPED (Qt 6 qmlscene is not installed on this host)")
        return 0
    if runtime.OUT:
        Path(runtime.OUT).mkdir(parents=True, exist_ok=True)
    directory = runtime.stage()
    try:
        for name, body in (("clipboard-pick", PICK), ("clipboard-refused", REFUSED)):
            out = str(Path(runtime.OUT) / f"{name}.png") if runtime.OUT else ""
            source, messages = runtime.scenario_source(1920, 1080, runtime.machines(8), body, out=out)
            runtime.run(runner, directory, name, source, messages)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    print("HyperLab clipboard shell contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
