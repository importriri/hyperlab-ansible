#!/usr/bin/python3 -I
"""Reviewed managed lifecycle runner. No argv input, privilege or lock cleanup.

Records are observations, never command authority. Both launch and run resolve
an allowlisted action through the existing registry and current spec context.
The operation unit owns Ansible and its private PTY. Foot runs in a separate
view unit that only attaches: closing it detaches, it never cancels.
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import pwd
import re
import secrets
import select
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import termios
import time
from pathlib import Path

SELF = "/usr/local/bin/privatestack-operation"
CLI = "/usr/local/bin/hyperlabctl"
POINTER = Path("/etc/hyperlabctl/checkout")
ACTIONS = {"vm.managed-start": "start", "vm.managed-shutdown": "shutdown",
           "vm.managed-reboot": "reboot", "vm.force-stop": "force-stop",
           "vm.power-cycle": "power-cycle", "vm.reset": "reset"}
FINAL = {"succeeded", "failed", "interrupted"}
PHASES = FINAL | {"requested", "dispatched", "running"}
# terminal-opened and terminal-launch-failed are kept so earlier records stay
# readable after an upgrade; new records use the execution-* reasons.
REASONS = {"requested", "terminal-opened", "authentication-or-execution",
           "execution-succeeded", "execution-failed", "unit-inactive",
           "terminal-launch-failed", "interrupted", "execution-unavailable",
           "execution-dispatched", "execution-launch-failed"}
# Bounded replay for a view attached late; echo is off at password prompts.
TRANSCRIPT_LIMIT = 1 << 20
REPLAY_LIMIT = 64 << 10
KEYS = {"schema", "operation_id", "machine", "action_id", "phase", "unit",
        "checkout", "checkout_identity", "command_digest", "spec_digest",
        "created_at", "updated_at", "rc", "reason"}


class Refused(ValueError):
    pass


class Interrupted(Exception):
    pass


def require(ok, reason):
    if not ok:
        raise Refused(reason)


def identity(value):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{32}", value),
            "invalid-operation-id")
    return value


def private(path, directory=False):
    info = path.lstat()
    require((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            and info.st_uid == os.getuid()
            and stat.S_IMODE(info.st_mode) == (0o700 if directory else 0o600),
            "unsafe-operation-storage")


def directory():
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    require(runtime.is_absolute(), "unsafe-runtime-directory")
    private(runtime, True)
    root = runtime / "hyperlab"
    root.mkdir(mode=0o700, exist_ok=True)
    private(root, True)
    root = root / "operations"
    root.mkdir(mode=0o700, exist_ok=True)
    private(root, True)
    return root


@contextlib.contextmanager
def locked(root):
    fd = os.open(root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == os.getuid()
                and stat.S_IMODE(info.st_mode) == 0o600, "unsafe-operation-lock")
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def validate(record):
    require(isinstance(record, dict) and set(record) == KEYS, "invalid-operation-record")
    oid = identity(record["operation_id"])
    require(type(record["schema"]) is int and record["schema"] == 1 and record["action_id"] in ACTIONS
            and record["phase"] in PHASES and record["reason"] in REASONS
            and record["unit"] == "hyperlab-operation-" + oid,
            "invalid-operation-record")
    name = record["machine"]
    require(isinstance(name, str) and 0 < len(name) <= 255
            and not any(ord(c) < 32 or ord(c) == 127 for c in name), "invalid-machine")
    require(isinstance(record["checkout"], str) and Path(record["checkout"]).is_absolute()
            and isinstance(record["checkout_identity"], str), "invalid-checkout")
    for key in ("command_digest", "spec_digest"):
        require(isinstance(record[key], str) and re.fullmatch(r"[0-9a-f]{64}", record[key]),
                "invalid-operation-record")
    for key in ("created_at", "updated_at"):
        require(type(record[key]) in (int, float) and 0 < record[key] < 1e12,
                "invalid-operation-record")
    require(record["updated_at"] >= record["created_at"], "invalid-operation-record")
    rc = record["rc"]
    require(rc is None or (type(rc) is int and -255 <= rc <= 255), "invalid-operation-record")
    require((record["phase"] != "succeeded" or rc == 0)
            and (record["phase"] != "failed" or (type(rc) is int and rc != 0))
            and (record["phase"] in FINAL or rc is None), "invalid-operation-result")
    return record


def read(root, oid):
    path = root / (identity(oid) + ".json")
    private(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd) as stream:
        info = os.fstat(stream.fileno())
        require(info.st_uid == os.getuid() and stat.S_IMODE(info.st_mode) == 0o600
                and stat.S_ISREG(info.st_mode) and info.st_size <= 8192,
                "unsafe-operation-record")
        record = validate(json.load(stream))
    require(record["operation_id"] == oid, "operation-id-mismatch")
    return record


def write(root, record):
    validate(record)
    fd, name = tempfile.mkstemp(prefix=".record-", dir=root)
    try:
        with os.fdopen(fd, "w") as stream:
            os.fchmod(stream.fileno(), 0o600)
            json.dump(record, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, root / (record["operation_id"] + ".json"))
    finally:
        if os.path.exists(name):
            os.unlink(name)


def transition(root, record, phase, reason, rc=None):
    record = dict(record, phase=phase, reason=reason, rc=rc, updated_at=time.time())
    write(root, record)
    return record


def environment():
    user = pwd.getpwuid(os.getuid())
    env = {"PATH": "/usr/local/bin:/usr/bin", "HOME": user.pw_dir,
           "USER": user.pw_name, "LOGNAME": user.pw_name,
           "XDG_RUNTIME_DIR": str(directory().parents[1]), "LANG": "C.UTF-8"}
    for key in ("WAYLAND_DISPLAY", "DISPLAY", "XAUTHORITY", "DBUS_SESSION_BUS_ADDRESS"):
        value = os.environ.get(key)
        if value and len(value) <= 4096 and not any(ord(c) < 32 for c in value):
            env[key] = value
    return env


def call(argv, **kwargs):
    return subprocess.run(argv, capture_output=True, text=True, timeout=20,
                          check=False, env=environment(), **kwargs)


def cli(repo, *args):
    result = call([CLI, "--repo", str(repo), "--json", *args], cwd=repo)
    require(result.returncode == 0, "action-resolution-unavailable")
    return json.loads(result.stdout)


def checkout():
    repo = Path(POINTER.read_text().strip())
    require(repo.is_absolute() and repo.is_dir(), "invalid-checkout")
    return repo.resolve()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def resolve(action, machine, repo):
    require(action in ACTIONS, "unsupported-action")
    require(repo == checkout(), "checkout-changed")
    rows = cli(repo, "compose", "list")
    require(isinstance(rows, list), "invalid-spec-inventory")
    matches = [r for r in rows if isinstance(r, dict)
               and isinstance(r.get("spec"), dict) and r["spec"].get("name") == machine]
    require(len(matches) == 1, "machine-spec-unavailable")
    row = matches[0]
    argv = cli(repo, "actions", "--resolve", action, "--spec", row["path"],
               "--domain", machine)
    # The entire command is supplied by the existing resolver, never by the
    # caller or record. Normalize only its reviewed executable token.
    require(isinstance(argv, list) and argv and all(isinstance(x, str) and x for x in argv)
            and argv[0] == "ansible-playbook" and "-K" in argv,
            "invalid-reviewed-command")
    argv[0] = "/usr/bin/ansible-playbook"
    info = repo.stat()
    return argv, f"{info.st_dev}:{info.st_ino}", digest((repo / row["path"]).read_bytes())


def unit_active(unit):
    result = call(["/usr/bin/systemctl", "--user", "show", unit + ".service",
                   "--property=LoadState", "--property=ActiveState"])
    values = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    if values.get("LoadState") == "not-found":
        return False
    require(result.returncode == 0 and values.get("ActiveState") in
            {"active", "activating", "reloading", "deactivating", "inactive", "failed"},
            "unit-status-unavailable")
    return values["ActiveState"] not in {"inactive", "failed"}


def recover(root, record):
    if record["phase"] not in FINAL and not unit_active(record["unit"]):
        return transition(root, record, "interrupted", "unit-inactive")
    return record


def records(root):
    result = [read(root, path.stem) for path in sorted(root.glob("*.json"))]
    # A deleted record must not make a still-running unit disappear from
    # duplicate detection, including after presentation-shell restart.
    units = call(["/usr/bin/systemctl", "--user", "list-units", "--all",
                  "--plain", "--no-legend", "--no-pager", "hyperlab-operation-*.service"])
    require(units.returncode == 0, "unit-status-unavailable")
    known = {record["unit"] + ".service" for record in result}
    for line in units.stdout.splitlines():
        fields = line.split(None, 4)
        require(len(fields) >= 4 and re.fullmatch(
            r"hyperlab-operation-[0-9a-f]{32}\.service", fields[0]),
            "invalid-unit-inventory")
        require(fields[2] in {"active", "activating", "reloading", "deactivating",
                              "inactive", "failed"}, "invalid-unit-inventory")
        if fields[2] not in {"inactive", "failed"}:
            require(fields[0] in known, "active-operation-record-missing")
    return [recover(root, record) for record in result]


def launch(action, machine):
    require(action in ACTIONS, "unsupported-action")
    root = directory()
    with locked(root):
        for record in records(root):
            if record["machine"] == machine and record["phase"] not in FINAL:
                return {"phase": "refused", "reason": "operation-in-progress",
                        "operation_id": record["operation_id"], "machine": machine}
        repo = checkout()
        argv, repo_id, spec_hash = resolve(action, machine, repo)
        oid = secrets.token_hex(16)
        now = time.time()
        record = {"schema": 1, "operation_id": oid, "machine": machine, "action_id": action,
                      "phase": "requested", "unit": "hyperlab-operation-" + oid,
                      "checkout": str(repo), "checkout_identity": repo_id,
                      "command_digest": digest(json.dumps(argv).encode()), "spec_digest": spec_hash,
                      "created_at": now, "updated_at": now, "rc": None, "reason": "requested"}
        write(root, record)
        record = transition(root, record, "dispatched", "execution-dispatched")
        env = environment()
        command = ["/usr/bin/systemd-run", "--user", "--quiet", "--collect",
                   "--unit=" + record["unit"], "--property=Type=exec",
                   "--property=KillMode=control-group", "--property=UMask=0077",
                   "--working-directory=" + str(repo), "/usr/bin/env", "-i",
                   *[key + "=" + value for key, value in env.items()],
                   SELF, "run", oid]
        try:
            result = call(command, cwd=repo)
            require(result.returncode == 0, "execution-launch-failed")
        except subprocess.TimeoutExpired:
            # The unit may have started. An unknown outcome is not a failure:
            # the record stays dispatched and unit-state recovery settles it.
            return record
        except (OSError, Refused):
            return transition(root, record, "failed", "execution-launch-failed", 125)
    # Outside the lock: the view is presentation. Failing to open it leaves
    # the operation running and reattachable, never failed or cancelled.
    view(oid)
    return record


def view(oid):
    """Open an observer terminal in its own unit. Returns whether it launched."""
    identity(oid)
    env = environment()
    command = ["/usr/bin/systemd-run", "--user", "--quiet", "--collect",
               "--unit=hyperlab-view-" + oid + "-" + secrets.token_hex(4),
               "--property=Type=exec", "--property=UMask=0077", "/usr/bin/env", "-i",
               *[key + "=" + value for key, value in env.items()],
               "/usr/bin/foot", "--app-id=hyperlab-operation",
               "--title=HyperLab operation " + oid[:8], SELF, "attach", oid]
    try:
        return call(command).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def endpoint(root, oid):
    return root / (identity(oid) + ".sock")


def transcript(root, oid):
    return root / (identity(oid) + ".log")


def serve(root, oid):
    """Private listener for observers. Only this uid may attach."""
    path = endpoint(root, oid)
    with contextlib.suppress(FileNotFoundError):
        require(stat.S_ISSOCK(path.lstat().st_mode), "unsafe-operation-endpoint")
        path.unlink()
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
    listener.bind(str(path))
    os.chmod(path, 0o600)
    listener.listen(4)
    listener.setblocking(False)
    return listener, path


def peer_is_owner(conn):
    creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    return int.from_bytes(creds[4:8], sys.byteorder) == os.getuid()


def relay(child, master, listener, log, log_path):
    """Pump PTY output to the transcript and observers until the child exits."""
    clients = []
    written = 0

    def output(data):
        nonlocal written
        if written < TRANSCRIPT_LIMIT:
            chunk = data[:TRANSCRIPT_LIMIT - written]
            log.write(chunk)
            log.flush()
            written += len(chunk)
        for conn in list(clients):
            try:
                conn.sendall(data)
            except OSError:
                clients.remove(conn)
                conn.close()

    try:
        while True:
            exited = child.poll() is not None
            ready, _, _ = select.select([master, listener, *clients], [], [], 0 if exited else 0.5)
            if exited and master not in ready:
                break
            for item in ready:
                if item is master:
                    try:
                        data = os.read(master, 65536)
                    except OSError:
                        data = b""
                    if not data:
                        if exited or child.poll() is not None:
                            return
                        continue
                    output(data)
                elif item is listener:
                    try:
                        conn, _ = listener.accept()
                    except OSError:
                        continue
                    if not peer_is_owner(conn):
                        conn.close()
                        continue
                    # A stalled observer must never backpressure execution.
                    # sendall failure detaches it; it can reconnect for replay.
                    conn.setblocking(False)
                    try:
                        with open(log_path, "rb") as replay:
                            replay.seek(max(0, written - REPLAY_LIMIT))
                            conn.sendall(replay.read(REPLAY_LIMIT))
                        clients.append(conn)
                    except OSError:
                        conn.close()
                else:
                    try:
                        data = item.recv(4096)
                    except OSError:
                        data = b""
                    if not data:
                        # An observer left. That is detachment, not a signal.
                        clients.remove(item)
                        item.close()
                        continue
                    with contextlib.suppress(OSError):
                        os.write(master, data)
    finally:
        for conn in clients:
            conn.close()


def run(oid):
    root = directory()
    child = None
    record = None
    claimed = False
    phase, reason, rc = "failed", "execution-unavailable", 125

    def interrupted(signum, frame):
        raise Interrupted()

    # Only stopping the unit interrupts. A hangup (an observer, a closed
    # terminal, a lost session) is never a reason to abandon the operation.
    old = {signal.SIGTERM: signal.signal(signal.SIGTERM, interrupted),
           signal.SIGHUP: signal.signal(signal.SIGHUP, signal.SIG_IGN)}
    try:
        with locked(root):
            record = read(root, oid)
            require(record["phase"] == "dispatched", "operation-already-claimed")
            # Claim before resolution. A second run cannot execute the record.
            record = transition(root, record, "running", "authentication-or-execution")
            claimed = True
        argv, repo_id, spec_hash = resolve(record["action_id"], record["machine"],
                                           Path(record["checkout"]))
        require(repo_id == record["checkout_identity"]
                and spec_hash == record["spec_digest"]
                and digest(json.dumps(argv).encode()) == record["command_digest"],
                "reviewed-context-changed")
        master, slave = os.openpty()
        os.set_inheritable(slave, True)
        with contextlib.suppress(OSError):
            termios.tcsetwinsize(slave, (32, 120))
        header = f"HyperLab reviewed operation: {record['action_id']} {record['machine']}\r\n"
        os.write(slave, header.encode())
        listener, sock = serve(root, oid)
        log_fd = os.open(transcript(root, oid), os.O_CREAT | os.O_TRUNC | os.O_WRONLY
                         | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            with os.fdopen(log_fd, "wb") as log:
                # The PTY is Ansible's controlling terminal, so the become
                # prompt works without any observer, and no observer's exit
                # can hang it up.
                child = subprocess.Popen(
                    argv, cwd=record["checkout"], stdin=slave, stdout=slave, stderr=slave,
                    start_new_session=True, env={**environment(), "TERM": "xterm-256color"},
                    preexec_fn=lambda: fcntl.ioctl(0, termios.TIOCSCTTY, 0))
                os.close(slave)
                slave = None
                relay(child, master, listener, log, transcript(root, oid))
                rc = child.wait()
        finally:
            listener.close()
            with contextlib.suppress(OSError):
                sock.unlink()
            if slave is not None:
                os.close(slave)
            os.close(master)
        phase, reason = ("succeeded", "execution-succeeded") if rc == 0 else ("failed", "execution-failed")
    except (Interrupted, KeyboardInterrupt):
        phase, reason, rc = "interrupted", "interrupted", None
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        phase, reason, rc = "failed", "execution-unavailable", 125
    finally:
        for sig in old:
            signal.signal(sig, signal.SIG_IGN)
        if child is not None and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=3)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        # Never overwrite a record another observer already made terminal.
        if claimed:
            with locked(root):
                current = read(root, oid)
                if current["phase"] not in FINAL:
                    transition(root, current, phase, reason, rc)
        for sig, handler in old.items():
            signal.signal(sig, handler)
    return 0 if phase == "succeeded" else 1


def attach(oid):
    """Observer only. Leaving never signals the operation."""
    root = directory()
    with locked(root):
        record = read(root, oid)
    tty = sys.stdin.isatty()
    conn = None
    for _ in range(50):
        if record["phase"] in FINAL:
            break
        try:
            conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
            conn.connect(str(endpoint(root, oid)))
            break
        except OSError:
            conn.close()
            conn = None
            time.sleep(0.2)
            with locked(root):
                record = read(root, oid)
    saved = termios.tcgetattr(0) if tty and conn else None
    ended = False
    try:
        if conn is None:
            with contextlib.suppress(OSError), open(transcript(root, oid), "rb") as log:
                log.seek(max(0, log.seek(0, os.SEEK_END) - REPLAY_LIMIT))
                os.write(1, log.read())
        else:
            if saved:
                raw = termios.tcgetattr(0)
                raw[3] &= ~(termios.ICANON | termios.ECHO | termios.ISIG)
                raw[0] &= ~(termios.ICRNL | termios.IXON)
                termios.tcsetattr(0, termios.TCSANOW, raw)
            while True:
                ready, _, _ = select.select([conn, 0], [], [])
                if conn in ready:
                    data = conn.recv(65536)
                    if not data:
                        ended = True
                        break
                    os.write(1, data)
                if 0 in ready:
                    data = os.read(0, 4096)
                    if not data:
                        break
                    conn.sendall(data)
    finally:
        if saved:
            termios.tcsetattr(0, termios.TCSANOW, saved)
        if conn is not None:
            conn.close()
    # The runner ends the stream before it publishes the result. After the
    # stream ends, wait (bounded) for that record instead of reporting the
    # stale running phase; a detaching observer does not wait.
    deadline = time.monotonic() + 10
    while True:
        with locked(root):
            record = recover(root, read(root, oid))
        if not ended or record["phase"] in FINAL or time.monotonic() > deadline:
            break
        time.sleep(0.2)
    print(f"\r\n[HyperLab operation {record['phase']}"
          + (f" (exit {record['rc']})" if record["rc"] is not None else "")
          + (" - closing this window does not stop it" if record["phase"] not in FINAL else "")
          + "]", flush=True)
    if tty:
        with contextlib.suppress(EOFError, OSError):
            input("[press Enter to close] ")
    return 0


def main():
    os.umask(0o077)
    args = sys.argv[1:]
    if len(args) == 3 and args[0] == "launch":
        result = launch(args[1], args[2])
    elif len(args) == 2 and args[0] == "run":
        return run(identity(args[1]))
    elif len(args) == 2 and args[0] == "attach":
        return attach(identity(args[1]))
    elif len(args) == 2 and args[0] == "view":
        oid = identity(args[1])
        root = directory()
        with locked(root):
            record = recover(root, read(root, oid))
        result = record if view(oid) else {
            "phase": "refused", "reason": "operation-view-unavailable", "operation_id": oid}
    elif args == ["operations"] or (len(args) == 2 and args[0] == "operation"):
        root = directory()
        with locked(root):
            result = ({"schema": 1, "operations": records(root)} if len(args) == 1
                      else recover(root, read(root, args[1])))
    else:
        raise Refused("unsupported-operation-request")
    print(json.dumps(result, separators=(",", ":")), flush=True)
    return 2 if result.get("phase") == "refused" else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        print('{"phase":"refused","reason":"operation-information-unavailable"}', flush=True)
        raise SystemExit(2) from None
