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


def main() -> int:
    bridge = load_bridge()
    choose_action_cases(bridge)
    ssh_parity_cases(bridge)
    capability_cases(bridge)
    static_cases(bridge)

    if FAILURES:
        for failure in FAILURES:
            print("FAIL:", failure)
        return 1

    print("HyperLab machine-action bridge contract: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
