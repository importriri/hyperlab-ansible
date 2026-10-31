"""Guest fullscreen receipts, replay, identity, completion and recovery.

The compositor is a file-backed transport fixture. Every transaction still runs
production's embedded Python in a real subprocess, with its real durable files.
"""

from __future__ import annotations

import ast
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from contextlib import ExitStack, contextmanager, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from typing import Callable, Iterator
from unittest.mock import patch

from harness import check, equals
from hyperlabctl.commands import vm
from hyperlabctl.errors import Unavailable


# Only fault injection needs source anchors. Never silently run an unmodified
# transaction after an anchor changes; all replacements go through _inject.
POINTS = {
    "imports": "OP_RE = re.compile",
    "prepare": "        session = select_session()\n",
    "prepared": '        current_phase = "prepared"\n\n    # Prepared replay',
    "prelaunch": "    try:\n        remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n",
    "dispatching": '    current_phase = "dispatching"\n',
    "budget": "        dispatch_timeout = remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n",
    "returned": "    except subprocess.TimeoutExpired:\n",
    "dispatched": '    current_phase = "dispatched"\n',
    "lock_wait": "    except BlockingIOError:\n",
    "command_return": (
        "    except subprocess.TimeoutExpired as exc:\n"
        "        if time.monotonic() >= transaction_deadline:\n"
        '            raise TxnFailure("TRANSACTION_DEADLINE_EXCEEDED") from exc\n'
        '        raise TxnFailure(failure_code + "_TIMEOUT") from exc\n'
    ),
    "rollback": (
        '        record["phase"] = "prepared"\n'
        "        replace_json(operation_path, record)\n"
        '        current_phase = "prepared"\n'
        "        finalize_failure(record, exc.code)\n"
    ),
}


def _inject(source: str, target: str, replacement: str) -> str:
    count = source.count(target)
    if count != 1:
        raise AssertionError("fault target must be unique: found %d: %r" % (count, target))
    result = source.replace(target, replacement, 1)
    compile(result, "<fullscreen-fault>", "exec")
    return result


def _at(source: str, point: str, addition: str, *, before: bool = False) -> str:
    target = POINTS[point]
    return _inject(source, target, addition + target if before else target + addition)


def _source() -> str:
    return vm._GUEST_FULLSCREEN_TRANSACTION


def _clock(source: str) -> str:
    return _inject(
        source, "import time\n", """import time
class _FixtureClock:
    now = 100.0
    def monotonic(self):
        return self.now
    def __getattr__(self, name):
        return getattr(_real_time, name)
_real_time = time
time = _FixtureClock()
""",
    )


def _slow_start(source: str, seconds: float) -> str:
    return _inject(
        source, "from __future__ import annotations\n",
        "from __future__ import annotations\nimport time as _startup\n_startup.sleep(%r)\n" % seconds,
    )


COMPOSITOR = r'''#!/usr/bin/env python3
import json
import os
import pathlib
import re
import signal
import sys
import time

root = pathlib.Path(os.environ["HL_FULLSCREEN_ROOT"])
def read(name):
    return (root / name).read_text().strip()
def write(name, value):
    (root / name).write_text(str(value))
def append(name, value):
    with (root / name).open("a") as handle:
        handle.write(value + "\n")
def wait(name):
    deadline = time.monotonic() + 20
    while not (root / name).exists():
        if time.monotonic() >= deadline:
            raise SystemExit(90)
        time.sleep(0.01)

args = sys.argv[1:]
behavior = read("behavior")
if args == ["instances", "-j"]:
    exact = {"pid": int(read("pid")), "instance": read("instance"), "wl_socket": read("socket")}
    mode = read("inventory")
    if mode == "malformed":
        payload = [exact, {"pid": exact["pid"]}]
    elif mode == "duplicate":
        payload = [exact, exact]
    elif mode == "mixed":
        payload = [exact, dict(exact, wl_socket=exact["wl_socket"] + "-conflict")]
    elif mode == "replacement":
        payload = [dict(exact, instance="replacement", wl_socket="replacement")]
    elif mode == "omit":
        payload = []
    elif mode == "normal":
        payload = [exact]
    else:
        raise SystemExit(91)
    print(json.dumps(payload))
    raise SystemExit(0)

window = {"address": "0xabc", "stableId": read("stable"), "fullscreen": int(read("state"))}
if args == ["activewindow", "-j"]:
    append("active-calls", "1")
    if behavior == "active_forbidden":
        raise SystemExit(9)
    print(json.dumps(window))
    raise SystemExit(0)

if args == ["clients", "-j"]:
    if behavior == "query_fail":
        raise SystemExit(9)
    if behavior == "slow_query":
        wait("never-release")
    if behavior == "state_flip":
        window["fullscreen"] = 0
    print(json.dumps([] if behavior == "target_missing" else [window]))
    raise SystemExit(0)

if len(args) != 2 or args[0] != "dispatch":
    raise SystemExit(22)
expression = args[1]
append("dispatches", expression)
write("dispatch-ready", "ready")
# Parse the selector the transport actually received, including the unsafe
# address selector used by the identity mutation. The fixture must expose a
# mutation's effect rather than reject it for an unrelated fake-only rule.
match = re.fullmatch(r'hl\.dsp\.window\.fullscreen\(\{ mode = "fullscreen", action = "(set|unset|toggle)", window = "(stableid|address):([0-9a-fA-Fx]+)" \}\)', expression)
if not match:
    raise SystemExit(20)
action, selector, identity = match.groups()
if behavior == "reuse_before_dispatch":
    write("stable", "18000002")
if identity != (read("stable") if selector == "stableid" else "0xabc"):
    raise SystemExit(4)
if behavior == "toggle_race":
    write("state", 2)
mode = int(read("state"))
desired = action == "set" or (action == "toggle" and mode not in (2, 3))
new_mode = (mode | 2) if desired else (mode & 1)
if behavior in ("signal_delayed", "nonzero_delayed", "timeout_delayed"):
    if behavior == "signal_delayed":
        os.kill(os.getpid(), signal.SIGKILL)
    if behavior == "nonzero_delayed":
        raise SystemExit(4)
    wait("never-release")
if behavior == "hold_sync":
    wait("sync-release")
if behavior == "zero_delay":
    time.sleep(0.05)
if behavior not in ("complete_noapply", "ack_noapply_query_fail"):
    write("state", new_mode)
if behavior in ("apply_query_fail", "ack_noapply_query_fail"):
    write("behavior", "query_fail")
if behavior == "apply_nonzero":
    raise SystemExit(7)
if behavior == "timeout_applied":
    wait("never-release")
print("ok")
'''


