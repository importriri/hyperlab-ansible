#!/usr/bin/env python3
"""Typed unprivileged action bridge for the shared HyperLab Shell."""

from __future__ import annotations

import json
import os
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
    "controls-open": (
        "/usr/local/bin/privatestack-controls",
        "menu",
    ),
}


def trusted_target(path: Path) -> bool:
    """Require one immutable-by-session executable owned by root."""
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
    availability = {
        action: trusted_target(Path(argv[0]))
        for action, argv in ACTIONS.items()
    }

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


def main() -> int:
    if len(sys.argv) != 2:
        print(
            "usage: privatestack-shell-actions "
            "{keyboard-cycle|wallpaper-mode-toggle|controls-open|probe}",
            file=sys.stderr,
        )
        return 2

    action = sys.argv[1]

    if action == "probe":
        return probe()

    argv = ACTIONS.get(action)

    if argv is None:
        print(
            f"HyperLab: rejected unknown shell action: {action}",
            file=sys.stderr,
        )
        return 2

    executable = Path(argv[0])

    if not trusted_target(executable):
        print(
            f"HyperLab: rejected unavailable or untrusted target: "
            f"{executable}",
            file=sys.stderr,
        )
        return 126

    os.execv(argv[0], list(argv))
    return 127


if __name__ == "__main__":
    raise SystemExit(main())
