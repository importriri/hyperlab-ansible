#!/usr/bin/env python3
"""Behavioural contract for the typed machine-operation bridge.

The shell never reconstructs lifecycle rules; it shows what the bridge
answers. So the bridge's own evaluator is what must be right, and it must
agree with what the backend will actually enforce:

  * a managed domain whose spec is unavailable is not an external domain,
    and is never offered direct lifecycle (operations.py refuses it anyway);
  * an unreadable domain is neither managed nor external;
  * only shut-off (or crashed) machines are offered Start -- paused and
    unknown states are named, not treated as startable by elimination;
  * the SSH preflight answers exactly as the real `hyperlabctl open ssh`
    runtime-inventory validator does;
  * connection transports report their own mode, so the shell can track them
    apart from serialized lifecycle operations;
  * a capability answer carries tri-state managed/vfio facts.

The real bridge module is loaded under a non-main name with its CLI calls
replaced by inert fixtures. Nothing here runs hyperlabctl, virsh or a
terminal, and nothing is written outside a temporary directory.
"""

from __future__ import annotations

import importlib.util
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "roles/host_desktop_common/files/privatestack-machine-actions.py"

sys.path.insert(0, str(ROOT / "tools/hyperlabctl"))

from hyperlabctl.commands import open as open_command  # noqa: E402
from hyperlabctl.errors import Unavailable  # noqa: E402

FAILURES: list[str] = []


def check(condition: bool, message: str) -> None:
    if not condition:
        FAILURES.append(message)