DELAYED_APPLY = '''import pathlib, sys, time
root = pathlib.Path(sys.argv[1])
deadline = time.monotonic() + 20
while not (root / "late-release").exists():
    if time.monotonic() >= deadline:
        raise SystemExit(90)
    time.sleep(0.01)
(root / "state").write_text("2")
(root / "late-applied").write_text("done")
'''


class Guest:
    """Own files and every child until after transaction/recovery assertions."""

    def __init__(self, mode: int = 0, behavior: str = "normal") -> None:
        self.mode = mode
        self.behavior = behavior
        self.children: list[subprocess.Popen] = []
        self.stack = ExitStack()

    def __enter__(self) -> Guest:
        try:
            self.root = Path(self.stack.enter_context(tempfile.TemporaryDirectory(prefix="hyperlab-fs-")))
            self.runtime = self.root / "runtime"
            self.runtime.mkdir(mode=0o700)
            self.base = self.runtime / "hyperlab-fullscreen"
            self.bin = self.root / "bin"
            self.bin.mkdir()
            for name, value in {
                "state": self.mode, "behavior": self.behavior, "stable": "18000001",
                "instance": "instance-a", "socket": "wayland-a", "pid": os.getpid(),
                "inventory": "normal", "dispatches": "", "active-calls": "",
            }.items():
                self.write(name, value)
            self.executable("hyprctl", COMPOSITOR)
            self.executable("pgrep", '#!/bin/sh\ncat -- "$HL_FULLSCREEN_ROOT/pid"\n')
            # A small explicit environment also isolates tests from real sessions.
            self.env = {
                "PATH": str(self.bin) + os.pathsep + "/usr/bin:/bin",
                "XDG_RUNTIME_DIR": str(self.runtime),
                "HL_FULLSCREEN_ROOT": str(self.root),
                "PYTHONDONTWRITEBYTECODE": "1",
            }
            if self.behavior in ("signal_delayed", "nonzero_delayed", "timeout_delayed"):
                self.worker = self.start(DELAYED_APPLY, [str(self.root)])
        except BaseException:
            self.__exit__(*sys.exc_info())
            raise
        return self

    def __exit__(self, *_exc: object) -> None:
        try:
            for child in reversed(self.children):
                _reap(child)
        finally:
            self.stack.close()

    def executable(self, name: str, source: str) -> None:
        path = self.bin / name
        path.write_text(source, encoding="utf-8")
        path.chmod(0o700)

    def write(self, name: str, value: object) -> None:
        (self.root / name).write_text(str(value), encoding="utf-8")

    def read(self, name: str) -> str:
        return (self.root / name).read_text(encoding="utf-8").strip()

    @property
    def dispatches(self) -> list[str]:
        return self.read("dispatches").splitlines()

    def wait(self, name: str) -> None:
        deadline = time.monotonic() + 10.0
        while not (self.root / name).exists():
            if time.monotonic() >= deadline:
                raise AssertionError("fixture handshake not reached: " + name)
            time.sleep(0.01)

    def start(self, source: str, args: list[str]) -> subprocess.Popen:
        child = subprocess.Popen(
            [sys.executable, "-c", source, *args], env=self.env, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True,
        )
        self.children.append(child)
        return child

    def launch(self, operation_id: str, requested: str, source: str | None = None) -> subprocess.Popen:
        return self.start(_source() if source is None else source, [operation_id, requested])

    def finish(self, child: subprocess.Popen) -> subprocess.CompletedProcess:
        stdout, stderr = child.communicate(timeout=10.0)
        return subprocess.CompletedProcess(child.args, child.returncode, stdout, stderr)

    def run(self, operation_id: str, requested: str, source: str | None = None) -> subprocess.CompletedProcess:
        return self.finish(self.launch(operation_id, requested, source))

    def late_apply(self) -> None:
        self.write("late-release", "release")
        self.wait("late-applied")
        result = self.finish(self.worker)
        equals("late_worker_reaped", result.returncode, 0)

    def paths(self, operation_id: str) -> tuple[Path, Path]:
        return (self.base / "receipts" / (operation_id + ".json"),
                self.base / "operations" / (operation_id + ".json"))

    def seed(self, operation_id: str, requested: str = "on", phase: str = "prepared") -> Path:
        receipt, operation = self.paths(operation_id)
        for directory in (self.base, receipt.parent, operation.parent):
            directory.mkdir(mode=0o700, exist_ok=True)
        payload = {
            "operation_id": operation_id, "phase": phase, "requested": requested,
            "address": "0xabc", "stable_id": "18000001", "before_mode": 0,
            "desired": 1, "requires_dispatch": 1, "hyprland_pid": int(self.read("pid")),
            "instance": "instance-a", "wl_socket": "wayland-a", "dispatch_rc": None,
        }
        operation.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        operation.chmod(0o600)
        return operation


def _reap(child: subprocess.Popen) -> None:
    if child.poll() is None:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    child.communicate(timeout=10.0)


def _receipt(**fields: object) -> str:
    payload = {
        "operation_id": "a" * 32, "status": "success", "address": "0xabc",
        "before_mode": 0, "after_mode": 2, "requested": "toggle", "desired": 1,
        "transition_required": 1, "failure": None,
    }
    payload.update(fields)
    return json.dumps(payload) + "\n"


def _terminal(result: subprocess.CompletedProcess, operation_id: str, requested: str,
              *, rc: int = 0) -> dict:
    equals("terminal_rc", result.returncode, rc)
    payload = vm._parse_fullscreen_receipt(result.stdout, operation_id, requested)
    equals("terminal_status", payload["status"], "success" if rc == 0 else "failure")
    return payload


def _unknown(result: subprocess.CompletedProcess, operation_id: str) -> dict:
    equals("unknown_rc", result.returncode, 75)
    return vm._parse_fullscreen_unknown(result.stdout, operation_id)


def _recovery(guest: Guest, operation_id: str) -> dict:
    result = guest.run(operation_id, "recover")
    equals("recovery_transport", result.returncode, 0)
    return vm._parse_fullscreen_recovery(result.stdout, operation_id)


def _unavailable(name: str, callback: Callable, contains: str | None = None) -> None:
    try:
        callback()
    except Unavailable as error:
        check(name, True)
        if contains is not None:
            check(name + "_reason", contains in str(error), str(error))
    else:
        check(name, False, "expected Unavailable")


def _result(rc: int = 0, stdout: str = "") -> SimpleNamespace:
    return SimpleNamespace(returncode=rc, stdout=stdout, stderr="")


