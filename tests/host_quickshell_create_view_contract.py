#!/usr/bin/env python3
"""Execute the shell's Create view offscreen against a real creation plan (ADR 0017).

The plan is produced by the real hyperlabctl factory code over the checked-in
Templates and images, wrapped the way the bridge relays it, and validated by
the real ShellState. The view's request goes to a recording transport fixture.
With HYPERLAB_RENDER_OUT=<dir> every scenario saves a capture.
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

import host_quickshell_runtime_contract as runtime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))

from hyperlabctl.machine_provision import creation_plan  # noqa: E402

VIEW = ROOT / "roles/host_desktop_common/files/quickshell/hyperlab/CreateMachineView.qml"


def real_plan() -> dict:
    blob = base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + bytes(range(32))).decode()
    with tempfile.TemporaryDirectory() as temporary:
        home = Path(temporary)
        (home / ".ssh").mkdir()
        (home / ".ssh/hyperlab_ed25519.pub").write_text(f"ssh-ed25519 {blob} fixture\n")
        plan = creation_plan(ROOT, home=home, cpu_count=8)
    return {"phase": "create-plan", "plan": plan}


OPEN = """
            sharedMachineActions.createPlanAnswer = @@PLAN@@;
            sharedSurfaces.openWorkspace("machines");
            const opener = window.find(workspaceSurface, "newMachine");
            check(opener !== null && opener.visible, "Machines has no New Machine control");
            opener.activated();
            check(sharedState.createPlan.state === "ok",
                  "the real creation plan was rejected by ShellState");
"""

SERVER = OPEN + """
            check(window.find(workspaceSurface, "createName") === null || !window.find(workspaceSurface, "createName").visible,
                  "the form showed before a Template was chosen");
            check(sharedState.createProblem({template: ""}) === "Choose a Template",
                  "a request without a Template was not explained");
            const debian = window.find(workspaceSurface, "createTemplate-server-debian");
            check(debian !== null && debian.enabled, "server-debian is not offered");
            debian.activated();
            const name = window.find(workspaceSurface, "createName");
            check(name !== null && name.visible, "choosing a Template did not show the form");
            check(window.find(workspaceSurface, "createNetwork-services") !== null
                  && window.find(workspaceSurface, "createNetwork-clean") === null,
                  "the networks are not the Template's allowlist");
            const submit = window.find(workspaceSurface, "createSubmit");
            check(!submit.enabled, "an empty name could be submitted");
            name.text = "fixture-000";
            check(!submit.enabled && window.find(workspaceSurface, "createProblem").text.indexOf("already exists") >= 0,
                  "an existing Machine name was accepted");
            name.text = "srv-deb-02";
            check(submit.enabled, "a valid server request was not allowed: "
                  + window.find(workspaceSurface, "createProblem").text);
            window.find(workspaceSurface, "createNetwork-services").activated();
            submit.activated();
            check(sharedMachineActions.created.length === 1
                  && JSON.stringify(sharedMachineActions.created[0])
                     === JSON.stringify(["server-debian", "srv-deb-02", "permanent", "services", "balanced"]),
                  "the bridge got a different request: "
                  + JSON.stringify(sharedMachineActions.created));
            check(window.find(workspaceSurface, "createKey").text.indexOf("SHA256:") >= 0,
                  "the guest key fingerprint is not shown");
            check(window.find(workspaceSurface, "createProblem").text.indexOf("Recording srv-deb-02") >= 0,
                  "a pending request is not shown as pending");
"""

CUSTOM = OPEN + """
            window.find(workspaceSurface, "createTemplate-server-fedora").activated();
            window.find(workspaceSurface, "createName").text = "srv-fed-02";
            check(window.find(workspaceSurface, "createLifecycle-permanent").selected,
                  "a server does not start as permanent, its Template default");
            window.find(workspaceSurface, "createLifecycle-disposable").activated();
            window.find(workspaceSurface, "createProfile-custom").activated();
            const memory = window.find(workspaceSurface, "createMemory");
            const vcpus = window.find(workspaceSurface, "createVcpus");
            const disk = window.find(workspaceSurface, "createDisk");
            check(memory.visible && memory.text === "2048" && disk.text === "5",
                  "custom fields do not start at the image limits");
            memory.text = "1024";
            check(window.find(workspaceSurface, "createProblem").text === "Memory must be at least 2048 MB",
                  "a memory below the image floor was not explained");
            memory.text = "4096";
            vcpus.text = "9";
            check(window.find(workspaceSurface, "createProblem").text === "vCPUs must be between 1 and 8",
                  "more vCPUs than the host has were allowed");
            vcpus.text = "2";
            disk.text = "4";
            check(window.find(workspaceSurface, "createProblem").text.indexOf("at least 5 GiB") >= 0,
                  "a disk smaller than the sealed image was allowed");
            disk.text = "24";
            check(window.find(workspaceSurface, "createSubmit").enabled, "a valid custom request was refused");
            window.find(workspaceSurface, "createSubmit").activated();
            check(JSON.stringify(sharedMachineActions.created[0])
                  === JSON.stringify(["server-fedora", "srv-fed-02", "disposable", "dev", "custom", "4096", "2", "24"]),
                  "custom values reached the bridge differently: "
                  + JSON.stringify(sharedMachineActions.created));
            // A refusal from the bridge is shown as its own reason.
            sharedMachineActions.createPhase = "refused";
            sharedMachineActions.createDetail = "the Template does not allow that network";
            check(window.find(workspaceSurface, "createProblem").text === "the Template does not allow that network",
                  "a bridge refusal was not shown");
