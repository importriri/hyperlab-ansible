import json
import secrets
import shutil
import subprocess
import time
from pathlib import Path

from .. import document as doc
from ..errors import ContractError, Unavailable
from ..inventory import domain_detail
from ..registry import target_choices
from .base import Command
from .open import _ssh_argv, _wait_for_ssh_ready


_GUEST_FULLSCREEN_DOMAIN_TIMEOUT_SECONDS = 5.0
_GUEST_FULLSCREEN_TRANSACTION_TIMEOUT_SECONDS = 12.0
_GUEST_FULLSCREEN_RECEIPT_READ_TIMEOUT_SECONDS = 2.0
_GUEST_FULLSCREEN_RECEIPT_RECONCILE_SECONDS = 6.0
_GUEST_FULLSCREEN_RECEIPT_POLL_SECONDS = 0.25
_GUEST_FULLSCREEN_OPERATION_HEX_LENGTH = 32
_TRUE_FULLSCREEN_MODES = frozenset((2, 3))


_GUEST_FULLSCREEN_TRANSACTION = r"""from __future__ import annotations

import fcntl
import json
import os
import pathlib
import re
import stat
import subprocess
import sys
import time

OP_RE = re.compile(r"^[0-9a-f]{32}$")
ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]+$")
STABLE_ID_RE = re.compile(r"^[0-9a-fA-F]{1,32}$")
MODES = {0, 1, 2, 3}
TRUE_MODES = {2, 3}
REQUESTS = {"toggle", "on", "off"}
PHASES = {"prepared", "dispatching", "dispatched"}
DISPATCH_TIMEOUT_SECONDS = 2.0
TRANSACTION_BUDGET_SECONDS = 8.0


class TxnFailure(Exception):
    def __init__(self, code):
        super().__init__(code)
        self.code = code


class TxnUncertain(Exception):
    def __init__(self, code, blocking_operation_id=None):
        super().__init__(code)
        self.code = code
        self.blocking_operation_id = blocking_operation_id


operation_id = sys.argv[1] if len(sys.argv) > 1 else ""
requested_arg = sys.argv[2] if len(sys.argv) > 2 else ""
if not OP_RE.fullmatch(operation_id):
    raise SystemExit(64)
if requested_arg not in REQUESTS and requested_arg != "recover":
    raise SystemExit(64)

uid = os.getuid()
runtime = pathlib.Path(
    os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}"
)
current_phase = None
transaction_deadline = time.monotonic() + TRANSACTION_BUDGET_SECONDS


def secure_dir(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        try:
            path.mkdir(mode=0o700)
        except FileExistsError:
            pass
        info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise TxnFailure("RUNTIME_DIR_INVALID")
    if info.st_uid != uid:
        raise TxnFailure("RUNTIME_DIR_OWNER")
    os.chmod(path, 0o700)


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def remaining_timeout(cap):
    remaining = transaction_deadline - time.monotonic()
    if remaining <= 0:
        raise TxnFailure("TRANSACTION_DEADLINE_EXCEEDED")
    return min(float(cap), remaining)


def command(argv, failure_code, timeout=2.0):
    effective_timeout = remaining_timeout(timeout)
    try:
        result = subprocess.run(
            argv,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=effective_timeout,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        if time.monotonic() >= transaction_deadline:
            raise TxnFailure("TRANSACTION_DEADLINE_EXCEEDED") from exc
        raise TxnFailure(failure_code + "_TIMEOUT") from exc
    if time.monotonic() >= transaction_deadline:
        raise TxnFailure("TRANSACTION_DEADLINE_EXCEEDED")
    if result.returncode != 0:
        raise TxnFailure(failure_code)
    return result.stdout


def hyprland_process_pids():
    timeout = remaining_timeout(2.0)
    try:
        result = subprocess.run(
            ["pgrep", "-u", str(uid), "-x", "Hyprland"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired as exc:
        if time.monotonic() >= transaction_deadline:
            raise TxnFailure("TRANSACTION_DEADLINE_EXCEEDED") from exc
        raise TxnFailure("HYPRLAND_PROCESS_QUERY_TIMEOUT") from exc

    if time.monotonic() >= transaction_deadline:
        raise TxnFailure("TRANSACTION_DEADLINE_EXCEEDED")
    if result.returncode == 1 and not result.stdout.strip():
        return []
    if result.returncode != 0:
        raise TxnFailure("HYPRLAND_PROCESS_QUERY_FAILED")

    raw = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if not raw or any(not line.isdigit() for line in raw):
        raise TxnFailure("HYPRLAND_PROCESS_QUERY_INVALID")
    return [int(line) for line in raw]


def exact_mode(value, failure_code):
    if type(value) is not int or value not in MODES:
        raise TxnFailure(failure_code)
    return value


def is_true(mode):
    return mode in TRUE_MODES


def desired_for(request, mode):
    before_true = is_true(mode)
    if request == "toggle":
        return int(not before_true)
    if request == "on":
        return 1
    return 0


def instances():
    try:
        payload = json.loads(
            command(
                ["hyprctl", "instances", "-j"],
                "HYPRLAND_INSTANCES_FAILED",
            )
        )
    except json.JSONDecodeError as exc:
        raise TxnFailure("HYPRLAND_INSTANCES_INVALID") from exc
    if not isinstance(payload, list):
        raise TxnFailure("HYPRLAND_INSTANCES_INVALID")
    return payload


def session_tuple(item):
    pid = item.get("pid")
    instance = item.get("instance")
    wl_socket = item.get("wl_socket")
    if (
        type(pid) is not int
        or pid <= 0
        or not isinstance(instance, str)
        or not instance
        or not isinstance(wl_socket, str)
        or not wl_socket
    ):
        raise TxnFailure("HYPRLAND_INSTANCE_INVALID")
    return pid, instance, wl_socket


def select_session():
    pids = hyprland_process_pids()
    if len(pids) != 1:
        raise TxnFailure("HYPRLAND_PROCESS_AMBIGUOUS")
    pid = pids[0]

    matches = []
    for item in instances():
        if isinstance(item, dict) and item.get("pid") == pid:
            matches.append(item)
    if len(matches) != 1:
        raise TxnFailure("HYPRLAND_INSTANCE_AMBIGUOUS")
    return session_tuple(matches[0])


def record_session(record):
    return (
        record["hyprland_pid"],
        record["instance"],
        record["wl_socket"],
    )


SESSION_BOUND = "bound"
SESSION_EXPIRED = "expired"
SESSION_UNKNOWN = "unknown"


def session_binding_state(record):
    expected = record_session(record)

    try:
        observed_instances = instances()
    except TxnFailure as exc:
        if exc.code == "TRANSACTION_DEADLINE_EXCEEDED":
            raise
        return SESSION_UNKNOWN

    parsed = []
    for item in observed_instances:
        if not isinstance(item, dict):
            return SESSION_UNKNOWN
        try:
            parsed.append(session_tuple(item))
        except TxnFailure:
            return SESSION_UNKNOWN

    same_pid = [
        candidate
        for candidate in parsed
        if candidate[0] == expected[0]
    ]

    # Binding is authoritative only when inventory contains exactly one
    # identity for the durable PID and that complete tuple is the recorded
    # session. Conflicting or duplicate identities are ambiguity, never
    # evidence that the durable operation is safe to retire or redispatch.
    if len(same_pid) > 1:
        return SESSION_UNKNOWN

    if len(same_pid) == 1:
        if same_pid[0] != expected:
            return SESSION_UNKNOWN
        os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = expected[1]
        os.environ["WAYLAND_DISPLAY"] = expected[2]
        return SESSION_BOUND

    # Inventory omission alone is not authoritative expiration. Only the
    # independent process query can establish that the durable PID ended.
    try:
        pids = hyprland_process_pids()
    except TxnFailure as exc:
        if exc.code == "TRANSACTION_DEADLINE_EXCEEDED":
            raise
        return SESSION_UNKNOWN

    if expected[0] not in pids:
        return SESSION_EXPIRED

    return SESSION_UNKNOWN


def bind_session(record):
    return session_binding_state(record) == SESSION_BOUND


def bind_new_session(session):
    os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = session[1]
    os.environ["WAYLAND_DISPLAY"] = session[2]


def target_from_active():
    try:
        payload = json.loads(
            command(
                ["hyprctl", "activewindow", "-j"],
                "ACTIVE_QUERY_FAILED",
            )
        )
    except json.JSONDecodeError as exc:
        raise TxnFailure("ACTIVE_QUERY_INVALID") from exc
    if not isinstance(payload, dict):
        raise TxnFailure("ACTIVE_QUERY_INVALID")

    address = payload.get("address")
    if not isinstance(address, str) or not ADDRESS_RE.fullmatch(address):
        raise TxnFailure("ACTIVE_ADDRESS_INVALID")

    stable_id = payload.get("stableId")
    if not isinstance(stable_id, str) or not STABLE_ID_RE.fullmatch(stable_id):
        raise TxnFailure("ACTIVE_STABLE_ID_INVALID")

    if "fullscreen" not in payload:
        raise TxnFailure("ACTIVE_MODE_MISSING")
    return (
        address,
        stable_id,
        exact_mode(payload["fullscreen"], "ACTIVE_MODE_INVALID"),
    )


def mode_for_target(stable_id, timeout=0.5):
    try:
        payload = json.loads(
            command(
                ["hyprctl", "clients", "-j"],
                "CLIENTS_QUERY_FAILED",
                timeout=timeout,
            )
        )
    except json.JSONDecodeError as exc:
        raise TxnFailure("CLIENTS_QUERY_INVALID") from exc
    if not isinstance(payload, list):
        raise TxnFailure("CLIENTS_QUERY_INVALID")
    matches = [
        item
        for item in payload
        if isinstance(item, dict) and item.get("stableId") == stable_id
    ]
    if len(matches) != 1:
        raise TxnFailure("TARGET_IDENTITY_LOST")
    item = matches[0]
    if "fullscreen" not in item:
        raise TxnFailure("TARGET_MODE_MISSING")
    return exact_mode(item["fullscreen"], "TARGET_MODE_INVALID")



base = runtime / "hyperlab-fullscreen"
receipt_dir = base / "receipts"
operation_dir = base / "operations"
secure_dir(base)
secure_dir(receipt_dir)
secure_dir(operation_dir)

receipt_path = receipt_dir / f"{operation_id}.json"
operation_path = operation_dir / f"{operation_id}.json"


def read_json_file(path, *, missing_ok):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
    except FileNotFoundError:
        if missing_ok:
            return None
        raise TxnUncertain("STATE_FILE_MISSING")
    except OSError as exc:
        raise TxnUncertain("STATE_FILE_UNREADABLE") from exc

    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != uid
            or stat.S_IMODE(info.st_mode) != 0o600
        ):
            raise TxnUncertain("STATE_FILE_INVALID")
        raw = os.read(fd, 8193)
    finally:
        os.close(fd)

    if len(raw) > 8192:
        raise TxnUncertain("STATE_FILE_INVALID")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TxnUncertain("STATE_FILE_INVALID") from exc
    if not isinstance(payload, dict):
        raise TxnUncertain("STATE_FILE_INVALID")
    return payload


def write_all(fd, raw):
    offset = 0
    while offset < len(raw):
        written = os.write(fd, raw[offset:])
        if written <= 0:
            raise OSError("short state write")
        offset += written


def temp_json_path(path):
    return path.parent / (
        f".{path.name}.{os.getpid()}.{time.monotonic_ns()}.tmp"
    )


def write_new_json(path, payload):
    raw = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if len(raw) > 4096:
        raise RuntimeError("state payload overflow")

    # The final journal name is never visible until a complete fsynced JSON
    # record exists. A crash during creation can leave only a hidden temp file,
    # which operation discovery deliberately ignores.
    tmp = temp_json_path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o600)
    try:
        write_all(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)

    try:
        os.link(tmp, path, follow_symlinks=False)
    except FileExistsError as exc:
        raise TxnUncertain("OPERATION_CONFLICT") from exc
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    fsync_dir(path.parent)


def replace_json(path, payload):
    raw = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if len(raw) > 4096:
        raise RuntimeError("state payload overflow")

    tmp = temp_json_path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o600)
    try:
        write_all(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(tmp, path)
        fsync_dir(path.parent)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def remove_state(path):
    try:
        path.unlink()
    except FileNotFoundError:
        return
    fsync_dir(path.parent)


def validate_receipt(payload, opid, expected_request=None):
    expected_fields = {
        "operation_id",
        "status",
        "address",
        "before_mode",
        "after_mode",
        "requested",
        "desired",
        "transition_required",
        "failure",
    }
    if (
        set(payload) != expected_fields
        or payload.get("operation_id") != opid
        or payload.get("status") not in ("success", "failure")
    ):
        raise TxnUncertain("RECEIPT_INVALID")

    request = payload.get("requested")
    if request not in REQUESTS:
        raise TxnUncertain("RECEIPT_INVALID")
    if expected_request is not None and request != expected_request:
        raise TxnUncertain("RECEIPT_REQUEST_MISMATCH")

    if payload["status"] == "success":
        target = payload.get("address")
        before = payload.get("before_mode")
        after = payload.get("after_mode")
        want = payload.get("desired")
        transition_required = payload.get("transition_required")
        if (
            not isinstance(target, str)
            or not ADDRESS_RE.fullmatch(target)
            or type(before) is not int
            or before not in MODES
            or type(after) is not int
            or after not in MODES
            or type(want) is not int
            or want not in (0, 1)
            or type(transition_required) is not int
            or transition_required not in (0, 1)
            or payload.get("failure") is not None
        ):
            raise TxnUncertain("RECEIPT_INVALID")
        expected_desired = desired_for(request, before)
        if want != expected_desired or is_true(after) != bool(expected_desired):
            raise TxnUncertain("RECEIPT_INVALID")
        if transition_required != int(is_true(before) != bool(expected_desired)):
            raise TxnUncertain("RECEIPT_INVALID")
    else:
        failure = payload.get("failure")
        if not isinstance(failure, str) or not failure:
            raise TxnUncertain("RECEIPT_INVALID")
    return payload


def load_receipt(opid, expected_request=None):
    path = receipt_dir / f"{opid}.json"
    payload = read_json_file(path, missing_ok=True)
    if payload is None:
        return None
    return validate_receipt(payload, opid, expected_request)


def validate_operation(payload, opid, expected_request=None):
    expected_fields = {
        "operation_id",
        "phase",
        "requested",
        "address",
        "stable_id",
        "before_mode",
        "desired",
        "requires_dispatch",
        "hyprland_pid",
        "instance",
        "wl_socket",
        "dispatch_rc",
    }
    if set(payload) != expected_fields:
        raise TxnUncertain("OPERATION_INVALID")
    if payload.get("operation_id") != opid:
        raise TxnUncertain("OPERATION_INVALID")

    request = payload.get("requested")
    if request not in REQUESTS:
        raise TxnUncertain("OPERATION_INVALID")
    if expected_request is not None and request != expected_request:
        raise TxnUncertain("OPERATION_REQUEST_MISMATCH")

    phase = payload.get("phase")
    if phase not in PHASES:
        raise TxnUncertain("OPERATION_INVALID")

    target = payload.get("address")
    stable_id = payload.get("stable_id")
    before = payload.get("before_mode")
    want = payload.get("desired")
    needs_dispatch = payload.get("requires_dispatch")
    pid = payload.get("hyprland_pid")
    instance = payload.get("instance")
    wl_socket = payload.get("wl_socket")
    dispatch_rc = payload.get("dispatch_rc")
    if (
        not isinstance(target, str)
        or not ADDRESS_RE.fullmatch(target)
        or not isinstance(stable_id, str)
        or not STABLE_ID_RE.fullmatch(stable_id)
        or type(before) is not int
        or before not in MODES
        or type(want) is not int
        or want not in (0, 1)
        or type(needs_dispatch) is not int
        or needs_dispatch not in (0, 1)
        or type(pid) is not int
        or pid <= 0
        or not isinstance(instance, str)
        or not instance
        or not isinstance(wl_socket, str)
        or not wl_socket
    ):
        raise TxnUncertain("OPERATION_INVALID")

    expected_desired = desired_for(request, before)
    if want != expected_desired:
        raise TxnUncertain("OPERATION_INVALID")
    expected_change = int(is_true(before) != bool(expected_desired))
    if needs_dispatch != expected_change:
        raise TxnUncertain("OPERATION_INVALID")

    if phase in ("prepared", "dispatching"):
        if dispatch_rc is not None:
            raise TxnUncertain("OPERATION_INVALID")
    elif type(dispatch_rc) is not int or dispatch_rc != 0:
        raise TxnUncertain("OPERATION_INVALID")
    return payload


def load_operation(path, expected_request=None):
    opid = path.stem
    if not OP_RE.fullmatch(opid):
        raise TxnUncertain("OPERATION_FILENAME_INVALID")
    payload = read_json_file(path, missing_ok=False)
    return validate_operation(payload, opid, expected_request)


def publish_receipt(payload):
    path = receipt_dir / f"{payload['operation_id']}.json"
    existing = read_json_file(path, missing_ok=True)
    if existing is not None:
        validated = validate_receipt(
            existing,
            payload["operation_id"],
            payload["requested"],
        )
        if validated != payload:
            raise TxnUncertain("RECEIPT_CONFLICT")
        return

    raw = (
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    if len(raw) > 4096:
        raise RuntimeError("receipt overflow")

    tmp = temp_json_path(path)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(tmp, flags, 0o600)
    try:
        write_all(fd, raw)
        os.fsync(fd)
    finally:
        os.close(fd)

    try:
        os.link(tmp, path, follow_symlinks=False)
    except FileExistsError:
        existing = read_json_file(path, missing_ok=False)
        validated = validate_receipt(
            existing,
            payload["operation_id"],
            payload["requested"],
        )
        if validated != payload:
            raise TxnUncertain("RECEIPT_CONFLICT")
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
    fsync_dir(receipt_dir)


# `transition_required` describes the prepared snapshot intent only:
# whether the requested postcondition differed from the durable before-state.
# It is deliberately not named `changed`, because a synchronous compositor
# acknowledgement plus observation proves the requested postcondition, not
# exclusive causal ownership of the physical state transition.
def success_payload(record, observed_mode):
    return {
        "operation_id": record["operation_id"],
        "status": "success",
        "address": record["address"],
        "before_mode": record["before_mode"],
        "after_mode": observed_mode,
        "requested": record["requested"],
        "desired": record["desired"],
        "transition_required": record["requires_dispatch"],
        "failure": None,
    }


def failure_payload(record, code, observed_mode=None):
    return {
        "operation_id": record["operation_id"],
        "status": "failure",
        "address": record["address"],
        "before_mode": record["before_mode"],
        "after_mode": observed_mode,
        "requested": record["requested"],
        "desired": record["desired"],
        "transition_required": record["requires_dispatch"],
        "failure": code,
    }


def finalize_success(record, observed_mode):
    payload = success_payload(record, observed_mode)
    publish_receipt(payload)
    remove_state(operation_dir / f"{record['operation_id']}.json")
    sys.stdout.write(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    )
    raise SystemExit(0)


def finalize_failure(record, code, observed_mode=None):
    payload = failure_payload(record, code, observed_mode)
    publish_receipt(payload)
    remove_state(operation_dir / f"{record['operation_id']}.json")
    sys.stdout.write(
        json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
    )
    raise SystemExit(2)


def emit_unknown(reason, blocking_operation_id=None):
    envelope = {
        "operation_id": operation_id,
        "status": "unknown",
        "reason": reason,
        "blocking_operation_id": blocking_operation_id,
    }
    sys.stdout.write(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n"
    )
    raise SystemExit(75)


def emit_recovery(kind, *, receipt=None, reason=None):
    envelope = {
        "operation_id": operation_id,
        "recovery": kind,
        "receipt": receipt,
        "reason": reason,
    }
    sys.stdout.write(
        json.dumps(envelope, sort_keys=True, separators=(",", ":")) + "\n"
    )
    raise SystemExit(0)


def settle_dispatched(record, *, emit_terminal):
    if record["phase"] != "dispatched":
        raise TxnUncertain("DISPATCH_NOT_COMPLETED")

    # `dispatched` is reached only after the synchronous compositor call
    # returned rc=0 with the exact `ok` acknowledgement. The operation-owned
    # mutation therefore cannot still be pending. Success still requires an
    # immediate postcondition observation in this execution attempt.
    binding = session_binding_state(record)
    if binding != SESSION_BOUND:
        code = (
            "SESSION_EXPIRED"
            if binding == SESSION_EXPIRED
            else "POST_DISPATCH_QUERY_FAILED"
        )
        payload = failure_payload(record, code)
        publish_receipt(payload)
        remove_state(operation_dir / f"{record['operation_id']}.json")
        if emit_terminal:
            sys.stdout.write(
                json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
            )
            raise SystemExit(2)
        return payload

    try:
        observed = mode_for_target(record["stable_id"])
    except TxnFailure as exc:
        code = (
            "TARGET_GONE_AFTER_DISPATCH"
            if exc.code == "TARGET_IDENTITY_LOST"
            else "POST_DISPATCH_QUERY_FAILED"
        )
        payload = failure_payload(record, code)
        publish_receipt(payload)
        remove_state(operation_dir / f"{record['operation_id']}.json")
        if emit_terminal:
            sys.stdout.write(
                json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
            )
            raise SystemExit(2)
        return payload

    if is_true(observed) == bool(record["desired"]):
        payload = success_payload(record, observed)
    else:
        payload = failure_payload(
            record,
            "POST_DISPATCH_STATE_MISMATCH",
            observed,
        )

    publish_receipt(payload)
    remove_state(operation_dir / f"{record['operation_id']}.json")
    if emit_terminal:
        sys.stdout.write(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        )
        raise SystemExit(0 if payload["status"] == "success" else 2)
    return payload


def retire_unproven_dispatched(record, *, emit_terminal):
    # A durable dispatched record without a receipt means the process died
    # after synchronous completion but before it durably proved the immediate
    # postcondition. A later matching compositor state is not attributable to
    # this operation, so recovery must never manufacture success from it.
    payload = failure_payload(record, "POST_DISPATCH_PROOF_LOST")
    publish_receipt(payload)
    remove_state(operation_dir / f"{record['operation_id']}.json")
    if emit_terminal:
        sys.stdout.write(
            json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n"
        )
        raise SystemExit(2)
    return payload

def recover():
    terminal = load_receipt(operation_id)
    if terminal is not None:
        emit_recovery(
            "completed" if terminal["status"] == "success" else "retired",
            receipt=terminal,
        )

    try:
        record_raw = read_json_file(operation_path, missing_ok=True)
    except TxnUncertain as exc:
        # Invalid bytes or metadata cannot prove whether the durable record was
        # pre-dispatch, dispatching, or already completed. Preserve the barrier.
        emit_recovery("still-unresolved", reason=exc.code)
    if record_raw is None:
        emit_recovery("not-found", reason="operation record does not exist")
    record = validate_operation(record_raw, operation_id)

    if record["phase"] == "prepared":
        payload = failure_payload(record, "RECOVERED_PRE_DISPATCH")
        publish_receipt(payload)
        remove_state(operation_path)
        emit_recovery("retired", receipt=payload)

    if record["phase"] == "dispatching":
        binding = session_binding_state(record)

        if binding == SESSION_BOUND:
            emit_recovery(
                "still-unresolved",
                reason=(
                    "dispatch completion is unknown in the original Hyprland "
                    "session; restart or replace that compositor session before "
                    "retiring this operation"
                ),
            )

        if binding == SESSION_UNKNOWN:
            emit_recovery(
                "still-unresolved",
                reason="SESSION_DISCOVERY_AMBIGUOUS",
            )

        payload = failure_payload(record, "SESSION_EXPIRED")
        publish_receipt(payload)
        remove_state(operation_path)
        emit_recovery("retired", receipt=payload)

    payload = retire_unproven_dispatched(
        record,
        emit_terminal=False,
    )
    emit_recovery("retired", receipt=payload)

def reconcile_other_operations():
    for path in sorted(operation_dir.glob("*.json")):
        if path == operation_path:
            continue

        opid = path.stem
        if not OP_RE.fullmatch(opid):
            raise TxnUncertain(
                "PREVIOUS_OPERATION_RECOVERY_REQUIRED",
                opid if len(opid) == 32 else None,
            )
        try:
            record = load_operation(path)
        except TxnUncertain as exc:
            raise TxnUncertain(
                "PREVIOUS_OPERATION_RECOVERY_REQUIRED",
                opid,
            ) from exc

        terminal = load_receipt(
            record["operation_id"],
            record["requested"],
        )
        if terminal is not None:
            remove_state(path)
            continue

        # Prepared is a durable pre-dispatch binding, not garbage. Another
        # operation may never erase it; explicit recovery or same-ID replay owns
        # its retirement.
        raise TxnUncertain(
            "PREVIOUS_OPERATION_RECOVERY_REQUIRED",
            record["operation_id"],
        )


def resume_same_operation(record):
    if record["phase"] == "prepared":
        return record
    if record["phase"] == "dispatching":
        raise TxnUncertain(
            "OPERATION_STILL_DISPATCHING",
            record["operation_id"],
        )
    retire_unproven_dispatched(record, emit_terminal=True)
    raise AssertionError("retire_unproven_dispatched unexpectedly returned")


lock_path = base / "transaction.lock"
flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
lock_fd = os.open(lock_path, flags, 0o600)
lock_info = os.fstat(lock_fd)
if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid != uid:
    raise SystemExit(70)
os.fchmod(lock_fd, 0o600)

lock_deadline = min(
    transaction_deadline,
    time.monotonic() + 3.0,
)
while True:
    try:
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        break
    except BlockingIOError:
        now = time.monotonic()
        if now >= lock_deadline:
            raise SystemExit(75)
        time.sleep(min(0.05, max(0.001, lock_deadline - now)))

if requested_arg == "recover":
    try:
        recover()
    except TxnUncertain as exc:
        emit_recovery("still-unresolved", reason=exc.code)
    except TxnFailure as exc:
        emit_recovery("still-unresolved", reason=exc.code)

requested = requested_arg

try:
    terminal = load_receipt(operation_id, requested)
    if terminal is not None:
        remove_state(operation_path)
        sys.stdout.write(
            json.dumps(terminal, sort_keys=True, separators=(",", ":")) + "\n"
        )
        raise SystemExit(0 if terminal["status"] == "success" else 2)

    reconcile_other_operations()

    record_raw = read_json_file(operation_path, missing_ok=True)
    if record_raw is not None:
        record = validate_operation(
            record_raw,
            operation_id,
            requested,
        )
        record = resume_same_operation(record)
        current_phase = "prepared"
    else:
        session = select_session()
        bind_new_session(session)
        address, stable_id, before_mode = target_from_active()
        desired = desired_for(requested, before_mode)
        transition_required = int(is_true(before_mode) != bool(desired))

        record = {
            "operation_id": operation_id,
            "phase": "prepared",
            "requested": requested,
            "address": address,
            "stable_id": stable_id,
            "before_mode": before_mode,
            "desired": desired,
            "requires_dispatch": transition_required,
            "hyprland_pid": session[0],
            "instance": session[1],
            "wl_socket": session[2],
            "dispatch_rc": None,
        }
        write_new_json(operation_path, record)
        current_phase = "prepared"

    # Prepared replay must preserve its original target, session and toggle
    # precondition. Never reselect the active window or recompute desired state.
    binding = session_binding_state(record)
    if binding == SESSION_EXPIRED:
        finalize_failure(record, "SESSION_EXPIRED_PRE_DISPATCH")
    if binding == SESSION_UNKNOWN:
        finalize_failure(record, "SESSION_DISCOVERY_AMBIGUOUS_PRE_DISPATCH")
    try:
        observed = mode_for_target(record["stable_id"])
    except TxnFailure as exc:
        finalize_failure(
            record,
            "TARGET_GONE_PRE_DISPATCH"
            if exc.code == "TARGET_IDENTITY_LOST"
            else exc.code,
        )
    if observed != record["before_mode"]:
        finalize_failure(record, "PREPARED_STATE_DRIFT", observed)

    if not record["requires_dispatch"]:
        finalize_success(record, observed)

    # Resolve the dispatch timeout while the durable operation is still
    # prepared. Deadline exhaustion here proves that no dispatch was
    # launched, so it is a terminal pre-dispatch failure, not uncertainty.
    try:
        remaining_timeout(DISPATCH_TIMEOUT_SECONDS)
    except TxnFailure as exc:
        finalize_failure(record, exc.code)

    record = dict(record)
    record["phase"] = "dispatching"
    replace_json(operation_path, record)
    current_phase = "dispatching"

    # Toggle is snapshot semantics: desired was resolved exactly once from the
    # durable prepared state. Never issue a live compositor toggle here because
    # an unrelated state change between prepare and dispatch could invert the
    # requested transition. Explicit set/unset idempotently enforces the
    # prepared postcondition on the stable identity.
    dispatch_action = "set" if record["desired"] else "unset"
    expression = (
        'hl.dsp.window.fullscreen({ mode = "fullscreen", '
        f'action = "{dispatch_action}", '
        f'window = "stableid:{record["stable_id"]}" }})'
    )

    # Recompute the budget immediately before launch. The durable dispatching
    # transition can itself consume the remaining transaction budget.
    # If no launch can occur, restore the durable pre-dispatch phase before
    # publishing a terminal failure so recovery never mistakes this for an
    # uncertain mutation.
    try:
        dispatch_timeout = remaining_timeout(DISPATCH_TIMEOUT_SECONDS)
    except TxnFailure as exc:
        record = dict(record)
        record["phase"] = "prepared"
        replace_json(operation_path, record)
        current_phase = "prepared"
        finalize_failure(record, exc.code)

    try:
        dispatch_result = subprocess.run(
            ["hyprctl", "dispatch", expression],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=dispatch_timeout,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        if time.monotonic() >= transaction_deadline:
            raise TxnUncertain(
                "TRANSACTION_DEADLINE_EXCEEDED",
                operation_id,
            )
        raise TxnUncertain("FULLSCREEN_DISPATCH_TIMEOUT")
    except Exception as exc:
        raise TxnUncertain("FULLSCREEN_DISPATCH_EXCEPTION") from exc

    if time.monotonic() >= transaction_deadline:
        raise TxnUncertain(
            "TRANSACTION_DEADLINE_EXCEEDED",
            operation_id,
        )
    if dispatch_result.returncode < 0:
        raise TxnUncertain(
            "FULLSCREEN_DISPATCH_SIGNALLED",
            operation_id,
        )
    if dispatch_result.returncode != 0:
        raise TxnUncertain(
            "FULLSCREEN_DISPATCH_UNACKNOWLEDGED",
            operation_id,
        )
    if dispatch_result.stdout.strip() != "ok":
        raise TxnUncertain(
            "FULLSCREEN_DISPATCH_ACK_INVALID",
            operation_id,
        )

    # Hyprland documents hyprctl/control-socket requests as synchronous and
    # `dispatch` returns `ok` on accepted completion. Only that exact
    # acknowledgement may advance the durable completion fence.
    record = dict(record)
    record["phase"] = "dispatched"
    record["dispatch_rc"] = 0
    replace_json(operation_path, record)
    current_phase = "dispatched"

    settle_dispatched(record, emit_terminal=True)

except TxnUncertain as exc:
    blocker = exc.blocking_operation_id
    if blocker is None and operation_path.exists():
        blocker = operation_id
    emit_unknown(exc.code, blocker)
except TxnFailure as exc:
    if current_phase in ("dispatching", "dispatched"):
        raise SystemExit(75) from None
    record_raw = read_json_file(operation_path, missing_ok=True)
    if record_raw is None:
        raise SystemExit(70) from None
    record = validate_operation(record_raw, operation_id, requested)
    finalize_failure(record, exc.code)
except Exception:
    if current_phase in ("dispatching", "dispatched"):
        raise SystemExit(75) from None
    raise SystemExit(71) from None
"""