@contextmanager
def _runtime(run: Callable, read: Callable | None = None) -> Iterator[None]:
    with ExitStack() as stack:
        for name, value in {
            "_require_running_domain": lambda *_args: None,
            "_ssh_argv": lambda *_args: ["ssh", "demo@example.invalid"],
            "_wait_for_ssh_ready": lambda *_args: None,
            "_run_fullscreen_remote": run,
            "_run_fullscreen_receipt_remote": read or (lambda *_args: _result(44)),
            "_GUEST_FULLSCREEN_RECEIPT_RECONCILE_SECONDS": 0.02,
            "_GUEST_FULLSCREEN_RECEIPT_POLL_SECONDS": 0.001,
        }.items():
            stack.enter_context(patch.object(vm, name, value))
        stack.enter_context(patch.object(vm.secrets, "token_hex", lambda _size: "a" * 32))
        yield


def _invoke(run: Callable, state: str = "toggle", read: Callable | None = None,
            recover: str | None = None) -> tuple[int, dict]:
    output = io.StringIO()
    with _runtime(run, read), redirect_stdout(output):
        rc = vm.VmCommand()._guest_fullscreen(
            SimpleNamespace(domain="demo", state=state, recover_operation=recover), object(),
        )
    return rc, json.loads(output.getvalue())


def test_discovery_owns_fullscreen_scenarios() -> None:
    path = Path(__file__)
    family = sorted(item.name for item in path.parent.glob("test_vm_guest_fullscreen*.py"))
    equals("fullscreen_single_discovery_owner", family, [path.name])
    tree = ast.parse(path.read_text())
    names = [node.name for node in tree.body if isinstance(node, ast.FunctionDef)
             and node.name.startswith("test_")]
    equals("fullscreen_no_shadowed_tests", len(names), len(set(names)))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            check("fullscreen_no_version_import", not (node.module or "").startswith(
                "test_vm_guest_fullscreen_v"))


def test_fault_injection_requires_one_target() -> None:
    for label, source in (("missing", "x = 0\n"), ("ambiguous", "pass\npass\n")):
        try:
            _inject(source, "pass\n", "raise RuntimeError\n")
        except AssertionError as error:
            check("fault_target_" + label, str(error).startswith("fault target must be unique"))
        else:
            check("fault_target_" + label, False, "invalid fault target accepted")
    equals("fault_target_positive", _inject("pass\n", "pass", "x = 1"), "x = 1\n")


def test_fixture_cleanup_after_assertion() -> None:
    child = None
    try:
        try:
            with Guest() as guest:
                root = guest.root
                child = guest.start("import time; time.sleep(30)", [])
                raise AssertionError("fixture cleanup control")
        except AssertionError as error:
            equals("cleanup_expected_assertion", str(error), "fixture cleanup control")
        check("cleanup_child_reaped", child.returncode is not None)
        check("cleanup_files_removed", not root.exists())
    finally:
        if child is not None:
            _reap(child)


def test_runtime_patch_cleanup_after_assertion() -> None:
    names = ("_require_running_domain", "_ssh_argv", "_wait_for_ssh_ready",
             "_run_fullscreen_remote", "_run_fullscreen_receipt_remote",
             "_GUEST_FULLSCREEN_RECEIPT_RECONCILE_SECONDS", "_GUEST_FULLSCREEN_RECEIPT_POLL_SECONDS")
    original = {name: getattr(vm, name) for name in names}
    token = vm.secrets.token_hex
    try:
        try:
            with _runtime(lambda *_args: None):
                raise AssertionError("patch cleanup control")
        except AssertionError as error:
            equals("patch_expected_assertion", str(error), "patch cleanup control")
        for name, value in original.items():
            check("patch_restored_" + name, getattr(vm, name) is value)
        check("patch_restored_token", vm.secrets.token_hex is token)
    finally:
        for name, value in original.items():
            setattr(vm, name, value)
        vm.secrets.token_hex = token


def test_cli_accepts_exact_terminal_receipt() -> None:
    def run(_argv: list[str], operation_id: str, requested: str, _timeout: float) -> SimpleNamespace:
        equals("cli_operation_id", operation_id, "a" * 32)
        equals("cli_requested", requested, "toggle")
        return _result(stdout=_receipt())
    rc, payload = _invoke(run)
    equals("cli_success_rc", rc, 0)
    equals("cli_not_reconciled", payload["reconciled"], 0)
    equals("cli_mode_preserved", payload["after_mode"], 2)


def _transport_timeout(*_args: object) -> None:
    raise subprocess.TimeoutExpired("fixture-ssh", 1)


def test_cli_reconciles_timeout_only_with_exact_receipt() -> None:
    def read(_argv: list[str], operation_id: str, _timeout: float) -> SimpleNamespace:
        return _result(stdout=_receipt(operation_id=operation_id, before_mode=1, after_mode=3, requested="on"))
    rc, payload = _invoke(_transport_timeout, "on", read)
    equals("timeout_receipt_rc", rc, 0)
    equals("timeout_reconciled", payload["reconciled"], 1)
    equals("timeout_preserves_maximized", payload["after_mode"], 3)
    _unavailable("timeout_without_receipt_unknown", lambda: _invoke(_transport_timeout), "UNKNOWN")
    failure = _receipt(status="failure", address=None, before_mode=None, after_mode=None,
                       desired=None, transition_required=None, failure="LOCK_BUSY")
    _unavailable("terminal_failure_refused",
                 lambda: _invoke(lambda *_args: _result(2), read=lambda *_args: _result(stdout=failure)),
                 "LOCK_BUSY")


def test_terminal_receipt_refusals() -> None:
    cases = [
        ("null", "null\n", "toggle"), ("array", "[]\n", "toggle"),
        ("number", "1\n", "toggle"), ("string", '"value"\n', "toggle"),
        ("invalid_json", "{\n", "toggle"), ("empty", "", "toggle"),
        ("two_envelopes", _receipt() + _receipt(), "toggle"),
        ("wrong_operation", _receipt(operation_id="b" * 32), "toggle"),
        ("extra_field", _receipt(extra="not allowed"), "toggle"),
        ("boolean_mode", _receipt(before_mode=True), "toggle"),
        ("maximized_is_not_fullscreen", _receipt(after_mode=1, requested="on"), "on"),
    ]
    for label, requested, before, after, desired in (
        ("on_contradiction", "on", 0, 0, 0),
        ("off_contradiction", "off", 2, 2, 1),
        ("toggle_contradiction", "toggle", 0, 0, 0),
    ):
        cases.append((label, _receipt(requested=requested, before_mode=before, after_mode=after,
                                      desired=desired, transition_required=0), requested))
    for label, raw, requested in cases:
        _unavailable("terminal_receipt_" + label,
                     lambda raw=raw, requested=requested: vm._parse_fullscreen_receipt(raw, "a" * 32, requested))
    for mode, expected in ((1, False), (2, True), (3, True)):
        equals("true_fullscreen_mode_%d" % mode, vm._is_true_fullscreen(mode), expected)


