#!/usr/bin/env python3
"""Real Quickshell capability processes answer or report a bounded, specific failure."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import host_quickshell_runtime_contract as runtime

QML = runtime.QML

FIXTURE = '''#!/usr/bin/env python3
import json
import os
from pathlib import Path
import signal
import sys
import time
if len(sys.argv) < 3 or sys.argv[1] != "capabilities":
    raise SystemExit(0)
mode = sys.argv[2]
if mode == "stall":
    time.sleep(30)
elif mode == "crash":
    os.kill(os.getpid(), signal.SIGKILL)
elif mode == "refused":
    print(json.dumps({"phase": "refused", "reason": "Permission denied reading the checked inventory"}))
    raise SystemExit(2)
elif mode == "exit":
    raise SystemExit(7)
elif mode == "invalid":
    print("not-json")
elif mode == "success" or mode.startswith("success-"):
    if mode.startswith("success-"):
        info = Path("/proc") / mode.removeprefix("success-") / "stat"
        if info.exists() and info.read_text().split()[2] != "Z":
            raise SystemExit(9)
    print(json.dumps({"phase": "capabilities", "machine": {"name": mode},
                      "verbs": {"shutdown": {"available": True, "reason": ""}}}))
'''


def run_case(directory: Path, bridge: Path, mode: str) -> dict:
    actions = (QML / "MachineActions.qml").read_text()
    actions = actions.replace("/usr/local/bin/privatestack-machine-actions", str(bridge))
    if mode == "inspection-missing":
        actions = actions.replace('"/usr/bin/test"', json.dumps(str(directory / "missing-test")))
    # Exercise real timers without spending minutes in a regression check.
    actions = re.sub(r'(property int capabilityTimeoutMs:) \d+', r'\1 1200', actions)
    actions = re.sub(r'(property int capabilityStartTimeoutMs:) \d+', r'\1 100', actions)
    (directory / "MachineActions.qml").write_text(actions)
    (directory / "shell.qml").write_text('''
import Quickshell
import QtQuick
Scope {
    id: fixture
    property bool clearRetained: false
    property bool replaced: false
    ShellState { id: state }
    MachineActions {
        id: actions
        onCapabilityRequested: (serial, machine, generation) =>
            state.beginCapabilityRequest(serial, machine, generation)
        onCapabilityAnswered: (serial, machine, raw, exitCode, detail) => {
            state.applyCapabilityAnswer(serial, machine, raw, exitCode, detail);
            const before = JSON.stringify(state.machineCapabilities);
            const duplicateAccepted = state.applyCapabilityAnswer(serial, machine, "", 2, "late failure");
            const result = Object.assign({}, state.machineCapabilities, {clearRetained: fixture.clearRetained, duplicateAccepted: duplicateAccepted, duplicateChanged: before !== JSON.stringify(state.machineCapabilities)});
            console.log("CAPABILITY_RESULT=" + JSON.stringify(result));
            Qt.quit();
        }
    }
    Component.onCompleted: actions.probe(''' + json.dumps("stall" if mode in {"supersede", "clear"} else mode) + ''', 1)
    Timer {
        interval: 10; repeat: true
        running: ''' + str(mode in {"supersede", "clear"}).lower() + ''' && !fixture.replaced
        onTriggered: {
            const runner = actions.capabilityRunner;
            if (runner === null || !(Number(runner.processId) > 0))
                return;
            // Use the actual retiring PID, never a timing-based pid file.
            const target = "success-" + runner.processId;
            fixture.replaced = true;
            ''' + ('actions.clearCapabilities(); state.clearCapabilities(); fixture.clearRetained = actions.capabilityRunner !== null;' if mode == "clear" else '') + '''
            actions.probe(target, 1);
        }
    }
    Timer {
        interval: 3500; running: true
        onTriggered: { console.log("CAPABILITY_RESULT=" + JSON.stringify(state.machineCapabilities)); Qt.quit(); }
    }
}
''')
    result = subprocess.run(
        [shutil.which("qs"), "-p", str(directory), "--no-color"],
        env={**os.environ, "QT_QPA_PLATFORM": "offscreen", "QT_QUICK_BACKEND": "software",
             "QT_FORCE_STDERR_LOGGING": "1", "WAYLAND_DISPLAY": "",
             "XDG_RUNTIME_DIR": str(directory / "run"), "XDG_CACHE_HOME": str(directory / "cache")},
        text=True, capture_output=True, timeout=10, check=False,
    )
    output = result.stdout + result.stderr
    records = re.findall(r"CAPABILITY_RESULT=(\{[^\n]+\})", output)
    assert result.returncode == 0 and len(records) == 1, f"capability process did not finish: {output}"
    assert not re.search(r"ReferenceError|TypeError|Error loading configuration", output), output
    answer = json.loads(records[0])
    assert answer["state"] != "loading", "capability request never answered"
    assert answer.get("clearRetained") is False, "clearing capabilities retained a pending runner"
    assert answer.get("duplicateChanged") is False, "a duplicate callback changed a spent capability result"
    assert answer.get("duplicateAccepted") is False, "a spent capability request accepted a duplicate reply"
    return answer


def main() -> int:
    assert shutil.which("qs"), "real Quickshell is required for capability transport"
    with tempfile.TemporaryDirectory(prefix="hl-cap-") as temporary:
        directory = Path(temporary)
        (directory / "run").mkdir(mode=0o700)
        (directory / "OperationTracker.qml").write_text((QML / "OperationTracker.qml").read_text())
        (directory / "ShellState.qml").write_text(runtime.adapt_state((QML / "ShellState.qml").read_text()))
        bridge = directory / "bridge"
        bridge.write_text(FIXTURE)
        bridge.chmod(0o700)
        good = run_case(directory, bridge, "success")
        assert good["state"] == "ok" and good["verbs"]["shutdown"]["available"], "a successful bridge answer was lost"
        cases = [(bridge, "refused", "Permission denied reading the checked inventory"),
                 (bridge, "empty", "returned no capability data"),
                 (bridge, "invalid", "returned invalid capability data"),
                 (bridge, "exit", "exited with code 7"),
                 (bridge, "crash", "was interrupted"),
                 (bridge, "stall", "timed out"),
                 (directory / "missing", "missing", "not installed")]
        denied = directory / "denied"
        denied.write_text(FIXTURE)
        denied.chmod(0o600)
        cases.append((denied, "denied", "not executable"))
        invalid_interpreter = directory / "invalid-interpreter"
        invalid_interpreter.write_text("#!/nonexistent/hyperlab-test-interpreter\n")
        invalid_interpreter.chmod(0o700)
        cases.extend([(invalid_interpreter, "interpreter", "executable exists but could not start"),
                      (directory / "missing", "inspection-missing", "path inspection timed out")])
        for executable, mode, reason in cases:
            answer = run_case(directory, executable, mode)
            assert answer["state"] == "unavailable" and not answer["verbs"], f"{mode}: failed bridge left actionable or unanswered capabilities: {answer}"
            assert reason.lower() in answer["detail"].lower(), f"{mode}: known cause lost: {answer['detail']}"
        for mode in ("supersede", "clear"):
            answer = run_case(directory, bridge, mode)
            assert answer["state"] == "ok" and answer["machine"].startswith("success-"), f"{mode}: retiring probe survived or replaced the new answer: {answer}"
    print("Machine capability transport contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
