#!/usr/bin/env python3
"""Typed unprivileged action bridge for the shared HyperLab Shell.

Two shapes cross this boundary and no third one exists:

  ACTIONS          a fixed identifier resolved to an immutable argument
                   vector this file owns; the caller supplies no value at all
  PARAMETERIZED    a reviewed operation that carries a single argument,
                   validated here against an explicit pattern before it is
                   ever placed in the vector

`app-launch` is the parameterized operation for host applications: its
argument is an id from APPLICATIONS, the reviewed catalogue in this file,
and it is resolved here to a root-owned desktop entry the package manager
installed; the argument vector carries that path, never the id or anything
else the caller sent. `applications` lists the catalogue entries present on
this host.

Nothing the shell collects from a user -- a query, a name, a path -- can reach
either shape, and every target is re-checked for root ownership before exec.
"""

from __future__ import annotations

import json
import os
import re
import stat
import sys
from pathlib import Path


ACTIONS: dict[str, tuple[str, ...]] = {
    "keyboard-cycle": (
        "/usr/local/bin/privatestack-keyboard",
        "cycle",
    ),
    "wallpaper-mode-toggle": (
        "/usr/local/bin/privatestack-theme",
        "mode-toggle",
    ),
    # Chooses what keyboard RGB follows; it never names an identity.
    "rgb-mode-toggle": (
        "/usr/local/bin/privatestack-theme",
        "rgb-mode-toggle",
    ),
    "theme-cycle": (
        "/usr/local/bin/privatestack-theme",
        "cycle",
    ),
    # Focused-window fullscreen and opacity are deliberately absent. They
    # act on whatever the compositor reports as focused when they run, not
    # on a captured target, so they stay on the compositor shortcuts until a
    # target-bound operation is reviewed.
    #
    # Raise the already-open HyperLab workspace window. No argument: the
    # adapter identifies the window by its owning shell process.
    "workspace-window-focus": (
        "/usr/local/bin/privatestack-compositor-adapter",
        "shell-window-focus",
    ),
    "session-lock": (
        "/usr/local/bin/privatestack-lock",
    ),
    "session-suspend": (
        "/usr/bin/systemctl",
        "suspend",
    ),
    "session-logout": (
        "/usr/local/bin/privatestack-compositor-adapter",
        "session-exit",
    ),
    "session-reboot": (
        "/usr/bin/systemctl",
        "reboot",
    ),
    "session-poweroff": (
        "/usr/bin/systemctl",
        "poweroff",
    ),
    "audio-mute-toggle": (
        "/usr/bin/wpctl",
        "set-mute",
        "@DEFAULT_AUDIO_SINK@",
        "toggle",
    ),
    "audio-volume-up": (
        "/usr/bin/wpctl",
        "set-volume",
        "-l",
        "1.25",
        "@DEFAULT_AUDIO_SINK@",
        "5%+",
    ),
    "audio-volume-down": (
        "/usr/bin/wpctl",
        "set-volume",
        "@DEFAULT_AUDIO_SINK@",
        "5%-",
    ),
}


# The reviewed host applications the shell may start (roadmap milestone 8).
# Each id names a desktop entry under APPLICATIONS_DIR; the list is the
# review. Every entry here is also started by a reviewed host key today.
APPLICATIONS: tuple[str, ...] = (
    "foot",
    "nemo",
)
APPLICATIONS_DIR = Path("/usr/share/applications")
TRUSTED_UID = 0


# The reviewed operations that accept a value. The pattern is the whole
# contract for workspace-select, which the compositor adapter validates
# again; app-launch is resolved further by application_entry.
PARAMETERIZED: dict[str, tuple[tuple[str, ...], str]] = {
    "workspace-select": (
        (
            "/usr/local/bin/privatestack-compositor-adapter",
            "workspace-select",
        ),
        r"^[1-9]$",
    ),
    "app-launch": (
        (
            "/usr/bin/gio",
            "launch",
        ),
        r"^[a-z0-9][a-z0-9._-]{0,95}$",
    ),
}