_GUEST_FULLSCREEN_RECEIPT_READ = r"""from __future__ import annotations

import os
import pathlib
import re
import stat
import sys

operation_id = sys.argv[1] if len(sys.argv) > 1 else ""
if not re.fullmatch(r"[0-9a-f]{32}", operation_id):
    raise SystemExit(64)
uid = os.getuid()
runtime = pathlib.Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{uid}")
path = runtime / "hyperlab-fullscreen" / "receipts" / f"{operation_id}.json"
flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
try:
    fd = os.open(path, flags)
except FileNotFoundError:
    raise SystemExit(44)
except OSError:
    raise SystemExit(45)
try:
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != uid or stat.S_IMODE(info.st_mode) != 0o600:
        raise SystemExit(45)
    raw = os.read(fd, 8193)
finally:
    os.close(fd)
if len(raw) > 8192:
    raise SystemExit(45)
try:
    text = raw.decode("utf-8")
except UnicodeDecodeError:
    raise SystemExit(45)
sys.stdout.write(text)
"""


def _valid_fullscreen_address(value):
    return (
        isinstance(value, str)
        and value.startswith("0x")
        and len(value) > 2
        and all(char in "0123456789abcdefABCDEF" for char in value[2:])
    )


def _valid_fullscreen_mode(value):
    return type(value) is int and value in (0, 1, 2, 3)