def test_unknown_and_recovery_envelopes_refuse_contradictions() -> None:
    operation_id = "a" * 32
    base = {"operation_id": operation_id, "status": "unknown", "reason": "TEST",
            "blocking_operation_id": "b" * 32}
    for label, payload in (
        ("wrong_operation", dict(base, operation_id="c" * 32)),
        ("invalid_blocker", dict(base, blocking_operation_id="not-an-operation")),
    ):
        _unavailable("unknown_" + label,
                     lambda payload=payload: vm._parse_fullscreen_unknown(json.dumps(payload), operation_id))
    success = json.loads(_receipt(requested="on"))
    failure = dict(success, status="failure", after_mode=None, failure="POST_DISPATCH_QUERY_FAILED")
    for kind, receipt in (("completed", failure), ("retired", success)):
        payload = {"operation_id": operation_id, "recovery": kind, "receipt": receipt, "reason": None}
        _unavailable("recovery_contradiction_" + kind,
                     lambda payload=payload: vm._parse_fullscreen_recovery(json.dumps(payload), operation_id))


def test_cli_surfaces_blocker_and_explicit_recovery() -> None:
    blocker = "b" * 32
    recovery = {"operation_id": blocker, "recovery": "completed", "reason": None,
                "receipt": json.loads(_receipt(operation_id=blocker, requested="on"))}
    def run(_argv: list[str], operation_id: str, requested: str, _timeout: float) -> SimpleNamespace:
        if requested == "recover":
            equals("cli_recovery_exact_id", operation_id, blocker)
            return _result(stdout=json.dumps(recovery))
        equals("cli_new_operation", operation_id, "a" * 32)
        equals("cli_on_request", requested, "on")
        return _result(75, json.dumps({"operation_id": operation_id, "status": "unknown",
                       "reason": "PREVIOUS_OPERATION_RECOVERY_REQUIRED", "blocking_operation_id": blocker}))
    rc, payload = _invoke(run, "on")
    equals("cli_unknown_rc", rc, 2)
    equals("cli_blocker", payload["blocking_operation_id"], blocker)
    equals("cli_unknown_reason", payload["reason"], "PREVIOUS_OPERATION_RECOVERY_REQUIRED")
    rc, payload = _invoke(run, recover=blocker)
    equals("cli_recovery_rc", rc, 0)
    equals("cli_recovery_payload", payload, recovery)


def test_late_host_reconciliation_rejects_success() -> None:
    now = [10.0]
    timeouts = []
    def late_read(_argv: list[str], _op: str, timeout: float) -> SimpleNamespace:
        timeouts.append(timeout)
        now[0] += 0.03
        return _result(stdout=_receipt(requested="on"))
    clock = SimpleNamespace(monotonic=lambda: now[0], sleep=lambda _n: None)
    with (_runtime(lambda *_args: None, late_read), patch.object(vm, "time", clock),
          patch.object(vm, "_GUEST_FULLSCREEN_RECEIPT_RECONCILE_SECONDS", 0.01)):
        _unavailable("late_receipt_refused", lambda: vm._reconcile_fullscreen_receipt(
            ["ssh", "fixture"], "demo", "a" * 32, "on", "test"))
    check("host_timeout_has_no_floor", bool(timeouts) and 0 < timeouts[0] <= 0.011, repr(timeouts))


def test_successful_modes_and_no_dispatch_controls() -> None:
    for label, before, request, after, dispatches, action in (
        ("set_from_maximized", 1, "on", 3, 1, "set"),
        ("unset_keeps_maximized", 3, "off", 1, 1, "unset"),
        ("toggle_on", 0, "toggle", 2, 1, "set"),
        ("toggle_off", 2, "toggle", 0, 1, "unset"),
        ("already_on", 2, "on", 2, 0, None),
        ("already_off", 1, "off", 1, 0, None),
    ):
        with Guest(before) as guest:
            operation_id = "c" * 32
            payload = _terminal(guest.run(operation_id, request), operation_id, request)
            equals(label + "_before", payload["before_mode"], before)
            equals(label + "_after", payload["after_mode"], after)
            equals(label + "_state", int(guest.read("state")), after)
            equals(label + "_dispatches", len(guest.dispatches), dispatches)
            if action:
                expression = guest.dispatches[0]
                check(label + "_stable_selector", 'window = "stableid:18000001"' in expression)
                check(label + "_explicit_action", 'action = "%s"' % action in expression)
                check(label + "_fullscreen", 'mode = "fullscreen"' in expression)
                check(label + "_no_focus", "focuswindow" not in expression)


def test_sequential_replay_dispatches_once() -> None:
    with Guest() as guest:
        operation_id = "e" * 32
        first = guest.run(operation_id, "toggle")
        replay = guest.run(operation_id, "toggle")
        equals("sequential_dispatches", len(guest.dispatches), 1)
        _terminal(first, operation_id, "toggle")
        _terminal(replay, operation_id, "toggle")
        equals("sequential_same_receipt", replay.stdout, first.stdout)
        equals("sequential_state", int(guest.read("state")), 2)


def _concurrent_case(same_id: bool) -> None:
    with Guest(behavior="hold_sync") as guest:
        first_id = "f" * 32
        second_id = first_id if same_id else "1" * 32
        first = guest.launch(first_id, "toggle" if same_id else "on")
        guest.wait("dispatch-ready")
        # Visible convergence alone must not let an opposite request overtake
        # a compositor call that is still outstanding.
        if not same_id:
            guest.write("state", 2)
        guest.write("behavior", "normal")
        source = _at(_source(), "lock_wait",
                     '        (runtime.parent / "lock-waiting").write_text("waiting")\n')
        second = guest.launch(second_id, "toggle" if same_id else "off", source)
        guest.wait("lock-waiting")
        check("concurrent_second_waits", second.poll() is None)
        equals("concurrent_first_only_dispatch", len(guest.dispatches), 1)
        guest.write("sync-release", "release")
        first_result, second_result = guest.finish(first), guest.finish(second)
        equals("concurrent_first_rc", first_result.returncode, 0)
        equals("concurrent_second_rc", second_result.returncode, 0)
        equals("concurrent_first_stderr", first_result.stderr, "")
        equals("concurrent_second_stderr", second_result.stderr, "")
        if same_id:
            equals("concurrent_same_receipt", second_result.stdout, first_result.stdout)
            equals("concurrent_dispatches", len(guest.dispatches), 1)
            equals("concurrent_state", int(guest.read("state")), 2)
        else:
            payload = _terminal(second_result, second_id, "off")
            equals("ordered_before", payload["before_mode"], 2)
            equals("ordered_desired", payload["desired"], 0)
            equals("ordered_transition", payload["transition_required"], 1)
            equals("ordered_after", payload["after_mode"], 0)
            equals("ordered_dispatches", len(guest.dispatches), 2)
            equals("ordered_final_state", int(guest.read("state")), 0)


