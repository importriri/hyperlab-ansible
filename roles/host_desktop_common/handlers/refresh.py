#!/usr/bin/env python3
"""Refresh installed presentation code in an existing desktop user's session."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess
import threading
import time
from typing import Any

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
    ("/usr/local/bin/privatestack-surface-provenance", "stream"),
    ("/usr/local/bin/privatestack-telemetry", "snapshot"),
})
# How the bridges' "#!/usr/bin/env bash" or "python3" shebangs appear in argv.
INTERPRETERS = frozenset({(), ("bash",), ("python3",), ("/usr/bin/env", "bash"),
                          ("/usr/bin/env", "python3")})
IDLE_WAIT_SECONDS = 10


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


def regular_file_ns(path: Path) -> int:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise RuntimeError(f"Installed source is not an unredirected regular file: {path}")
    # ctime also detects atomic replacements that preserve an older mtime.
    return max(info.st_mtime_ns, info.st_ctime_ns)


def installed_shell_ns() -> int:
    def newest(directory: Path) -> int:
        if not stat.S_ISDIR(directory.lstat().st_mode):
            raise RuntimeError(f"Redirected shell directory: {directory}")
        latest = 0
        for path in directory.iterdir():
            info = path.lstat()
            if stat.S_ISDIR(info.st_mode):
                latest = max(latest, newest(path))
            else:
                stamp = regular_file_ns(path)
                # This runtime-data file has its own live FileView observer.
                if path != SHELL_ROOT / "features.json":
                    latest = max(latest, stamp)
        return latest

    regular_file_ns(SHELL_ROOT / "shell.qml")
    return max(newest(SHELL_ROOT), regular_file_ns(UNIT_PATH))


def process_started_ns(pid: int) -> int:
    if pid <= 0:
        raise RuntimeError("Missing resident process PID")
    directory = PROC_ROOT / str(pid)
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError("Resident process is redirected or belongs to another user")
    # /proc/PID/stat field 22 is boot-relative ticks, including suspend.
    # comm (field 2) can itself contain spaces and closing parentheses.
    path = directory / "stat"
    regular_file_ns(path)
    fields = path.read_text().rpartition(") ")[2].split()
    try:
        ticks = int(fields[19])
    except (IndexError, ValueError) as exc:
        raise RuntimeError("Cannot read resident process start time") from exc
    rate = os.sysconf("SC_CLK_TCK")
    realtime = time.time_ns()
    boot = time.clock_gettime_ns(time.CLOCK_BOOTTIME)
    started = ticks * 1_000_000_000 // rate
    if ticks <= 0 or started > boot:
        raise RuntimeError("Invalid resident process start time")
    return realtime - boot + started


def shell_properties(env: dict[str, str]) -> dict[str, str]:
    names = ("LoadState", "ActiveState", "MainPID", "ControlGroup", "NeedDaemonReload")
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
        regular_file_ns(membership)
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


def resident_observer(argv: tuple[str, ...]) -> bool:
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


def refresh_quickshell(env: dict[str, str]) -> dict[str, bool | str]:
    properties = shell_properties(env)
    if properties["LoadState"] == "not-found" or properties["ActiveState"] in ("inactive", "failed"):
        return {"changed": False, "status": "shell-inactive"}
    if properties["LoadState"] != "loaded" or properties["ActiveState"] != "active":
        raise RuntimeError("Cannot refresh a shell in an unexpected or transitional state")
    started = process_started_ns(int(properties["MainPID"]))
    if installed_shell_ns() < started and properties["NeedDaemonReload"] == "no":
        return {"changed": False, "status": "shell-current"}
    require_idle_cgroup(properties)
    # Reload only for an actual stale resident. The unit is copied by a later
    # play; its time is compared here, so the next apply picks it up.
    subprocess.run(["/usr/bin/systemctl", "--user", "daemon-reload"],
                   check=True, timeout=30, env=env)
    # try-restart also guards against the service stopping after the probe.
    subprocess.run(["/usr/bin/systemctl", "--user", "try-restart", UNIT],
                   check=True, timeout=30, env=env)
    subprocess.run(["/usr/bin/systemctl", "--user", "is-active", "--quiet", UNIT],
                   check=True, timeout=10, env=env)
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
    connection = control_center_connection(env)
    if not control_center_running(connection):
        return {"changed": False, "status": "control-center-absent"}
    started = process_started_ns(control_center_pid(connection))
    if regular_file_ns(CONTROL_CENTER_PATH) < started:
        return {"changed": False, "status": "control-center-current"}
    # Existing versions already export quit. A theme refresh would retain the
    # old Python code, and launching --warm would need the compositor's env.
    subprocess.run(["/usr/bin/gapplication", "action", APP_ID, "quit"],
                   check=True, timeout=15, env=env)
    deadline = time.monotonic() + 10
    while control_center_running(connection):
        if time.monotonic() >= deadline:
            raise RuntimeError("HyperLab Control Center retained its old code after quit")
        time.sleep(0.1)
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
