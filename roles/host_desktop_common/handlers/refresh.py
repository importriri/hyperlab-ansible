#!/usr/bin/env python3
"""Refresh installed presentation code in an existing desktop user's session."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
import signal
from pathlib import Path
import stat
import subprocess
import threading
import time
from typing import Any, Iterator
import uuid

UNIT = "hyperlab-quickshell.service"
APP_ID = "io.github.importriri.HyperlabControlCenter"
SHELL_ROOT = Path("/etc/xdg/quickshell/hyperlab")
UNIT_PATH = Path("/etc/systemd/user") / UNIT
CONTROL_CENTER_PATH = Path("/usr/local/bin/privatestack-hyperlab-domains")
PROC_ROOT = Path("/proc")
CGROUP_ROOT = Path("/sys/fs/cgroup")
STATUS_BRIDGE = "/usr/local/bin/privatestack-hyperlab"
COMPOSITOR_ADAPTER = "/usr/local/bin/privatestack-compositor-adapter"
# Every command ShellState.qml runs: status reads, event watches and the
# provenance resolver. None changes state, and the restarted shell starts
# them again. Operation and launcher children are never on this list.
RESIDENT_OBSERVERS = frozenset({
    (STATUS_BRIDGE, "network-inventory"),
    (STATUS_BRIDGE, "nitro-status"),
    (STATUS_BRIDGE, "watch", "trust"),
    (STATUS_BRIDGE, "ram"),
    (STATUS_BRIDGE, "gpu"),
    (STATUS_BRIDGE, "vms"),
    (STATUS_BRIDGE, "diagnostics-domains"),
    (COMPOSITOR_ADAPTER, "workspace-watch"),
    (COMPOSITOR_ADAPTER, "focused-window-watch"),
    (COMPOSITOR_ADAPTER, "product-identity"),
    ("/usr/local/bin/privatestack-surface-provenance", "stream"),
    ("/usr/local/bin/privatestack-telemetry", "snapshot"),
})
# How the bridges' "#!/usr/bin/env bash" or "python3" shebangs appear in argv.
INTERPRETERS = frozenset({(), ("bash",), ("python3",), ("/usr/bin/env", "bash"),
                          ("/usr/bin/env", "python3")})
IDLE_WAIT_SECONDS = 10
CHECKOUT_POINTER = Path("/etc/hyperlabctl/checkout")


def runtime_path() -> Path:
    uid = os.getuid()
    if uid == 0:
        raise RuntimeError("Desktop refresh must run as the desktop user")
    return Path("/run/user") / str(uid)


def session_environment() -> dict[str, str] | None:
    # Ignore inherited root/SSH session addresses. A logged-out user needs no
    # refresh; an existing but redirected or foreign transport is a refusal.
    runtime = runtime_path()
    try:
        info = runtime.lstat()
    except FileNotFoundError:
        return None
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise RuntimeError("Unsafe desktop user runtime directory")
    bus = runtime / "bus"
    try:
        info = bus.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError("Unsafe desktop user bus")
    return dict(os.environ, XDG_RUNTIME_DIR=str(runtime),
                DBUS_SESSION_BUS_ADDRESS="unix:path=" + str(bus))


def require_regular_file(path: Path) -> None:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"Installed source is not an unredirected regular file: {path}")


def source_generation(surface: str) -> str:
    entries = []

    def include(path: Path, name: str) -> None:
        require_regular_file(path)
        entries.append((name, hashlib.sha256(path.read_bytes()).hexdigest()))

    def collect(directory: Path) -> None:
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise RuntimeError(f"Redirected shell directory: {directory}")
        for path in sorted(directory.iterdir()):
            if stat.S_ISDIR(path.lstat().st_mode):
                collect(path)
            else:
                require_regular_file(path)
                # This runtime-data file has its own live FileView observer.
                if path != SHELL_ROOT / "features.json":
                    include(path, str(path.relative_to(SHELL_ROOT)))

    if surface == "quickshell":
        require_regular_file(SHELL_ROOT / "shell.qml")
        collect(SHELL_ROOT)
        include(UNIT_PATH, str(UNIT_PATH))
        for executable in sorted({command[0] for command in RESIDENT_OBSERVERS}):
            include(Path(executable), executable)
        _, resolver = provenance_source()
        include(CHECKOUT_POINTER, str(CHECKOUT_POINTER))
        include(resolver, str(resolver))
    else:
        include(CONTROL_CENTER_PATH, str(CONTROL_CENTER_PATH))
    return hashlib.sha256(json.dumps(entries, separators=(",", ":")).encode()).hexdigest()


def process_fields(pid: int) -> list[str]:
    if pid <= 0:
        raise RuntimeError("Missing resident process PID")
    directory = PROC_ROOT / str(pid)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError("Resident process is redirected or belongs to another user")
    path = directory / "stat"
    require_regular_file(path)
    fields = path.read_text().rpartition(") ")[2].split()
    if len(fields) < 20:
        raise RuntimeError("Cannot read resident process identity")
    return fields


def boot_ticks() -> int:
    return time.clock_gettime_ns(time.CLOCK_BOOTTIME) * os.sysconf("SC_CLK_TCK") // 1_000_000_000


def process_ticks(pid: int) -> int:
    try:
        ticks = int(process_fields(pid)[19])
    except ValueError as exc:
        raise RuntimeError("Cannot read resident process start ticks") from exc
    if ticks <= 0 or ticks > boot_ticks():
        raise RuntimeError("Invalid resident process start ticks")
    return ticks


def unique_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise RuntimeError("Duplicated resident checkpoint field")
        result[key] = value
    return result


class Checkpoint:
    def __init__(self, descriptor: int) -> None:
        self.descriptor = descriptor
        boot = PROC_ROOT / "sys/kernel/random/boot_id"
        require_regular_file(boot)
        self.boot_id = str(uuid.UUID(boot.read_text().strip()))
        raw = os.read(descriptor, 8193)
        self.state = json.loads(raw, object_pairs_hook=unique_keys) if raw else None
        if raw and self.state is None:
            raise RuntimeError("Invalid resident checkpoint")
        if self.state is not None:
            state = self.state
            if (not isinstance(state, dict)
                    or set(state) != {"boot_id", "generation", "boundary", "resident"}
                    or not isinstance(state["boot_id"], str)
                    or str(uuid.UUID(state["boot_id"])) != state["boot_id"]
                    or not isinstance(state["generation"], str)
                    or len(state["generation"]) != 64
                    or any(char not in "0123456789abcdef" for char in state["generation"])
                    or type(state["boundary"]) is not int or state["boundary"] < 0):
                raise RuntimeError("Invalid resident checkpoint")
            resident = state["resident"]
            if resident is not None and (not isinstance(resident, list) or len(resident) != 2
                                        or any(type(value) is not int or value <= 0 for value in resident)):
                raise RuntimeError("Invalid checkpoint process identity")
            if state["boot_id"] == self.boot_id and state["boundary"] > boot_ticks():
                raise RuntimeError("Checkpoint boundary is in the future")

    def current(self, generation: str, pid: int) -> bool:
        identity = [pid, process_ticks(pid)]
        state = self.state
        return bool(state and state["boot_id"] == self.boot_id
                    and state["generation"] == generation
                    and (state["resident"] == identity or identity[1] > state["boundary"]))

    def record(self, generation: str, boundary: int, pid: int | None = None) -> None:
        state = {"boot_id": self.boot_id, "generation": generation, "boundary": boundary,
                 "resident": [pid, process_ticks(pid)] if pid is not None else None}
        raw = json.dumps(state).encode()
        os.lseek(self.descriptor, 0, os.SEEK_SET)
        if os.write(self.descriptor, raw) != len(raw):
            raise RuntimeError("Incomplete resident checkpoint write")
        os.ftruncate(self.descriptor, len(raw))
        os.fsync(self.descriptor)
        self.state = state


@contextmanager
def checkpoint(env: dict[str, str], surface: str) -> Iterator[Checkpoint]:
    path = Path(env["XDG_RUNTIME_DIR"]) / ("hyperlab-resident-" + surface + ".json")
    descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                or stat.S_IMODE(info.st_mode) != 0o600 or info.st_nlink != 1
                or info.st_size > 8192):
            raise RuntimeError("Unsafe resident checkpoint")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            saved = Checkpoint(descriptor)
        except (ValueError, TypeError) as exc:
            raise RuntimeError("Invalid resident checkpoint") from exc
        yield saved
    finally:
        os.close(descriptor)


def shell_properties(env: dict[str, str]) -> dict[str, str]:
    names = ("LoadState", "ActiveState", "MainPID", "ControlGroup", "NeedDaemonReload", "Restart",
             "RestartPreventExitStatus", "SuccessExitStatus")
    result = subprocess.run(
        ["/usr/bin/systemctl", "--user", "show", "--property=" + ",".join(names), UNIT],
        check=True, timeout=10, env=env, capture_output=True, text=True,
    )
    properties = {}
    for line in result.stdout.splitlines():
        key, separator, value = line.partition("=")
        if not separator or key not in names or key in properties:
            raise RuntimeError("Invalid or duplicated shell service property")
        properties[key] = value
    if set(properties) != set(names):
        raise RuntimeError("Missing shell service property")
    if properties["NeedDaemonReload"] not in ("yes", "no"):
        raise RuntimeError("Invalid shell daemon-reload state")
    return properties


def control_group_members(properties: dict[str, str]) -> set[int]:
    group = Path(properties["ControlGroup"])
    if not group.is_absolute() or group == Path("/") or ".." in group.parts:
        raise RuntimeError("Missing or unsafe shell control group")
    directory = CGROUP_ROOT / str(group).lstrip("/")
    if directory.resolve(strict=True) != directory:
        raise RuntimeError("Redirected shell control group")
    members: set[int] = set()

    def collect(path: Path) -> None:
        # systemd's control-group kill includes descendant cgroups as well.
        membership = path / "cgroup.procs"
        require_regular_file(membership)
        for value in membership.read_text().split():
            if not value.isdecimal() or int(value) <= 0:
                raise RuntimeError("Invalid shell control-group member")
            members.add(int(value))
        for entry in path.iterdir():
            info = entry.lstat()
            if stat.S_ISLNK(info.st_mode):
                raise RuntimeError("Redirected shell control-group input")
            if stat.S_ISDIR(info.st_mode):
                collect(entry)

    collect(directory)
    return members


def process_identity(pid: int) -> tuple[int, tuple[str, ...]]:
    directory = PROC_ROOT / str(pid)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError("Shell child is redirected or belongs to another user")
    fields = (directory / "stat").read_text().rpartition(") ")[2].split()
    try:
        parent = int(fields[1])
    except (IndexError, ValueError) as exc:
        raise RuntimeError("Cannot read shell child parent") from exc
    arguments = (directory / "cmdline").read_bytes().split(b"\0")[:-1]
    return parent, tuple(os.fsdecode(argument) for argument in arguments)


def provenance_source() -> tuple[Path, Path]:
    require_regular_file(CHECKOUT_POINTER)
    lines = CHECKOUT_POINTER.read_text().splitlines()
    if len(lines) != 1:
        raise RuntimeError("Invalid checkout pointer")
    checkout = Path(lines[0])
    if not checkout.is_absolute():
        raise RuntimeError("Redirected checkout pointer")
    resolver = checkout.resolve(strict=True) / "tools/surface_provenance.py"
    require_regular_file(resolver)
    if resolver.resolve(strict=True) != resolver:
        raise RuntimeError("Redirected provenance resolver")
    return checkout, resolver


def provenance_resolver(argv: tuple[str, ...]) -> bool:
    if argv[:3] != ("/usr/bin/python3", "-I", "-B"):
        return False
    checkout, _ = provenance_source()
    # The bridge execs with the pointer's spelling, including checkout symlinks.
    resolver = checkout / "tools/surface_provenance.py"
    return argv == ("/usr/bin/python3", "-I", "-B", str(resolver), "--repo", str(checkout),
                    "--proc-root", "/proc", "stream", "--registry",
                    f"/run/user/{os.getuid()}/hyperlab/surface-provenance.json")


def resident_observer(argv: tuple[str, ...]) -> bool:
    if provenance_resolver(argv):
        return True
    for command in RESIDENT_OBSERVERS:
        split = len(argv) - len(command)
        if split >= 0 and argv[split:] == command and argv[:split] in INTERPRETERS:
            return True
    return False


def busy_members(properties: dict[str, str]) -> list[int]:
    main_pid = int(properties["MainPID"])
    members = control_group_members(properties)
    if main_pid not in members:
        raise RuntimeError("Shell main PID is outside its control group")
    identities: dict[int, tuple[int, tuple[str, ...]]] = {}
    busy: set[int] = set()
    for pid in members - {main_pid}:
        try:
            identities[pid] = process_identity(pid)
        except (OSError, RuntimeError):
            # Exited, hidden or foreign: never assume it is disposable.
            busy.add(pid)

    def observed(pid: int, depth: int = 0) -> bool:
        parent, argv = identities[pid]
        if parent == main_pid:
            return resident_observer(argv)
        # An observer's own readers (for example an event stream) belong to it.
        return parent in identities and depth < len(identities) and observed(parent, depth + 1)

    busy.update(pid for pid in identities if not observed(pid))
    return sorted(busy)


def require_idle_cgroup(properties: dict[str, str]) -> None:
    # Restarting the unit kills its whole control group. Only the shell's own
    # read-only observers may go; the new shell starts them again.
    deadline = time.monotonic() + IDLE_WAIT_SECONDS
    while busy := busy_members(properties):
        if time.monotonic() >= deadline:
            raise RuntimeError(
                f"Shell refresh refused: shell child PIDs {busy} are not read-only "
                "observers. Finish or close them, then reapply."
            )
        time.sleep(0.25)


def thread_states(pid: int) -> list[str]:
    task = PROC_ROOT / str(pid) / "task"
    if not stat.S_ISDIR(task.lstat().st_mode):
        raise RuntimeError("Redirected shell threads")
    states = []
    for thread in task.iterdir():
        if not stat.S_ISDIR(thread.lstat().st_mode):
            raise RuntimeError("Redirected shell thread")
        path = thread / "stat"
        require_regular_file(path)
        fields = path.read_text().rpartition(") ")[2].split()
        if not fields:
            raise RuntimeError("Missing shell thread state")
        states.append(fields[0])
    if not states:
        raise RuntimeError("Missing shell threads")
    return states


class PausedShell:
    def __init__(self, descriptor: int) -> None:
        self.descriptor = descriptor
        self.killed = False

    def terminate(self) -> None:
        # No SIGCONT and no systemd restart job: either would let the shell
        # launch a child after the final inspection. SIGKILL cannot run QML.
        signal.pidfd_send_signal(self.descriptor, signal.SIGKILL)
        self.killed = True


@contextmanager
def paused_shell(pid: int, started: int) -> Iterator[PausedShell]:
    descriptor = os.pidfd_open(pid)
    paused = PausedShell(descriptor)
    stopped = False
    try:
        if process_ticks(pid) != started or any(state in ("T", "t") for state in thread_states(pid)):
            raise RuntimeError("Shell identity changed or was already stopped")
        stopped = True
        signal.pidfd_send_signal(descriptor, signal.SIGSTOP)
        if any(state != "T" for state in thread_states(pid)):
            raise RuntimeError("Shell did not stop every thread; reapply")
        yield paused
    finally:
        try:
            if stopped and not paused.killed:
                try:
                    signal.pidfd_send_signal(descriptor, signal.SIGCONT)
                except ProcessLookupError:
                    pass  # The pinned process has already exited.
        finally:
            os.close(descriptor)


def active_shell(properties: dict[str, str]) -> bool:
    if properties["LoadState"] == "not-found" or properties["ActiveState"] in ("inactive", "failed"):
        return False
    if properties["LoadState"] != "loaded" or properties["ActiveState"] != "active":
        raise RuntimeError("Cannot refresh a shell in an unexpected or transitional state")
    return True


def replace_shell(env: dict[str, str], properties: dict[str, str]) -> int:
    # Any launches during daemon-reload are included in the final inspection.
    subprocess.run(["/usr/bin/systemctl", "--user", "daemon-reload"],
                   check=True, timeout=30, env=env)
    current = shell_properties(env)
    if (not active_shell(current) or current["MainPID"] != properties["MainPID"]
            or current["ControlGroup"] != properties["ControlGroup"]
            or current["Restart"] != "on-failure" or current["RestartPreventExitStatus"]
            or current["SuccessExitStatus"]
            or current["NeedDaemonReload"] != "no"):
        raise RuntimeError("Shell identity or restart policy changed before refresh")
    pid = int(current["MainPID"])
    started = process_ticks(pid)
    require_idle_cgroup(current)
    with paused_shell(pid, started) as paused:
        # Never wait while host trust/provenance presentation is frozen.
        if busy := busy_members(current):
            raise RuntimeError(
                f"Shell refresh refused: shell child PIDs {busy} appeared before "
                "the pause. Finish or close them, then reapply."
            )
        paused.terminate()
    # Existing on-failure policy performs the restart and observer cleanup.
    # We never start an inactive service or send a compositor/session job.
    deadline = time.monotonic() + 30
    while True:
        current = shell_properties(env)
        if current["ActiveState"] == "active" and current["LoadState"] == "loaded":
            new_pid = int(current["MainPID"])
            if (new_pid, process_ticks(new_pid)) != (pid, started):
                return new_pid
        if time.monotonic() >= deadline:
            raise RuntimeError("Shell did not restart with a new resident identity")
        time.sleep(0.1)


def refresh_quickshell(env: dict[str, str]) -> dict[str, bool | str]:
    with checkpoint(env, "quickshell") as saved:
        properties = shell_properties(env)
        if not active_shell(properties):
            return {"changed": False, "status": "shell-inactive"}
        generation = source_generation("quickshell")
        if saved.current(generation, int(properties["MainPID"])) and properties["NeedDaemonReload"] == "no":
            return {"changed": False, "status": "shell-current"}
        boundary = boot_ticks()
        new_pid = replace_shell(env, properties)
        if source_generation("quickshell") != generation:
            raise RuntimeError("Installed shell changed during refresh; reapply")
        saved.record(generation, boundary, new_pid)
        return {"changed": True, "status": "shell-refreshed"}


def control_center_connection(env: dict[str, str]) -> Any:
    from gi.repository import Gio

    # Authentication precedes calls and has no per-call timeout. Bound it
    # separately so an unresponsive user bus cannot hold an apply forever.
    cancellable = Gio.Cancellable.new()
    timer = threading.Timer(5, cancellable.cancel)
    timer.daemon = True
    timer.start()
    try:
        return Gio.DBusConnection.new_for_address_sync(
            env["DBUS_SESSION_BUS_ADDRESS"],
            Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
            | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,
            None, cancellable,
        )
    finally:
        timer.cancel()


def control_center_running(connection: Any) -> bool:
    from gi.repository import Gio, GLib

    reply = connection.call_sync(
        "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
        "NameHasOwner", GLib.Variant("(s)", (APP_ID,)), GLib.VariantType.new("(b)"),
        Gio.DBusCallFlags.NO_AUTO_START, 5000, None,
    )
    return reply.unpack()[0]


def control_center_pid(connection: Any) -> int:
    from gi.repository import Gio, GLib

    owner = connection.call_sync(
        "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
        "GetNameOwner", GLib.Variant("(s)", (APP_ID,)), GLib.VariantType.new("(s)"),
        Gio.DBusCallFlags.NO_AUTO_START, 5000, None,
    ).unpack()[0]
    return connection.call_sync(
        "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
        "GetConnectionUnixProcessID", GLib.Variant("(s)", (owner,)), GLib.VariantType.new("(u)"),
        Gio.DBusCallFlags.NO_AUTO_START, 5000, None,
    ).unpack()[0]


def refresh_control_center(env: dict[str, str]) -> dict[str, bool | str]:
    with checkpoint(env, "control-center") as saved:
        connection = control_center_connection(env)
        generation = source_generation("control-center")
        boundary = boot_ticks()
        if not control_center_running(connection):
            # An owner started after this observation loads the installed code.
            saved.record(generation, boundary)
            return {"changed": False, "status": "control-center-absent"}
        if saved.current(generation, control_center_pid(connection)):
            return {"changed": False, "status": "control-center-current"}
        subprocess.run(["/usr/bin/gapplication", "action", APP_ID, "quit"],
                       check=True, timeout=15, env=env)
        deadline = time.monotonic() + 10
        while control_center_running(connection):
            if time.monotonic() >= deadline:
                raise RuntimeError("HyperLab Control Center retained its old code after quit")
            time.sleep(0.1)
        if source_generation("control-center") != generation:
            raise RuntimeError("Installed Control Center changed during retirement; reapply")
        saved.record(generation, boundary)
        return {"changed": True, "status": "control-center-retired"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("surface", choices=("quickshell", "control-center"))
    args = parser.parse_args()
    env = session_environment()
    result: dict[str, bool | str] = {"changed": False, "status": "no-desktop-session"}
    if env is not None:
        if args.surface == "quickshell":
            result = refresh_quickshell(env)
        else:
            result = refresh_control_center(env)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