def test_concurrent_replay_dispatches_once() -> None:
    _concurrent_case(True)


def test_synchronous_completion_orders_opposite_request() -> None:
    _concurrent_case(False)


def test_postdispatch_proof_loss_is_terminal_and_immutable() -> None:
    # Distinct observations after the same immediate proof loss: normal state,
    # a replaced compositor, a reused address, and permanent target loss.
    for label, behavior, later, failure, initial_after in (
        ("applied_query_loss", "apply_query_fail", "normal", "POST_DISPATCH_QUERY_FAILED", 2),
        ("compositor_replaced", "apply_query_fail", "instance", "POST_DISPATCH_QUERY_FAILED", 2),
        ("address_reused", "apply_query_fail", "stable", "POST_DISPATCH_QUERY_FAILED", 2),
        ("target_lost", "apply_query_fail", "target_missing", "POST_DISPATCH_QUERY_FAILED", 2),
        ("ack_without_proof", "ack_noapply_query_fail", "normal", "POST_DISPATCH_QUERY_FAILED", 0),
        ("ack_without_effect", "complete_noapply", "normal", "POST_DISPATCH_STATE_MISMATCH", 0),
    ):
        with Guest(behavior=behavior) as guest:
            operation_id = "7" * 32
            first = guest.run(operation_id, "on")
            payload = _terminal(first, operation_id, "on", rc=2)
            equals(label + "_status", payload["status"], "failure")
            equals(label + "_failure", payload["failure"], failure)
            equals(label + "_state", int(guest.read("state")), initial_after)
            if failure == "POST_DISPATCH_STATE_MISMATCH":
                equals(label + "_before", payload["before_mode"], 0)
                equals(label + "_after", payload["after_mode"], 0)
                equals(label + "_desired", payload["desired"], 1)
            receipt, operation = guest.paths(operation_id)
            check(label + "_receipt", receipt.is_file())
            check(label + "_retired", not operation.exists())
            disk_receipt = receipt.read_bytes()
            early_replay = guest.run(operation_id, "on")
            equals(label + "_early_replay_rc", early_replay.returncode, 2)
            equals(label + "_early_replay_receipt", early_replay.stdout, first.stdout)
            equals(label + "_early_replay_dispatches", len(guest.dispatches), 1)
            guest.write("behavior", "normal")
            if later == "instance":
                guest.write("instance", "instance-new")
                guest.write("socket", "wayland-new")
            elif later == "stable":
                guest.write("stable", "18000002")
            elif later == "target_missing":
                guest.write("behavior", later)
            # Later unrelated convergence cannot retrospectively prove success.
            guest.write("state", 2)
            replay = guest.run(operation_id, "on")
            equals(label + "_replay_rc", replay.returncode, 2)
            equals(label + "_replay_receipt", replay.stdout, first.stdout)
            recovered = _recovery(guest, operation_id)
            equals(label + "_recovery", recovered["recovery"], "retired")
            equals(label + "_recovery_failure", recovered["receipt"]["failure"], failure)
            equals(label + "_immutable_receipt", receipt.read_bytes(), disk_receipt)
            equals(label + "_one_dispatch", len(guest.dispatches), 1)


def test_terminal_failure_allows_new_operation() -> None:
    with Guest(behavior="apply_query_fail") as guest:
        _terminal(guest.run("5" * 32, "on"), "5" * 32, "on", rc=2)
        equals("terminal_failure_applied", int(guest.read("state")), 2)
        equals("terminal_failure_first_dispatch", len(guest.dispatches), 1)
        guest.write("behavior", "normal")
        _terminal(guest.run("6" * 32, "off"), "6" * 32, "off")
        equals("terminal_failure_next_dispatch", len(guest.dispatches), 2)
        equals("terminal_failure_final_state", int(guest.read("state")), 0)


def test_noop_requires_target_and_unchanged_precondition() -> None:
    for behavior, failure in (("target_missing", "TARGET_GONE_PRE_DISPATCH"),
                              ("state_flip", "PREPARED_STATE_DRIFT")):
        with Guest(2, behavior) as guest:
            payload = _terminal(guest.run("9" * 32, "on"), "9" * 32, "on", rc=2)
            equals(behavior + "_failure", payload["failure"], failure)
            equals(behavior + "_no_dispatch", len(guest.dispatches), 0)


def test_uncertain_dispatch_blocks_replay_and_requires_safe_recovery() -> None:
    for label, behavior, reason, applied in (
        ("timeout_after_apply", "timeout_applied", "FULLSCREEN_DISPATCH_TIMEOUT", True),
        ("timeout_before_late_apply", "timeout_delayed", "FULLSCREEN_DISPATCH_TIMEOUT", False),
        ("nonzero_after_apply", "apply_nonzero", "FULLSCREEN_DISPATCH_UNACKNOWLEDGED", True),
        ("nonzero_before_late_apply", "nonzero_delayed", "FULLSCREEN_DISPATCH_UNACKNOWLEDGED", False),
        ("signal_before_late_apply", "signal_delayed", "FULLSCREEN_DISPATCH_SIGNALLED", False),
        ("address_reuse_before_dispatch", "reuse_before_dispatch", "FULLSCREEN_DISPATCH_UNACKNOWLEDGED", False),
    ):
        with Guest(behavior=behavior) as guest:
            operation_id = "b" * 32
            result = guest.run(operation_id, "on")
            equals(label + "_dispatches", len(guest.dispatches), 1)
            equals(label + "_state", int(guest.read("state")), 2 if applied else 0)
            first = _unknown(result, operation_id)
            equals(label + "_reason", first["reason"], reason)
            equals(label + "_blocker", first["blocking_operation_id"], operation_id)
            if behavior == "reuse_before_dispatch":
                equals(label + "_replacement_identity", guest.read("stable"), "18000002")
            receipt, operation = guest.paths(operation_id)
            check(label + "_no_receipt", not receipt.exists())
            check(label + "_barrier", operation.is_file())
            guest.write("behavior", "normal")
            replay = _unknown(guest.run(operation_id, "on"), operation_id)
            equals(label + "_replay_reason", replay["reason"], "OPERATION_STILL_DISPATCHING")
            blocked = _unknown(guest.run("c" * 32, "off"), "c" * 32)
            equals(label + "_next_blocker", blocked["blocking_operation_id"], operation_id)
            equals(label + "_next_reason", blocked["reason"], "PREVIOUS_OPERATION_RECOVERY_REQUIRED")
            equals(label + "_no_second_dispatch", len(guest.dispatches), 1)
            if behavior in ("timeout_delayed", "nonzero_delayed", "signal_delayed"):
                guest.late_apply()
                equals(label + "_late_state", int(guest.read("state")), 2)
            recovery = _recovery(guest, operation_id)
            equals(label + "_same_session", recovery["recovery"], "still-unresolved")
            guest.write("instance", "instance-b")
            conflicting = _recovery(guest, operation_id)
            equals(label + "_tuple_conflict", conflicting["recovery"], "still-unresolved")
            equals(label + "_conflict_reason", conflicting["reason"], "SESSION_DISCOVERY_AMBIGUOUS")
            check(label + "_barrier_after_conflict", operation.exists())
            check(label + "_no_false_receipt", not receipt.exists())
            equals(label + "_no_conflict_dispatch", len(guest.dispatches), 1)
            guest.write("pid", int(guest.read("pid")) + 100000)
            retired = _recovery(guest, operation_id)
            equals(label + "_expired_retired", retired["recovery"], "retired")
            equals(label + "_expired_failure", retired["receipt"]["failure"], "SESSION_EXPIRED")
            check(label + "_barrier_retired", not operation.exists())
            equals(label + "_no_recovery_dispatch", len(guest.dispatches), 1)
            final = _terminal(guest.run("e" * 32, "off"), "e" * 32, "off")
            equals(label + "_post_recovery_after", final["after_mode"], 0)
            equals(label + "_post_recovery_dispatches", len(guest.dispatches), 2 if int(applied) or behavior.endswith("delayed") else 1)


