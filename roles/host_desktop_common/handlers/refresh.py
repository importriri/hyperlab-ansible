#!/usr/bin/env python3
"""Refresh installed presentation code in an existing desktop user's session."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import subprocess
import threading
import time
from typing import Any

UNIT = "hyperlab-quickshell.service"
APP_ID = "io.github.importriri.HyperlabControlCenter"


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
        print("No desktop user runtime; no resident surface refreshed")
        return None
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid()
            or stat.S_IMODE(info.st_mode) != 0o700):
        raise RuntimeError("Unsafe desktop user runtime directory")
    bus = runtime / "bus"
    try:
        info = bus.lstat()
    except FileNotFoundError:
        print("No desktop user bus; no resident surface refreshed")
        return None
    if not stat.S_ISSOCK(info.st_mode) or info.st_uid != os.getuid():
        raise RuntimeError("Unsafe desktop user bus")
    return dict(os.environ, XDG_RUNTIME_DIR=str(runtime),
                DBUS_SESSION_BUS_ADDRESS="unix:path=" + str(bus))


def refresh_quickshell(env: dict[str, str]) -> None:
    probe = ["/usr/bin/systemctl", "--user", "is-active", "--quiet", UNIT]
    state = subprocess.run(probe, check=False, timeout=10, env=env)
    if state.returncode in (3, 4):
        print("HyperLab shell is inactive; no shell started")
        return
    if state.returncode != 0:
        raise RuntimeError("Cannot inspect the running HyperLab shell")
    # try-restart also guards against the service stopping after the probe.
    # Keep the compositor and all other user services outside this operation.
    subprocess.run(["/usr/bin/systemctl", "--user", "try-restart", UNIT],
                   check=True, timeout=30, env=env)
    subprocess.run(probe, check=True, timeout=10, env=env)


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


def refresh_control_center(env: dict[str, str]) -> None:
    connection = control_center_connection(env)
    if not control_center_running(connection):
        print("HyperLab Control Center is absent; no application started")
        return
    # Existing versions already export quit. A theme refresh would retain the
    # old Python code, and launching --warm would need the compositor's env.
    subprocess.run(["/usr/bin/gapplication", "action", APP_ID, "quit"],
                   check=True, timeout=15, env=env)
    deadline = time.monotonic() + 10
    while control_center_running(connection):
        if time.monotonic() >= deadline:
            raise RuntimeError("HyperLab Control Center retained its old code after quit")
        time.sleep(0.1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("surface", choices=("quickshell", "control-center"))
    args = parser.parse_args()
    env = session_environment()
    if env is not None:
        if args.surface == "quickshell":
            refresh_quickshell(env)
        else:
            refresh_control_center(env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