"""

WORKSTATION = OPEN + """
            const work = window.find(workspaceSurface, "createTemplate-workstation-dev");
            check(work !== null && work.enabled, "workstation-dev is not offered");
            work.activated();
            window.find(workspaceSurface, "createName").text = "dev-02";
            check(window.find(workspaceSurface, "createLifecycle-disposable") === null,
                  "a workstation offered a disposable Machine (ADR 0018)");
            check(window.find(workspaceSurface, "createProfile-performance") !== null
                  && window.find(workspaceSurface, "createProfile-minimum") === null,
                  "the resource profiles are not the Template's");
            check(window.find(workspaceSurface, "createSubmit").enabled, "a workstation request was refused");
"""

DISPATCH = SERVER + """
            sharedMachineActions.createPhase = "dispatched";
            check(sharedSurfaces.selectedMachineId === "srv-deb-02",
                  "a dispatched creation did not open the new Machine");
            check(window.find(workspaceSurface, "createName") === null,
                  "the Create view stayed open after provisioning started");
            check(window.find(workspaceSurface, "newMachine").visible, "Machines did not come back");
"""

UNAVAILABLE = """
            sharedMachineActions.createPlanAnswer = null;
            sharedSurfaces.openWorkspace("machines");
            window.find(workspaceSurface, "newMachine").activated();
            check(sharedState.createPlan.state === "unavailable",
                  "a bridge failure produced a plan");
            check(!window.find(workspaceSurface, "createSubmit").visible,
                  "a request could be submitted without a plan");
            window.find(workspaceSurface, "createBack").activated();
            check(window.find(workspaceSurface, "newMachine").visible, "Back did not return to Machines");
"""


def static_checks() -> None:
    source = VIEW.read_text(encoding="utf-8")
    for forbidden in ("Process", "Quickshell.Io", "password:", "echoMode", "TextInput.Password"):
        if forbidden in source:
            raise SystemExit(f"Create view contract: the view must not hold {forbidden!r}")
    if "createArguments(view.form)" not in source or "submitCreate(args)" not in source:
        raise SystemExit("Create view contract: the view no longer submits ShellState's arguments")


def main() -> int:
    static_checks()
    runner = shutil.which("qmlscene", path="/usr/lib/qt6/bin") or shutil.which("qmlscene6")
    if not runner:
        if os.environ.get("HYPERLAB_REQUIRE_QML_RUNTIME") == "1":
            raise SystemExit("Create view contract: Qt 6 qmlscene is required")
        print("Create view contract: SKIPPED (Qt 6 qmlscene is not installed on this host)")
        return 0
    plan = json.dumps(real_plan())
    out_dir = runtime.OUT
    if out_dir:
        Path(out_dir).mkdir(parents=True, exist_ok=True)
    directory = runtime.stage()
    try:
        inventory = runtime.machines(6)
        cases = [
            ("create-server", 1920, 1080, SERVER),
            ("create-custom", 1920, 1080, CUSTOM),
            ("create-workstation", 1366, 768, WORKSTATION),
            ("create-narrow", 800, 600, WORKSTATION),
            ("create-dispatched", 1920, 1080, DISPATCH),
            ("create-unavailable", 1920, 1080, UNAVAILABLE),
        ]
        for name, width, height, body in cases:
            out = str(Path(out_dir) / f"{name}.png") if out_dir else ""
            source, messages = runtime.scenario_source(
                width, height, inventory, body.replace("@@PLAN@@", plan), out=out)
            runtime.run(runner, directory, name, source, messages)
    finally:
        shutil.rmtree(directory, ignore_errors=True)
    print("HyperLab Create view contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