def test_invalid_journals_remain_blocking() -> None:
    for label in ("truncated", "permissions", "oversized"):
        with Guest() as guest:
            blocker_id = "2" * 32
            blocker = guest.seed(blocker_id)
            equals(label + "_valid_seed", json.loads(blocker.read_text())["operation_id"], blocker_id)
            if label == "permissions":
                blocker.chmod(0o644)
            elif label == "truncated":
                blocker.write_text("{", encoding="utf-8")
            else:
                blocker.write_text(blocker.read_text() + " " * 9000, encoding="utf-8")
            blocked = _unknown(guest.run("3" * 32, "on"), "3" * 32)
            equals(label + "_blocker", blocked["blocking_operation_id"], blocker_id)
            equals(label + "_no_dispatch", len(guest.dispatches), 0)
            recovered = _recovery(guest, blocker_id)
            equals(label + "_recovery", recovered["recovery"], "still-unresolved")
            equals(label + "_reason", recovered["reason"], "STATE_FILE_INVALID")
            check(label + "_preserved", blocker.exists())


def test_atomic_journal_publication_and_short_writes() -> None:
    # Crash residue under a hidden name is not a published operation.
    with Guest() as guest:
        operation_id = "1" * 32
        seeded = guest.seed(operation_id)
        seeded.unlink()
        partial = seeded.parent / ("." + operation_id + ".json.crash.tmp")
        partial.write_text("{", encoding="utf-8")
        partial.chmod(0o600)
        source = _at(_source(), "imports", '''_write = os.write
def _short_write(fd, raw):
    return _write(fd, raw[:7])
os.write = _short_write
''', before=True)
        payload = _terminal(guest.run(operation_id, "on", source), operation_id, "on")
        equals("atomic_short_write_success", payload["status"], "success")
        check("atomic_hidden_residue_preserved", partial.exists())
        equals("atomic_dispatches", len(guest.dispatches), 1)
        receipt, operation = guest.paths(operation_id)
        equals("atomic_receipt_payload", json.loads(receipt.read_text()), payload)
        check("atomic_operation_retired", not operation.exists())
    tree = ast.parse(_source())
    create = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "write_new_json")
    calls = [node.func for node in ast.walk(create) if isinstance(node, ast.Call)]
    check("atomic_publish_uses_link", any(isinstance(fn, ast.Attribute) and isinstance(fn.value, ast.Name)
          and fn.value.id == "os" and fn.attr == "link" for fn in calls))


def test_prepared_replay_preserves_binding_and_detects_drift() -> None:
    for drift in (False, True):
        with Guest() as guest:
            operation_id = "5" * 32
            prepared = guest.seed(operation_id, "toggle")
            blocked = _unknown(guest.run("6" * 32, "on"), "6" * 32)
            equals("prepared_blocks_other", blocked["blocking_operation_id"], operation_id)
            check("prepared_not_erased", prepared.exists())
            equals("prepared_other_no_dispatch", len(guest.dispatches), 0)
            guest.write("behavior", "active_forbidden")
            if drift:
                guest.write("state", 2)
            payload = _terminal(guest.run(operation_id, "toggle"), operation_id, "toggle", rc=2 if drift else 0)
            equals("prepared_never_reselects", guest.read("active-calls"), "")
            equals("prepared_dispatches", len(guest.dispatches), 0 if drift else 1)
            check("prepared_retired", not prepared.exists())
            if drift:
                equals("prepared_drift_reason", payload["failure"], "PREPARED_STATE_DRIFT")
            else:
                equals("prepared_replay_after", payload["after_mode"], 2)
                equals("prepared_final_state", int(guest.read("state")), 2)


def test_acknowledgement_requires_synchronous_effect() -> None:
    with Guest(behavior="zero_delay") as guest:
        payload = _terminal(guest.run("8" * 32, "on"), "8" * 32, "on")
        equals("sync_ack_after", payload["after_mode"], 2)
        equals("sync_ack_state", int(guest.read("state")), 2)
        equals("sync_ack_one_dispatch", len(guest.dispatches), 1)
        check("sync_ack_no_barrier", not guest.paths("8" * 32)[1].exists())


def test_toggle_uses_durable_snapshot_despite_dispatch_race() -> None:
    with Guest(behavior="toggle_race") as guest:
        payload = _terminal(guest.run("d" * 32, "toggle"), "d" * 32, "toggle")
        equals("toggle_race_before", payload["before_mode"], 0)
        equals("toggle_race_desired", payload["desired"], 1)
        equals("toggle_race_after", payload["after_mode"], 2)
        equals("toggle_race_state", int(guest.read("state")), 2)
        equals("toggle_race_one_dispatch", len(guest.dispatches), 1)
        check("toggle_snapshot_explicit_set", 'action = "set"' in guest.dispatches[0])