def _is_true_fullscreen(mode):
    return mode in _TRUE_FULLSCREEN_MODES


def _parse_fullscreen_receipt(output, expected_operation_id, expected_requested):
    lines = [line for line in output.splitlines() if line.strip()]
    if len(lines) != 1:
        raise Unavailable("guest fullscreen receipt returned an invalid envelope")
    try:
        payload = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise Unavailable("guest fullscreen receipt returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise Unavailable("guest fullscreen receipt is not a JSON object")

    expected_fields = {
        "operation_id", "status", "address", "before_mode", "after_mode",
        "requested", "desired", "transition_required", "failure",
    }
    if set(payload) != expected_fields:
        raise Unavailable("guest fullscreen receipt returned unexpected fields")

    operation_id = payload.get("operation_id")
    if operation_id != expected_operation_id:
        raise Unavailable("guest fullscreen receipt changed operation identity")
    if (
        not isinstance(operation_id, str)
        or len(operation_id) != _GUEST_FULLSCREEN_OPERATION_HEX_LENGTH
        or any(char not in "0123456789abcdef" for char in operation_id)
    ):
        raise Unavailable("guest fullscreen receipt has an invalid operation id")

    status = payload.get("status")
    if status not in ("success", "failure"):
        raise Unavailable("guest fullscreen receipt has an invalid status")
    if payload.get("requested") != expected_requested:
        raise Unavailable("guest fullscreen receipt changed requested state")

    address = payload.get("address")
    if address is not None and not _valid_fullscreen_address(address):
        raise Unavailable("guest fullscreen receipt has an invalid target")

    for field in ("before_mode", "after_mode"):
        value = payload.get(field)
        if value is not None and not _valid_fullscreen_mode(value):
            raise Unavailable("guest fullscreen receipt has invalid %s" % field)

    for field in ("desired", "transition_required"):
        value = payload.get(field)
        if value is not None and (type(value) is not int or value not in (0, 1)):
            raise Unavailable("guest fullscreen receipt has invalid %s" % field)

    failure = payload.get("failure")
    if failure is not None and (
        not isinstance(failure, str)
        or not 1 <= len(failure) <= 48
        or any(char not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for char in failure)
    ):
        raise Unavailable("guest fullscreen receipt has invalid failure code")

    if status == "success":
        if (
            address is None
            or not _valid_fullscreen_mode(payload.get("before_mode"))
            or not _valid_fullscreen_mode(payload.get("after_mode"))
            or type(payload.get("desired")) is not int
            or payload["desired"] not in (0, 1)
            or type(payload.get("transition_required")) is not int
            or payload["transition_required"] not in (0, 1)
            or failure is not None
        ):
            raise Unavailable("guest fullscreen success receipt is incomplete")
        before_true = _is_true_fullscreen(payload["before_mode"])
        if expected_requested == "toggle":
            expected_desired = int(not before_true)
        elif expected_requested == "on":
            expected_desired = 1
        else:
            expected_desired = 0

        if payload["desired"] != expected_desired:
            raise Unavailable(
                "guest fullscreen receipt contradicts the requested transition"
            )
        if _is_true_fullscreen(payload["after_mode"]) != bool(expected_desired):
            raise Unavailable(
                "guest fullscreen success receipt does not prove requested state"
            )
        expected_transition_required = int(before_true != bool(expected_desired))
        if payload["transition_required"] != expected_transition_required:
            raise Unavailable("guest fullscreen receipt has inconsistent transition requirement")
    elif failure is None:
        raise Unavailable("guest fullscreen failure receipt lacks a code")

    return payload


def _parse_fullscreen_unknown(output, expected_operation_id):
    lines = [line for line in output.splitlines() if line.strip()]
    if len(lines) != 1:
        raise Unavailable("guest fullscreen UNKNOWN returned an invalid envelope")
    try:
        payload = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise Unavailable("guest fullscreen UNKNOWN returned invalid JSON") from exc

    expected_fields = {
        "operation_id",
        "status",
        "reason",
        "blocking_operation_id",
    }
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise Unavailable("guest fullscreen UNKNOWN returned an invalid schema")
    if payload.get("operation_id") != expected_operation_id:
        raise Unavailable("guest fullscreen UNKNOWN operation id mismatch")
    if payload.get("status") != "unknown":
        raise Unavailable("guest fullscreen UNKNOWN status is invalid")

    reason = payload.get("reason")
    if not isinstance(reason, str) or not reason:
        raise Unavailable("guest fullscreen UNKNOWN lacks a reason")

    blocker = payload.get("blocking_operation_id")
    if blocker is not None and (
        not isinstance(blocker, str)
        or len(blocker) != _GUEST_FULLSCREEN_OPERATION_HEX_LENGTH
        or any(char not in "0123456789abcdef" for char in blocker)
    ):
        raise Unavailable("guest fullscreen UNKNOWN blocker id is invalid")
    return payload

def _parse_fullscreen_recovery(output, expected_operation_id):
    lines = [line for line in output.splitlines() if line.strip()]
    if len(lines) != 1:
        raise Unavailable("guest fullscreen recovery returned an invalid envelope")
    try:
        payload = json.loads(lines[0])
    except json.JSONDecodeError as exc:
        raise Unavailable("guest fullscreen recovery returned invalid JSON") from exc

    expected_fields = {"operation_id", "recovery", "receipt", "reason"}
    if not isinstance(payload, dict) or set(payload) != expected_fields:
        raise Unavailable("guest fullscreen recovery returned an invalid schema")
    if payload.get("operation_id") != expected_operation_id:
        raise Unavailable("guest fullscreen recovery operation id mismatch")
    if payload.get("recovery") not in (
        "completed",
        "retired",
        "still-unresolved",
        "not-found",
    ):
        raise Unavailable("guest fullscreen recovery returned an invalid state")

    receipt = payload.get("receipt")
    reason = payload.get("reason")
    recovery = payload["recovery"]

    if recovery in ("completed", "retired"):
        if not isinstance(receipt, dict):
            raise Unavailable(
                "guest fullscreen recovery lacks a terminal receipt"
            )
        request = receipt.get("requested")
        if request not in ("toggle", "on", "off"):
            raise Unavailable(
                "guest fullscreen recovery receipt request is invalid"
            )
        parsed_receipt = _parse_fullscreen_receipt(
            json.dumps(receipt, sort_keys=True, separators=(",", ":")),
            expected_operation_id,
            request,
        )
        if recovery == "completed" and parsed_receipt["status"] != "success":
            raise Unavailable(
                "guest fullscreen completed recovery contains a failure receipt"
            )
        if recovery == "retired" and parsed_receipt["status"] != "failure":
            raise Unavailable(
                "guest fullscreen retired recovery contains a success receipt"
            )
        if reason is not None:
            raise Unavailable(
                "guest fullscreen terminal recovery has stray reason"
            )

    else:
        if receipt is not None or not isinstance(reason, str) or not reason:
            raise Unavailable("guest fullscreen unresolved recovery is incomplete")

    return payload



def _run_fullscreen_remote(ssh_argv, operation_id, requested, timeout):
    return subprocess.run(
        [*ssh_argv, "python3", "-", operation_id, requested],
        input=_GUEST_FULLSCREEN_TRANSACTION,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


def _run_fullscreen_receipt_remote(ssh_argv, operation_id, timeout):
    return subprocess.run(
        [*ssh_argv, "python3", "-", operation_id],
        input=_GUEST_FULLSCREEN_RECEIPT_READ,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )


def _finish_fullscreen_receipt(payload, domain, reconciled):
    if payload["status"] != "success":
        raise Unavailable(
            "guest fullscreen terminal failure for %s: %s" % (domain, payload["failure"])
        )
    output = dict(payload)
    output["reconciled"] = int(bool(reconciled))
    print(json.dumps(output, sort_keys=True))
    return 0


def _reconcile_fullscreen_receipt(
    ssh_argv,
    domain,
    operation_id,
    requested,
    reason,
):
    deadline = (
        time.monotonic()
        + _GUEST_FULLSCREEN_RECEIPT_RECONCILE_SECONDS
    )
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break

        try:
            result = _run_fullscreen_receipt_remote(
                ssh_argv,
                operation_id,
                min(
                    _GUEST_FULLSCREEN_RECEIPT_READ_TIMEOUT_SECONDS,
                    remaining,
                ),
            )
        except subprocess.TimeoutExpired:
            result = None

        completed_at = time.monotonic()
        if completed_at > deadline:
            break

        if result is not None and result.returncode == 0:
            try:
                payload = _parse_fullscreen_receipt(
                    result.stdout,
                    operation_id,
                    requested,
                )
            except Unavailable as exc:
                raise Unavailable(
                    "guest fullscreen outcome is UNKNOWN for %s operation %s "
                    "after %s: terminal receipt is invalid; "
                    "do not blindly retry"
                    % (domain, operation_id, reason)
                ) from exc
            return _finish_fullscreen_receipt(
                payload,
                domain,
                reconciled=True,
            )

        if result is not None and result.returncode not in (44,):
            raise Unavailable(
                "guest fullscreen outcome is UNKNOWN for %s operation %s "
                "after %s: terminal receipt cannot be validated; "
                "do not blindly retry"
                % (domain, operation_id, reason)
            )

        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(
            min(
                _GUEST_FULLSCREEN_RECEIPT_POLL_SECONDS,
                remaining,
            )
        )

    raise Unavailable(
        "guest fullscreen outcome is UNKNOWN for %s operation %s after %s; "
        "no terminal receipt exists yet and the remote transaction may still "
        "be outstanding; do not blindly retry"
        % (domain, operation_id, reason)
    )


def _require_running_domain(ctx, domain):
    result = ctx.virsh_uncached(
        "domstate",
        domain,
        timeout=_GUEST_FULLSCREEN_DOMAIN_TIMEOUT_SECONDS,
    )
    if result.rc == 124:
        raise Unavailable("domain state query timed out for %s" % domain)
    if not result.ok:
        raise Unavailable("domain state query failed for %s" % domain)
    if (result.stdout.strip() or "unknown").lower() != "running":
        raise Unavailable("%s is not running" % domain)


class VmCommand(Command):
    name = "vm"
    help = "list, inspect and move domains"
    order = 15

    def configure(self, parser):
        sub = parser.add_subparsers(dest="vm_action", required=True)
        sub.add_parser("list", help="every domain with state and allocation")
        for action in ("start", "stop", "inspect"):
            child = sub.add_parser(action)
            child.add_argument("domain")
        fullscreen = sub.add_parser("guest-fullscreen")
        fullscreen.add_argument("domain")
        fullscreen_mode = fullscreen.add_mutually_exclusive_group()
        fullscreen_mode.add_argument(
            "--state",
            choices=("toggle", "on", "off"),
            default="toggle",
        )
        fullscreen_mode.add_argument(
            "--recover-operation",
            metavar="OPERATION_ID",
            help="safely recover one durable UNKNOWN fullscreen operation",
        )
        inventory = sub.add_parser(
            "inventory",
            help="publish strict runtime inventory for one managed guest",
        )
        inventory.add_argument("spec")

    def run(self, args, ctx):
        if args.vm_action == "list":
            return self._list(args, ctx)
        if args.vm_action == "inspect":
            return self._inspect(args, ctx)
        if args.vm_action == "inventory":
            return self._inventory(args, ctx)
        if args.vm_action == "guest-fullscreen":
            return self._guest_fullscreen(args, ctx)
        return self._move(args, ctx)

    def _list(self, args, ctx):
        document = doc.build(ctx, only={"domains", "memory", "host"})
        domains = document.get("domains") or []
        if args.json:
            print(json.dumps(domains, indent=2))
            return 0
        for domain in domains:
            note = ""
            if domain["blocked"]:
                note = "  blocked: short %d MB" % domain["blocked"]["short_mb"]
            print("%-26s %-10s %8s %s%s" % (
                domain["name"], domain["state"],
                "%s MB" % domain["memory_mb"] if domain["memory_mb"] else "-",
                domain["network"] or "-", note))
        return 0

    def _inspect(self, args, ctx):
        detail = domain_detail(ctx, args.domain)
        if args.json:
            print(json.dumps(detail, indent=2))
        else:
            for key in ("name", "state", "memory_mb", "networks", "hostdevs", "vfio"):
                print("%-12s %s" % (key, detail[key]))
        return 0

    def _inventory_paths(self, ctx, spec):
        repo_value = ctx.config.repo_root
        if repo_value is None:
            raise Unavailable(
                "no HyperLab checkout is available for inventory publication"
            )

        repo_root = Path(repo_value).resolve()
        if spec not in target_choices("spec", repo_root):
            raise ContractError(
                "%s is not a checked-in or generated spec target" % spec
            )

        base_inventory = repo_root / "inventory.ini"
        playbook = repo_root / "playbooks/vm-guest-inventory.yml"

        for candidate, label in (
            (base_inventory, "base inventory"),
            (playbook, "runtime inventory playbook"),
        ):
            if candidate.is_symlink() or not candidate.is_file():
                raise Unavailable(
                    "%s is unavailable: %s" % (label, candidate)
                )

        return repo_root, base_inventory, playbook

    def _inventory(self, args, ctx):
        repo_root, base_inventory, playbook = self._inventory_paths(
            ctx,
            args.spec,
        )

        executable = shutil.which("ansible-playbook")
        if executable is None:
            raise Unavailable(
                "ansible-playbook is unavailable for inventory publication"
            )

        try:
            result = subprocess.run(
                [
                    executable,
                    "-i",
                    str(base_inventory),
                    str(playbook),
                    "-e",
                    "guest_spec=%s" % args.spec,
                ],
                cwd=repo_root,
                check=False,
                timeout=30.0,
            )
        except subprocess.TimeoutExpired as exc:
            raise Unavailable(
                "runtime inventory publication timed out"
            ) from exc

        return result.returncode

    def _guest_fullscreen(self, args, ctx):
        _require_running_domain(ctx, args.domain)

        ssh_argv = _ssh_argv(ctx, args.domain)
        _wait_for_ssh_ready(ssh_argv, args.domain)

        recover_operation = getattr(args, "recover_operation", None)
        if recover_operation:
            if (
                len(recover_operation) != _GUEST_FULLSCREEN_OPERATION_HEX_LENGTH
                or any(
                    char not in "0123456789abcdef"
                    for char in recover_operation
                )
            ):
                raise ContractError(
                    "guest fullscreen recovery operation id must be 32 lowercase hex characters"
                )
            try:
                result = _run_fullscreen_remote(
                    ssh_argv,
                    recover_operation,
                    "recover",
                    _GUEST_FULLSCREEN_TRANSACTION_TIMEOUT_SECONDS,
                )
            except subprocess.TimeoutExpired as exc:
                raise Unavailable(
                    "guest fullscreen recovery transport timed out for %s operation %s"
                    % (args.domain, recover_operation)
                ) from exc

            if result.returncode != 0:
                raise Unavailable(
                    "guest fullscreen recovery transport failed for %s operation %s "
                    "(rc=%d)"
                    % (args.domain, recover_operation, result.returncode)
                )
            payload = _parse_fullscreen_recovery(
                result.stdout,
                recover_operation,
            )
            print(json.dumps(payload, sort_keys=True))
            return (
                2
                if payload["recovery"] in ("still-unresolved", "not-found")
                else 0
            )

        requested = getattr(args, "state", "toggle")
        if requested not in ("toggle", "on", "off"):
            raise ContractError(
                "guest fullscreen state must be toggle, on or off"
            )

        operation_id = secrets.token_hex(
            _GUEST_FULLSCREEN_OPERATION_HEX_LENGTH // 2
        )
        if len(operation_id) != _GUEST_FULLSCREEN_OPERATION_HEX_LENGTH:
            raise Unavailable(
                "guest fullscreen operation id generation failed"
            )

        try:
            result = _run_fullscreen_remote(
                ssh_argv,
                operation_id,
                requested,
                _GUEST_FULLSCREEN_TRANSACTION_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            return _reconcile_fullscreen_receipt(
                ssh_argv,
                args.domain,
                operation_id,
                requested,
                "transaction transport timeout",
            )

        if result.returncode != 0:
            if result.returncode == 75:
                try:
                    unknown = _parse_fullscreen_unknown(
                        result.stdout,
                        operation_id,
                    )
                except Unavailable:
                    pass
                else:
                    print(json.dumps(unknown, sort_keys=True))
                    return 2

            return _reconcile_fullscreen_receipt(
                ssh_argv,
                args.domain,
                operation_id,
                requested,
                "transaction rc=%d" % result.returncode,
            )

        try:
            payload = _parse_fullscreen_receipt(
                result.stdout,
                operation_id,
                requested,
            )
        except Unavailable:
            return _reconcile_fullscreen_receipt(
                ssh_argv,
                args.domain,
                operation_id,
                requested,
                "malformed transaction completion",
            )

        return _finish_fullscreen_receipt(
            payload,
            args.domain,
            reconciled=False,
        )

    def _move(self, args, ctx):
        """start and stop stay unprivileged: the libvirt group already allows
        them. The refusal lives in operations.py so the panel refuses the same
        way, with the same numbers."""
        from ..operations import start, stop
        outcome = start(ctx, args.domain) if args.vm_action == "start" else stop(ctx, args.domain)
        print(outcome.message)
        return 0 if outcome.ok else 2