def load_bridge():
    spec = importlib.util.spec_from_file_location("hyperlab_machine_bridge", BRIDGE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def outcome(bridge, verb, machine, spec_row):
    try:
        return bridge.choose_action(verb, machine["name"], machine, spec_row)
    except bridge.Refused as exc:
        return "refused: " + str(exc)


SPEC_WINDOWS = {
    "path": "specs/win11.yml",
    "spec": {"name": "win", "looking_glass": True},
    "image": {"os_family": "windows"},
}


def choose_action_cases(bridge) -> None:
    running_managed = {"name": "win", "state": "running", "managed": True, "vfio": True}
    running_external = {"name": "ext", "state": "running", "managed": False, "vfio": False}

    # The finding this contract exists for: managed metadata without a spec.
    for verb in ("start", "shutdown", "reboot", "ssh", "looking-glass", "force-stop"):
        machine = dict(running_managed, state="shut off" if verb == "start" else "running")
        result = outcome(bridge, verb, machine, None)
        check(result.startswith("refused"),
              "managed domain without a spec was offered %s: %s" % (verb, result))
        check("vm.stop" not in result and "vm.start" not in result,
              "managed domain without a spec fell back to direct lifecycle for %s" % verb)

    # An unreadable domain is neither managed nor external.
    unreadable = {"name": "gone", "state": "unknown", "managed": None, "vfio": None}
    check(outcome(bridge, "start", unreadable, None).startswith("refused"),
          "an unknown-state machine was offered Start")
    unreadable_running = dict(unreadable, state="running")
    check(outcome(bridge, "shutdown", unreadable_running, None).startswith("refused"),
          "a machine with unreadable managed status was offered Shutdown")

    # Metadata and spec disagreeing is refused, not resolved by guessing.
    check(outcome(bridge, "shutdown", running_external, SPEC_WINDOWS).startswith("refused"),
          "an external domain with a same-named spec was offered lifecycle")

    # Only shut-off / crashed machines start.
    for state, startable in (("shut off", True), ("crashed", True), ("paused", False),
                             ("in shutdown", False), ("pmsuspended", False),
                             ("unknown", False), ("", False), ("running", False)):
        machine = {"name": "ext", "state": state, "managed": False, "vfio": False}
        result = outcome(bridge, "start", machine, None)
        check((result == "vm.start") == startable,
              "start eligibility for state %r was %s" % (state, result))

    # Valid paths still resolve to the reviewed actions.
    check(outcome(bridge, "shutdown", running_external, None) == "vm.stop",
          "an external running domain lost direct shutdown")
    check(outcome(bridge, "shutdown", running_managed, SPEC_WINDOWS) == "vm.managed-shutdown",
          "a managed running domain lost managed shutdown")
    check(outcome(bridge, "force-stop", running_managed, SPEC_WINDOWS) == "vm.force-stop",
          "a managed VFIO guest lost force stop")
    check(outcome(bridge, "force-stop", dict(running_managed, vfio=False),
                  SPEC_WINDOWS).startswith("refused"),
          "force stop was offered to a non-VFIO guest")
    check(outcome(bridge, "looking-glass", running_managed, SPEC_WINDOWS) == "vm.looking-glass",
          "an approved Windows VFIO guest lost Looking Glass")
    linux = dict(SPEC_WINDOWS, image={"os_family": "linux"},
                 spec={"name": "win", "looking_glass": True})
    check(outcome(bridge, "looking-glass", running_managed, linux).startswith("refused"),
          "an unapproved Linux Looking Glass transport was offered")
    check(outcome(bridge, "console", running_external, None) == "vm.console",
          "console lost for a running domain")

    # Restarting the capture (ADR 0045): a running managed Linux Looking Glass
    # guest only; never Windows, never without VFIO, never a stopped guest.
    linux_lg = dict(SPEC_WINDOWS, image={"os_family": "linux"},
                    spec={"name": "win", "looking_glass": True,
                          "looking_glass_mode": "linux-experimental"})
    check(outcome(bridge, "restart-capture", running_managed, linux_lg) == "vm.looking-glass-restart",
          "a Linux Looking Glass guest cannot restart its capture")
    for label, machine, spec_row in (
        ("Windows", running_managed, SPEC_WINDOWS),
        ("no VFIO", dict(running_managed, vfio=False), linux_lg),
        ("stopped", dict(running_managed, state="shut off"), linux_lg),
        ("external", running_external, None),
        ("no spec", running_managed, None),
        ("Looking Glass off", running_managed,
         dict(linux_lg, spec={"name": "win", "looking_glass": False,
                              "looking_glass_mode": "linux-experimental"})),
    ):
        check(outcome(bridge, "restart-capture", machine, spec_row).startswith("refused"),
              "a capture restart was offered to a %s guest" % label)
    check("restart-capture" not in bridge.DESTRUCTIVE_VERBS
          and "restart-capture" not in bridge.CONNECTION_VERBS,
          "restarting the capture is not a plain foreground operation")
    check(outcome(bridge, "reboot", running_external, None).startswith("refused"),
          "guest reboot was offered to an external domain")


def ssh_parity_cases(bridge) -> None:
    """The bridge and the real open path must agree on every file state."""
    with tempfile.TemporaryDirectory(prefix="hyperlab-ssh-") as runtime:
        previous = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = runtime
        os.chmod(runtime, 0o700)
        try:
            inventory = Path(runtime) / "guest.ini"
            real = Path(runtime) / "real.ini"

            def open_path_accepts() -> bool:
                try:
                    open_command._validate_runtime_inventory(
                        open_command._runtime_inventory_path("guest"), "guest"
                    )
                    return True
                except Unavailable:
                    return False

            # Missing: the open path publishes it, so the bridge must not
            # block it preemptively.
            check(bridge.runtime_ssh_problem("guest") is None,
                  "a missing runtime inventory blocked SSH that the open path would publish")

            inventory.write_text("[guest]\n")
            os.chmod(inventory, 0o600)
            check(open_path_accepts(), "fixture: open path refused a valid inventory")
            check(bridge.runtime_ssh_problem("guest") is None,
                  "a valid runtime inventory was refused by the bridge")

            os.chmod(inventory, 0o644)
            check(not open_path_accepts(), "fixture: open path accepted mode 0644")
            check(bridge.runtime_ssh_problem("guest") is not None,
                  "a world-readable runtime inventory was offered")

            inventory.unlink()
            real.write_text("[guest]\n")
            os.chmod(real, 0o600)
            inventory.symlink_to(real)
            check(not open_path_accepts(), "fixture: open path accepted a symlink")
            check(bridge.runtime_ssh_problem("guest") is not None,
                  "a symlinked runtime inventory was offered")

            inventory.unlink()
            inventory.mkdir()
            check(bridge.runtime_ssh_problem("guest") is not None,
                  "a directory in place of the runtime inventory was offered")
        finally:
            if previous is None:
                os.environ.pop("XDG_RUNTIME_DIR", None)
            else:
                os.environ["XDG_RUNTIME_DIR"] = previous


def capability_cases(bridge) -> None:
    """The real capabilities() answer, with inert inventory fixtures."""
    live_rows = [
        {"name": "win", "state": "running", "managed": True, "vfio": True},
        {"name": "orphan", "state": "running", "managed": True, "vfio": True},
        {"name": "gone", "state": "unknown", "managed": None, "vfio": None},
    ]
    spec_rows = [dict(SPEC_WINDOWS, spec={"name": "win", "looking_glass": True})]

    def fake_cli_json(*args):
        if args[:2] == ("vm", "list"):
            return live_rows
        if args[:2] == ("compose", "list"):
            return spec_rows
        if args[:2] == ("actions", "--resolve"):
            return ["/usr/local/bin/hyperlabctl", "noop"]
        raise AssertionError("unexpected hyperlabctl call %r" % (args,))

    bridge.cli_json = fake_cli_json

    with tempfile.TemporaryDirectory(prefix="hyperlab-ssh-") as runtime:
        previous = os.environ.get("XDG_RUNTIME_DIR")
        os.environ["XDG_RUNTIME_DIR"] = runtime
        os.chmod(runtime, 0o700)
        try:
            answer = bridge.capabilities("win")
            check(answer["phase"] == "capabilities", "capabilities lost its phase")
            check(answer["machine"]["name"] == "win",
                  "capabilities did not name the machine it answered for")
            check(answer["machine"]["managed"] is True and answer["machine"]["spec"] is True,
                  "managed facts not reported for a managed machine")
            for verb in bridge.VERBS:
                entry = answer["verbs"].get(verb)
                check(isinstance(entry, dict)
                      and isinstance(entry.get("available"), bool)
                      and isinstance(entry.get("reason"), str),
                      "malformed capability entry for %s" % verb)
            check(answer["verbs"]["shutdown"]["available"] is True,
                  "managed shutdown not offered for a running managed machine")
            check(answer["verbs"]["start"]["available"] is False,
                  "start offered for a running machine")

            orphan = bridge.capabilities("orphan")
            for verb in ("shutdown", "reboot", "force-stop", "ssh", "looking-glass"):
                check(orphan["verbs"][verb]["available"] is False,
                      "managed machine without spec offered %s" % verb)
                check(orphan["verbs"][verb]["action_id"] is None,
                      "managed machine without spec resolved an action for %s" % verb)

            gone = bridge.capabilities("gone")
            check(gone["machine"]["managed"] is None and gone["machine"]["vfio"] is None,
                  "unreadable managed/vfio facts were reported as known")
            check(not any(entry["available"] for entry in gone["verbs"].values()),
                  "an unreadable machine was offered an operation")
        finally:
            if previous is None:
                os.environ.pop("XDG_RUNTIME_DIR", None)
            else:
                os.environ["XDG_RUNTIME_DIR"] = previous


def static_cases(bridge) -> None:
    check(set(bridge.CONNECTION_VERBS) == {"console", "ssh", "looking-glass"},
          "connection verbs changed without the shell following")
    source = BRIDGE.read_text(encoding="utf-8")
    check('"connection" if verb in CONNECTION_VERBS' in source,
          "connections no longer report their own mode")


CREATE_PLAN = {
    "schema": 1,
    "templates": [
        {"id": "server-debian", "creatable": True, "blocked_reason": "",
         "lifecycles": ["permanent", "disposable"],
         "network_profiles": ["dev", "services", "lab"], "resource_profiles": ["balanced", "custom"],
         "custom": {"memory_mb_min": 2048, "vcpus_min": 1, "vcpus_max": 8, "disk_gib_min": 3},
         "looking_glass_mode": "disabled"},
        {"id": "workstation-dev", "creatable": True, "blocked_reason": "",
         "lifecycles": ["permanent"],
         "network_profiles": ["dev"], "resource_profiles": ["balanced", "performance", "custom"],
         "custom": {"memory_mb_min": 4096, "vcpus_min": 1, "vcpus_max": 8, "disk_gib_min": 100},
         "looking_glass_mode": "linux-experimental"},
        {"id": "workstation-unreviewed", "creatable": False,
         "blocked_reason": "no reviewed profile playbook for this Template",
         "lifecycles": ["permanent"],
         "network_profiles": ["dev"], "resource_profiles": ["balanced"], "custom": None,
         "looking_glass_mode": "linux-experimental"},
    ],
}


def creation_cases(bridge) -> None:
    calls: list[tuple[str, ...]] = []
    launched: list[tuple[str, str]] = []

    def fake_cli(*args):
        calls.append(args)
        if args == ("machine", "create-plan"):
            return CREATE_PLAN
        if args[:2] == ("machine", "create"):
            return {"record_path": "/state/x.yml", "machine": {"id": args[3]}}
        if args[:2] == ("machine", "project"):
            return {"machine": args[2], "spec": f"vm-specs/.generated/{args[2]}.yml"}
        raise AssertionError("unexpected hyperlabctl call %r" % (args,))

    bridge.cli_json = fake_cli
    bridge.privileged = lambda action, name: launched.append((action, name))

    def attempt(*args):
        calls.clear()
        launched.clear()
        try:
            bridge.create(list(args))
        except bridge.Refused as exc:
            return "refused: " + str(exc)
        return "launched"

    check(attempt("server-debian", "srv-deb-02", "disposable", "services", "balanced") == "launched",
          "a valid server request was not launched")
    check(calls[1] == ("machine", "create", "server-debian", "srv-deb-02", "--lifecycle", "disposable",
                       "--network-profile", "services", "--resource-profile", "balanced"),
          "the factory got a different request: %r" % (calls[1:2],))
    check(calls[2] == ("machine", "project", "srv-deb-02"), "the Machine was not projected")
    check(launched == [("machine.provision", "srv-deb-02")],
          "provisioning not handed to the reviewed runner: %r" % launched)

    check(attempt("workstation-dev", "dev-02", "permanent", "dev", "custom", "8192", "4", "120") == "launched",
          "a valid custom workstation request was refused")
    check(calls[1][10:16] == ("--memory-mb", "8192", "--vcpus", "4", "--disk-gib", "120"),
          "custom values lost: %r" % (calls[1],))
    check(calls[1][-2:] == ("--looking-glass-mode", "linux-experimental"),
          "the Template's Looking Glass mode was not applied")

    refusals = {
        ("server-debian", "Srv", "permanent", "dev", "balanced"): "the name",
        ("server-debian", "x", "permanent", "dev", "balanced"): "the name",
        ("server-debian", "srv-a", "permanent", "clean", "balanced"): "network",
        ("server-debian", "srv-a", "permanent", "dev", "performance"): "resource profile",
        ("server-debian", "srv-a", "permanent", "dev", "balanced", "1", "1", "1"): "only custom",
        ("server-debian", "srv-a", "permanent", "dev", "custom"): "custom resources",
        ("server-debian", "srv-a", "permanent", "dev", "custom", "1024", "2", "16"): "memory must be",
        ("server-debian", "srv-a", "permanent", "dev", "custom", "2048", "9", "16"): "vCPUs must be",
        ("server-debian", "srv-a", "permanent", "dev", "custom", "2048", "2", "2"): "disk must be",
        ("server-debian", "srv-a", "permanent", "dev", "custom", "2048", "0", "16"): "custom resources",
        ("server-debian", "srv-a", "permanent", "dev", "custom", "2048", "-2", "16"): "custom resources",
        ("workstation-unreviewed", "dev-03", "permanent", "dev", "balanced"): "no reviewed profile playbook",
        ("missing", "srv-a", "permanent", "dev", "balanced"): "unknown",
        ("--repo=/tmp", "srv-a", "permanent", "dev", "balanced"): "invalid creation request",
        ("server-debian", "srv-a", "permanent", "dev"): "usage",
        ("workstation-dev", "dev-04", "disposable", "dev", "balanced"): "lifecycle",
    }
    for args, reason in refusals.items():
        result = attempt(*args)
        check(result.startswith("refused") and reason in result,
              "creation %r: expected refusal mentioning %r, got %r" % (args, reason, result))
        check(not any(call[:2] in (("machine", "create"), ("machine", "project")) for call in calls)
              and not launched, "a refused request reached the factory or the runner: %r" % (args,))

    source = BRIDGE.read_text(encoding="utf-8")
    check("password" not in source.lower(), "the bridge handles a password")


def workbench_cases(bridge) -> None:
    registry = {"available": True, "errors": ["bad.json: invalid state or profile"], "candidates": [
        {"domain": "arch-dev", "image_id": "arch-dev-standard", "base_image": "arch",
         "profile": "dev", "state": "candidate", "adopted_at": "", "sha256": None},
        {"domain": "arch-old", "image_id": "arch-old-1", "base_image": "arch",
         "profile": "dev", "state": "captured", "adopted_at": "", "sha256": "a" * 64},
        {"domain": "gone-01", "image_id": "gone-1", "base_image": "arch",
         "profile": "dev", "state": "candidate", "adopted_at": "", "sha256": None},
    ]}
    live = [{"name": "arch-dev", "state": "shut off"}, {"name": "arch-old", "state": "running"},
            {"name": "dev-01", "state": "running"}]
    launched: list[tuple[str, str]] = []

    def fake_cli(*args):
        if args == ("workbench", "list"):
            return registry
        if args == ("vm", "list"):
            return live
        raise AssertionError("unexpected hyperlabctl call %r" % (args,))

    bridge.cli_json = fake_cli
    bridge.privileged = lambda action, name: launched.append((action, name))

    payload = bridge.workbench()
    check(payload["phase"] == "workbench" and payload["available"] is True, "Workbench payload shape")
    runtime = {row["domain"]: row["runtime"] for row in payload["candidates"]}
    check(runtime == {"arch-dev": "shut off", "arch-old": "running", "gone-01": "missing"},
          "candidates not joined with live state: %r" % runtime)
    check("dev-01" not in runtime, "a product Machine was listed in the Workbench")
    check(payload["errors"] == registry["errors"], "refused registry records were hidden")

    bridge.seal("arch-dev")
    check(launched == [("workbench.seal", "arch-dev")], "a shut-off candidate was not sealed: %r" % launched)
    for name, reason in (("dev-01", "not a Workbench candidate"),
                         ("arch-old", "already captured"),
                         ("gone-01", "not uniquely present")):
        launched.clear()
        try:
            bridge.seal(name)
            result = "launched"
        except bridge.Refused as exc:
            result = str(exc)
        check(reason in result and not launched, "seal %s: expected %r, got %r" % (name, reason, result))
    live[0]["state"] = "running"
    launched.clear()
    try:
        bridge.seal("arch-dev")
        result = "launched"
    except bridge.Refused as exc:
        result = str(exc)
    check("shut the candidate down" in result and not launched, "a running candidate was sealed")


def main() -> int:
    bridge = load_bridge()
    choose_action_cases(bridge)
    ssh_parity_cases(bridge)
    capability_cases(bridge)
    static_cases(bridge)
    creation_cases(bridge)
    workbench_cases(bridge)

    if FAILURES:
        for failure in FAILURES:
            print("FAIL:", failure)
        return 1

    print("HyperLab machine-action bridge contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