def test_ambiguous_inventory_preserves_dispatching_barrier() -> None:
    for mode in ("malformed", "duplicate", "mixed", "replacement", "omit"):
        with Guest() as guest:
            operation_id = "a" * 32
            operation = guest.seed(operation_id, phase="dispatching")
            guest.write("inventory", mode)
            recovery = _recovery(guest, operation_id)
            equals(mode + "_recovery", recovery["recovery"], "still-unresolved")
            equals(mode + "_reason", recovery["reason"], "SESSION_DISCOVERY_AMBIGUOUS")
            equals(mode + "_receipt", recovery["receipt"], None)
            check(mode + "_barrier", operation.exists())
            check(mode + "_no_receipt", not guest.paths(operation_id)[0].exists())
            equals(mode + "_no_dispatch", len(guest.dispatches), 0)


def test_crash_after_apply_before_completion_never_redispatches() -> None:
    with Guest() as guest:
        operation_id = "7" * 32
        # Kill the real transaction after its child was reaped, before the
        # completion fence. This also avoids leaving an orphan compositor.
        source = _at(_source(), "returned", "        os.kill(os.getpid(), 9)\n", before=True)
        first = guest.run(operation_id, "on", source)
        equals("crash_before_fence_killed", first.returncode, -signal.SIGKILL)
        equals("crash_before_fence_state", int(guest.read("state")), 2)
        equals("crash_before_fence_one_dispatch", len(guest.dispatches), 1)
        _unknown(guest.run(operation_id, "on"), operation_id)
        equals("crash_before_fence_no_redispatch", len(guest.dispatches), 1)
        check("crash_before_fence_no_receipt", not guest.paths(operation_id)[0].exists())


def test_crash_after_durable_dispatch_never_recovers_success() -> None:
    with Guest() as guest:
        operation_id = "5" * 32
        source = _at(_source(), "dispatched", "    os._exit(97)\n")
        first = guest.run(operation_id, "on", source)
        equals("durable_crash_process_rc", first.returncode, 97)
        equals("durable_crash_dispatches", len(guest.dispatches), 1)
        equals("durable_crash_applied", int(guest.read("state")), 2)
        receipt, operation = guest.paths(operation_id)
        check("durable_crash_barrier", operation.is_file())
        check("durable_crash_no_receipt", not receipt.exists())
        durable = json.loads(operation.read_text())
        equals("durable_crash_phase", durable["phase"], "dispatched")
        equals("durable_crash_dispatch_rc", durable["dispatch_rc"], 0)
        guest.write("state", 0)
        guest.write("state", 2)
        recovery = _recovery(guest, operation_id)
        equals("durable_crash_recovery", recovery["recovery"], "retired")
        equals("durable_crash_status", recovery["receipt"]["status"], "failure")
        equals("durable_crash_failure", recovery["receipt"]["failure"], "POST_DISPATCH_PROOF_LOST")
        check("durable_crash_retired", not operation.exists())
        check("durable_crash_failure_receipt", receipt.is_file())
        replay = _terminal(guest.run(operation_id, "on"), operation_id, "on", rc=2)
        equals("durable_crash_replay_failure", replay["failure"], "POST_DISPATCH_PROOF_LOST")
        equals("durable_crash_no_redispatch", len(guest.dispatches), 1)


def test_pre_dispatch_query_timeout_is_terminal() -> None:
    with Guest(behavior="slow_query") as guest:
        operation_id = "3" * 32
        payload = _terminal(guest.run(operation_id, "on"), operation_id, "on", rc=2)
        equals("query_timeout_failure", payload["failure"], "CLIENTS_QUERY_FAILED_TIMEOUT")
        equals("query_timeout_no_dispatch", len(guest.dispatches), 0)
        receipt, operation = guest.paths(operation_id)
        check("query_timeout_receipt", receipt.is_file())
        check("query_timeout_retired", not operation.exists())


def test_stages_share_deadline_even_after_slow_start() -> None:
    for label, slow_start in (("normal_start", 0.0), ("slow_start", 0.6)):
        with Guest() as guest:
            source = _clock(_source())
            source = _inject(source, "TRANSACTION_BUDGET_SECONDS = 8.0", "TRANSACTION_BUDGET_SECONDS = 1.5")
            source = _at(source, "prepare", "        time.now += 0.25\n", before=True)
            source = _inject(source, POINTS["prepared"],
                             '        current_phase = "prepared"\n        time.now += 1.35\n\n    # Prepared replay')
            source = _slow_start(source, slow_start)
            payload = _terminal(guest.run("3" * 32, "on", source), "3" * 32, "on", rc=2)
            equals(label + "_shared_deadline", payload["failure"], "TRANSACTION_DEADLINE_EXCEEDED")
            equals(label + "_no_dispatch", len(guest.dispatches), 0)


def test_held_lock_uses_shared_deadline_even_after_slow_start() -> None:
    for label, slow_start in (("normal_start", 0.0), ("slow_start", 1.2)):
        with Guest() as guest:
            guest.base.mkdir(mode=0o700)
            holder = guest.start('''import fcntl, pathlib, sys, time
root = pathlib.Path(sys.argv[1])
with (root / "runtime/hyperlab-fullscreen/transaction.lock").open("a+") as handle:
    fcntl.flock(handle, fcntl.LOCK_EX)
    (root / "holder-ready").write_text("ready")
    deadline = time.monotonic() + 20
    while not (root / "holder-release").exists():
        if time.monotonic() >= deadline:
            raise SystemExit(90)
        time.sleep(0.01)
''', [str(guest.root)])
            guest.wait("holder-ready")
            source = _inject(_source(), "TRANSACTION_BUDGET_SECONDS = 8.0", "TRANSACTION_BUDGET_SECONDS = 0.2")
            source = _slow_start(source, slow_start)
            result = guest.run("4" * 32, "on", source)
            equals(label + "_lock_refusal", result.returncode, 75)
            equals(label + "_lock_no_dispatch", len(guest.dispatches), 0)
            check(label + "_holder_still_holds", holder.poll() is None)
            guest.write("holder-release", "release")
            equals(label + "_holder_reaped", guest.finish(holder).returncode, 0)


def test_deadline_exhaustion_before_launch_is_terminal() -> None:
    for point in ("prelaunch", "dispatching"):
        with Guest() as guest:
            source = _at(_source(), point, "    transaction_deadline = time.monotonic() - 1.0\n",
                         before=point == "prelaunch")
            operation_id = "1" * 32
            payload = _terminal(guest.run(operation_id, "on", source), operation_id, "on", rc=2)
            equals(point + "_deadline_failure", payload["failure"], "TRANSACTION_DEADLINE_EXCEEDED")
            equals(point + "_no_launch", len(guest.dispatches), 0)
            receipt, operation = guest.paths(operation_id)
            check(point + "_receipt", receipt.is_file())
            check(point + "_retired", not operation.exists())


