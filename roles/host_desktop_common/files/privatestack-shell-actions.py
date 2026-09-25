#!/usr/bin/env python3
"""Typed unprivileged action bridge for the shared HyperLab Shell.

Two shapes cross this boundary and no third one exists:

  ACTIONS          a fixed identifier resolved to an immutable argument
                   vector this file owns; the caller supplies no value at all
  PARAMETERIZED    one reviewed operation that carries a single argument,
                   validated here against an explicit pattern before it is
                   ever placed in the vector

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


# The one reviewed operation that accepts a value. The pattern is the whole
# contract: the compositor adapter validates the same slot again.
PARAMETERIZED: dict[str, tuple[tuple[str, ...], str]] = {
    "workspace-select": (
        (
            "/usr/local/bin/privatestack-compositor-adapter",
            "workspace-select",
        ),
        r"^[1-9]$",
    ),
}


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

    return (*argv, argument[1])


def main() -> int:
    if len(sys.argv) < 2 or len(sys.argv) > 3:
        allowed = "|".join((*ACTIONS, *PARAMETERIZED, "probe"))
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