def application_entry(identifier: str) -> Path | None:
    """A catalogue id's desktop entry, only if the session cannot change it."""
    if identifier not in APPLICATIONS:
        return None
    path = APPLICATIONS_DIR / f"{identifier}.desktop"
    try:
        if path.is_symlink():
            return None
        metadata = path.stat()
    except OSError:
        return None
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != TRUSTED_UID or metadata.st_mode & 0o022:
        return None
    return path


def entry_fields(path: Path) -> dict[str, str]:
    """The unlocalised Name and Icon of a desktop entry's main group."""
    fields: dict[str, str] = {}
    group = None
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            group = line[1:-1]
        elif group == "Desktop Entry" and "=" in line:
            key, value = line.split("=", 1)
            if key in ("Name", "Icon") and key not in fields:
                fields[key] = value.strip()[:80]
    return fields


def applications() -> int:
    """List the catalogue entries present and trusted on this host."""
    listed = []
    for identifier in APPLICATIONS:
        path = application_entry(identifier)
        if path is None:
            continue
        fields = entry_fields(path)
        listed.append({
            "id": identifier,
            "name": fields.get("Name") or identifier,
            "icon": fields.get("Icon", ""),
        })
    print(json.dumps({"applications": listed}, separators=(",", ":")))
    return 0


def trusted_target(path: Path) -> bool:
    """Require one executable target immutable by the desktop session."""
    try:
        if path.is_symlink():
            return False
        metadata = path.stat()
    except OSError:
        return False

    return (
        stat.S_ISREG(metadata.st_mode)
        and metadata.st_uid == 0
        and metadata.st_mode & 0o022 == 0
        and os.access(path, os.X_OK)
    )


def probe() -> int:
    """Report whether every reviewed target passes ownership checks."""
    availability = {
        action: trusted_target(Path(argv[0]))
        for action, argv in ACTIONS.items()
    }

    availability.update({
        action: trusted_target(Path(argv[0]))
        for action, (argv, _pattern) in PARAMETERIZED.items()
    })

    print(
        json.dumps(
            {
                "actions": availability,
                "all_available": all(availability.values()),
            },
            separators=(",", ":"),
        )
    )

    return 0 if all(availability.values()) else 1


def resolve(argument: list[str]) -> tuple[str, ...] | None:
    """Resolve one reviewed invocation into its immutable argument vector."""
    action = argument[0]

    if action in ACTIONS:
        if len(argument) != 1:
            print(
                f"HyperLab: rejected arguments for fixed action: {action}",
                file=sys.stderr,
            )
            return None

        return ACTIONS[action]

    entry = PARAMETERIZED.get(action)

    if entry is None:
        print(
            f"HyperLab: rejected unknown shell action: {action}",
            file=sys.stderr,
        )
        return None

    argv, pattern = entry

    if len(argument) != 2 or not re.fullmatch(pattern, argument[1]):
        print(
            f"HyperLab: rejected invalid argument for action: {action}",
            file=sys.stderr,
        )
        return None

    if action == "app-launch":
        path = application_entry(argument[1])
        if path is None:
            print(
                "HyperLab: rejected an application outside the reviewed "
                f"catalogue or not installed: {argument[1]}",
                file=sys.stderr,
            )
            return None
        return (*argv, str(path))

    return (*argv, argument[1])


def main() -> int:
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        allowed = "|".join((*ACTIONS, *PARAMETERIZED, "probe", "applications"))
        print(
            f"usage: privatestack-shell-actions {{{allowed}}}",
            file=sys.stderr,
        )
        return 2

    if sys.argv[1] == "probe":
        if len(sys.argv) != 2:
            print(
                "usage: privatestack-shell-actions probe",
                file=sys.stderr,
            )
            return 2

        return probe()

    if sys.argv[1] == "applications":
        if len(sys.argv) != 2:
            print(
                "usage: privatestack-shell-actions applications",
                file=sys.stderr,
            )
            return 2

        return applications()

    argv = resolve(sys.argv[1:])

    if argv is None:
        return 2

    executable = Path(argv[0])

    if not trusted_target(executable):
        print(
            "HyperLab: rejected unavailable or untrusted target: "
            f"{executable}",
            file=sys.stderr,
        )
        return 126

    os.execv(argv[0], list(argv))
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