def test_results_after_deadline_keep_durable_barrier() -> None:
    for label in ("dispatch_return", "postdispatch_query"):
        with Guest() as guest:
            if label == "dispatch_return":
                source = _at(_source(), "returned", "        transaction_deadline = time.monotonic() - 1.0\n", before=True)
            else:
                source = _at(_source(), "command_return",
                             '        if current_phase == "dispatched":\n'
                             '            globals()["transaction_deadline"] = time.monotonic() - 1.0\n', before=True)
            operation_id = "2" * 32
            result = guest.run(operation_id, "on", source)
            equals(label + "_rc", result.returncode, 75)
            equals(label + "_one_dispatch", len(guest.dispatches), 1)
            receipt, operation = guest.paths(operation_id)
            check(label + "_barrier", operation.is_file())
            check(label + "_no_receipt", not receipt.exists())
            durable = json.loads(operation.read_text())
            equals(label + "_phase", durable["phase"], "dispatching" if label == "dispatch_return" else "dispatched")
            if label == "dispatch_return":
                unknown = _unknown(result, operation_id)
                equals(label + "_reason", unknown["reason"], "TRANSACTION_DEADLINE_EXCEEDED")
                equals(label + "_blocker", unknown["blocking_operation_id"], operation_id)
            else:
                equals(label + "_no_terminal_stdout", result.stdout, "")


def test_persistence_reduces_timeout_passed_to_actual_launch() -> None:
    with Guest() as guest:
        source = _clock(_source())
        source = _at(source, "prelaunch", "    transaction_deadline = time.monotonic() + 1.5\n", before=True)
        source = _inject(source, "        remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n",
                         "        probe_initial_timeout = remaining_timeout(DISPATCH_TIMEOUT_SECONDS)\n")
        source = _at(source, "dispatching", "    time.now += 0.15\n")
        source = _at(source, "imports", '''_actual_run = subprocess.run
def _observe_launch(argv, **kwargs):
    if argv[:2] == ["hyprctl", "dispatch"]:
        (runtime.parent / "budget.json").write_text(json.dumps([probe_initial_timeout, kwargs["timeout"]]))
    return _actual_run(argv, **kwargs)
subprocess.run = _observe_launch
''', before=True)
        _terminal(guest.run("5" * 32, "on", source), "5" * 32, "on")
        equals("persistence_one_dispatch", len(guest.dispatches), 1)
        before, launch = json.loads(guest.read("budget.json"))
        equals("persistence_initial_budget", before, 1.5)
        check("persistence_launch_budget_reduced", abs(launch - 1.35) < 1e-8, repr([before, launch]))


def test_remaining_timeout_never_exceeds_remaining_budget() -> None:
    tree = ast.parse(_source())
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "remaining_timeout")
    namespace = {"transaction_deadline": 100.0002, "time": SimpleNamespace(monotonic=lambda: 100.0),
                 "TxnFailure": RuntimeError}
    exec(compile(ast.Module(body=[function], type_ignores=[]), "<remaining-timeout>", "exec"), namespace)
    timeout = namespace["remaining_timeout"](2.0)
    check("remaining_no_floor", 0 < timeout < 0.001, repr(timeout))
    namespace["transaction_deadline"] = 100.0
    try:
        namespace["remaining_timeout"](2.0)
    except RuntimeError as error:
        equals("remaining_expired_refused", str(error), "TRANSACTION_DEADLINE_EXCEEDED")
    else:
        check("remaining_expired_refused", False)


def test_failed_rollback_write_preserves_blocking_journal() -> None:
    with Guest() as guest:
        source = _at(_source(), "dispatching", "    transaction_deadline = time.monotonic() - 1.0\n")
        rollback = POINTS["rollback"]
        source = _inject(source, rollback, rollback.replace(
            "        replace_json(operation_path, record)\n",
            '        raise OSError("injected rollback persistence failure")\n'))
        operation_id = "3" * 32
        result = guest.run(operation_id, "on", source)
        equals("rollback_write_failure_zero_dispatch", len(guest.dispatches), 0)
        receipt, operation = guest.paths(operation_id)
        check("rollback_write_failure_barrier", operation.is_file())
        check("rollback_write_failure_no_receipt", not receipt.exists())
        equals("rollback_write_failure_durable_phase", json.loads(operation.read_text())["phase"], "dispatching")
        check("rollback_write_failure_not_success", result.returncode != 0)
        blocked = _unknown(guest.run("6" * 32, "on"), "6" * 32)
        equals("rollback_write_failure_blocks_other", blocked["blocking_operation_id"], operation_id)
        recovery = _recovery(guest, operation_id)
        equals("rollback_write_failure_recovery", recovery["recovery"], "still-unresolved")
        equals("rollback_write_failure_recovery_no_dispatch", len(guest.dispatches), 0)
        check("rollback_write_failure_barrier_after_recovery", operation.is_file())
        check("rollback_write_failure_no_receipt_after_recovery", not receipt.exists())


def test_interrupted_rollback_resumes_and_replays_same_operation() -> None:
    with Guest() as guest:
        source = _at(_source(), "dispatching", "    transaction_deadline = time.monotonic() - 1.0\n")
        rollback = POINTS["rollback"]
        source = _inject(source, rollback, rollback.replace("        finalize_failure(record, exc.code)\n",
                                                           "        raise SystemExit(99)\n"))
        operation_id = "4" * 32
        first = guest.run(operation_id, "on", source)
        equals("interrupted_rollback_rc", first.returncode, 99)
        equals("interrupted_rollback_no_dispatch", len(guest.dispatches), 0)
        receipt, operation = guest.paths(operation_id)
        check("interrupted_rollback_barrier", operation.is_file())
        check("interrupted_rollback_no_receipt", not receipt.exists())
        equals("interrupted_rollback_prepared", json.loads(operation.read_text())["phase"], "prepared")
        resumed = guest.run(operation_id, "on")
        payload = _terminal(resumed, operation_id, "on")
        equals("interrupted_rollback_resumed", payload["status"], "success")
        equals("interrupted_rollback_one_dispatch", len(guest.dispatches), 1)
        check("interrupted_rollback_receipt", receipt.is_file())
        check("interrupted_rollback_retired", not operation.exists())
        replay = guest.run(operation_id, "on")
        equals("interrupted_rollback_replay_rc", replay.returncode, 0)
        equals("interrupted_rollback_same_receipt", replay.stdout, resumed.stdout)
        equals("interrupted_rollback_no_redispatch", len(guest.dispatches), 1)


def test_dispatch_counter_counts_independent_calls() -> None:
    with Guest() as guest:
        guest.write("dispatches", "1\n1\n")
        equals("dispatch_counter_two_calls", len(guest.dispatches), 2)
