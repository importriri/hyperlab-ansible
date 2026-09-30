#!/usr/bin/env python3
"""Typed machine-operation boundary for the HyperLab shell.

Two questions cross this boundary, and nothing else does:

  capabilities NAME   what may be done to this machine right now, and why not
  VERB NAME           do exactly one reviewed operation to this machine

Both answers are derived from live state every time: the live libvirt
inventory, the checked HyperLab spec, the strict runtime SSH inventory and the
reviewed action registry. The shell never reconstructs these rules, and a
capability answer is advice for presentation only -- this bridge re-derives
everything before it acts.

Every response is one JSON object on stdout so the shell reads structure
instead of prose. Managed lifecycle reports correlated durable operation records, never spawn success.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any

HYPERLABCTL = "/usr/local/bin/hyperlabctl"
OPERATION = "/usr/local/bin/privatestack-operation"
CHECKOUT_POINTER = Path("/etc/hyperlabctl/checkout")

VERBS = (
    "start",
    "shutdown",
    "reboot",
    "console",
    "ssh",
    "looking-glass",
    "force-stop",
)

# Operations that hand the guest a signal it cannot negotiate. The shell
# confirms them and the registry enforces them; both layers apply.
DESTRUCTIVE_VERBS = ("force-stop",)

# Transports. Each one becomes the client process it opens, so the shell owns
# one runner per open connection and never serializes lifecycle behind them.
CONNECTION_VERBS = ("console", "ssh", "looking-glass")

# Actions that are launched in their own terminal and outlive this process.
DETACHED_PREFIXES = ("vm.managed-",)
DETACHED_ACTIONS = ("vm.force-stop",)

# libvirt states from which a start is meaningful. Anything else -- paused,
# in shutdown, pmsuspended, unknown -- is reported as such, never as
# "startable" by elimination.
STARTABLE_STATES = ("shut off", "crashed")


class Refused(RuntimeError):
    pass


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, separators=(",", ":")), flush=True)


def cli_json(*args: str) -> Any:
    result = subprocess.run(
        [HYPERLABCTL, "--json", *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=15,
    )
    if result.returncode:
        raise Refused(
            result.stderr.strip()
            or result.stdout.strip()
            or "hyperlabctl request failed"
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise Refused("invalid hyperlabctl JSON") from exc


def live_machine(name: str) -> dict[str, Any]:
    rows = cli_json("vm", "list")
    if not isinstance(rows, list):
        raise Refused("invalid live machine inventory")

    matches = [
        row for row in rows
        if isinstance(row, dict) and row.get("name") == name
    ]
    if len(matches) != 1:
        raise Refused("machine is not uniquely present in live inventory")
    return matches[0]


def managed_spec(name: str) -> dict[str, Any] | None:
    rows = cli_json("compose", "list")
    if not isinstance(rows, list):
        raise Refused("invalid HyperLab spec inventory")

    matches = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        spec = row.get("spec")
        if isinstance(spec, dict) and spec.get("name") == name:
            matches.append(row)

    if len(matches) > 1:
        raise Refused("machine maps to more than one HyperLab spec")

    return matches[0] if matches else None


def resolve(
    action_id: str,
    name: str,
    spec_row: dict[str, Any] | None,
) -> list[str]:
    args = ["actions", "--resolve", action_id]

    if action_id in {
        "vm.console",
        "vm.ssh",
        "vm.looking-glass",
        "vm.start",
        "vm.stop",
    }:
        args += ["--domain", name]
    else:
        if spec_row is None:
            raise Refused("managed action has no HyperLab spec")
        path = spec_row.get("path")
        if not isinstance(path, str) or not path:
            raise Refused("managed spec has no validated path")
        args += ["--spec", path, "--domain", name]

    argv = cli_json(*args)
    if (
        not isinstance(argv, list)
        or not argv
        or not all(isinstance(part, str) and part for part in argv)
    ):
        raise Refused("registry returned an invalid command")
    return argv


def runtime_ssh_problem(name: str) -> str | None:
    """Mirror the reviewed open path's runtime SSH inventory policy.

    `hyperlabctl open ssh` (commands/open.py `_runtime_inventory`) requires a
    real runtime directory owned by this user, and a regular, non-symlink,
    user-owned, mode-0600 `<name>.ini` inside it. A missing file is not a
    refusal there: the open path publishes it from the managed spec. This
    answers the same question the same way, so the capability shown is the
    capability the open path will honour. Returns None when SSH may proceed.
    """
    runtime = Path(
        os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
    )
    try:
        info = runtime.lstat()
    except OSError:
        return "runtime directory is unavailable"
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        return "runtime directory is not a real directory"
    if info.st_uid != os.getuid():
        return "runtime directory is not owned by the current user"

    inventory = runtime / f"{name}.ini"
    try:
        info = inventory.lstat()
    except FileNotFoundError:
        # Published on demand by the open path from the managed spec.
        return None
    except OSError:
        return "cannot inspect runtime SSH inventory"
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        return "runtime SSH inventory is not a regular file"
    if info.st_uid != os.getuid():
        return "runtime SSH inventory has the wrong owner"
    if stat.S_IMODE(info.st_mode) != 0o600:
        return "runtime SSH inventory has the wrong mode"
    return None


def managed_identity(
    machine: dict[str, Any],
    spec_row: dict[str, Any] | None,
) -> bool:
    """Whether this machine is HyperLab-managed, from both authorities.

    The live domain metadata and the checked spec inventory must agree. A
    managed domain whose spec cannot be found is not an external domain --
    offering it direct lifecycle would only be refused downstream -- and an
    unreadable domain is neither.
    """
    live = machine.get("managed")
    if live is not True and live is not False:
        raise Refused("managed status of this machine could not be read")
    if live and spec_row is None:
        raise Refused("this managed machine's HyperLab spec is unavailable")
    if not live and spec_row is not None:
        raise Refused("machine metadata and HyperLab spec disagree")
    return live


def choose_action(
    verb: str,
    name: str,
    machine: dict[str, Any],
    spec_row: dict[str, Any] | None,
) -> str:
    state = str(machine.get("state") or "unknown").lower()
    running = state == "running"

    if verb == "start":
        if running:
            raise Refused("machine is already running")
        if state not in STARTABLE_STATES:
            raise Refused("machine is %s, not shut off" % state)
        managed = managed_identity(machine, spec_row)
        return "vm.managed-start" if managed else "vm.start"

    if verb == "shutdown":
        if not running:
            raise Refused("machine is not running")
        managed = managed_identity(machine, spec_row)
        return "vm.managed-shutdown" if managed else "vm.stop"

    if verb == "reboot":
        if not running:
            raise Refused("reboot requires a running managed machine")
        if not managed_identity(machine, spec_row):
            raise Refused("reboot requires a running managed machine")
        return "vm.managed-reboot"

    if verb == "console":
        if not running:
            raise Refused("console requires a running machine")
        return "vm.console"

    if verb == "ssh":
        if not running:
            raise Refused("SSH requires a running managed machine")
        if not managed_identity(machine, spec_row):
            raise Refused("SSH requires a running managed machine")
        problem = runtime_ssh_problem(name)
        if problem is not None:
            raise Refused(problem)
        return "vm.ssh"

    if verb == "looking-glass":
        if not running:
            raise Refused("Looking Glass requires a running managed machine")
        if not managed_identity(machine, spec_row):
            raise Refused("Looking Glass requires a running managed machine")
        if machine.get("vfio") is not True:
            raise Refused("Looking Glass requires VFIO")

        spec = spec_row.get("spec")
        image = spec_row.get("image")
        if not isinstance(spec, dict) or not isinstance(image, dict):
            raise Refused("Looking Glass metadata is unavailable")
        if spec.get("looking_glass") is not True:
            raise Refused("Looking Glass is disabled by the machine spec")

        os_family = str(image.get("os_family") or "")
        mode = str(spec.get("looking_glass_mode") or "")
        if os_family != "windows" and mode != "linux-experimental":
            raise Refused("Looking Glass transport is not approved")

        return "vm.looking-glass"

    if verb == "force-stop":
        if not running:
            raise Refused("force stop requires a running managed machine")
        if not managed_identity(machine, spec_row):
            raise Refused("force stop requires a running managed machine")
        if machine.get("vfio") is not True:
            raise Refused("force stop is restricted to managed VFIO guests")
        return "vm.force-stop"

    raise Refused("unsupported machine operation")


def detached(action_id: str) -> bool:
    return action_id in DETACHED_ACTIONS or action_id.startswith(
        DETACHED_PREFIXES
    )


def capabilities(name: str) -> dict[str, Any]:
    """Answer what this machine can actually do, and why it cannot."""
    machine = live_machine(name)
    spec_row = managed_spec(name)

    verbs: dict[str, Any] = {}
    for verb in VERBS:
        try:
            action_id = choose_action(verb, name, machine, spec_row)
        except Refused as exc:
            verbs[verb] = {
                "available": False,
                "reason": str(exc),
                "action_id": None,
                "destructive": verb in DESTRUCTIVE_VERBS,
            }
            continue

        try:
            # A resolvable action is the only kind this bridge will run, so a
            # registry that cannot resolve it is a real unavailability.
            resolve(action_id, name, spec_row)
        except Refused as exc:
            verbs[verb] = {
                "available": False,
                "reason": str(exc),
                "action_id": action_id,
                "destructive": verb in DESTRUCTIVE_VERBS,
            }
            continue

        verbs[verb] = {
            "available": True,
            "reason": "",
            "action_id": action_id,
            "destructive": verb in DESTRUCTIVE_VERBS,
        }

    # What the libvirt console actually shows. A VFIO guest's desktop is on
    # its passed-through GPU (Looking Glass or the physical output); the
    # console is its emulated display, useful for boot and login recovery.
    # Unknown VFIO state claims neither.
    vfio = machine.get("vfio")
    verbs["console"]["display"] = (
        "emulated-recovery" if vfio is True
        else "primary" if vfio is False
        else "unknown"
    )

    live_managed = machine.get("managed")
    return {
        "phase": "capabilities",
        "machine": {
            "name": name,
            "state": str(machine.get("state") or "unknown"),
            # Tri-state: None when the domain's own metadata could not be
            # read, never a guessed False.
            "managed": live_managed if isinstance(live_managed, bool) else None,
            "spec": spec_row is not None,
            "vfio": machine.get("vfio") if isinstance(machine.get("vfio"), bool) else None,
        },
        "verbs": verbs,
    }


def checkout() -> str:
    value = CHECKOUT_POINTER.read_text(encoding="utf-8").strip()
    candidate = Path(value)
    if not candidate.is_absolute() or not candidate.is_dir():
        raise Refused("invalid HyperLab checkout")
    return str(candidate)


def privileged(action_id: str, name: str) -> None:
    # The runner re-resolves the action; argv never crosses this boundary.
    os.execv(OPERATION, [OPERATION, "launch", action_id, name])


def valid_name(name: str) -> None:
    if not name or len(name) > 255:
        raise Refused("invalid machine name")
    if any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise Refused("invalid machine name")


def main() -> int:
    if sys.argv[1:] == ["operations"]:
        os.execv(OPERATION, [OPERATION, "operations"])
    if len(sys.argv) == 3 and sys.argv[1] == "operation":
        os.execv(OPERATION, [OPERATION, "operation", sys.argv[2]])
    if len(sys.argv) == 3 and sys.argv[1] == "operation-view":
        # Reattach an observer; the runner validates the id and owns nothing new.
        os.execv(OPERATION, [OPERATION, "view", sys.argv[2]])
    if len(sys.argv) != 3:
        raise Refused("usage: machine-action {capabilities|VERB} MACHINE")

    verb = sys.argv[1]
    name = sys.argv[2]

    valid_name(name)

    if verb == "capabilities":
        emit(capabilities(name))
        return 0

    if verb not in VERBS:
        raise Refused("unsupported machine operation")

    machine = live_machine(name)
    spec_row = managed_spec(name)
    action_id = choose_action(verb, name, machine, spec_row)
    argv = resolve(action_id, name, spec_row)

    if detached(action_id):
        privileged(action_id, name)
        return 127

    emit({
        "phase": "accepted",
        "mode": "connection" if verb in CONNECTION_VERBS else "foreground",
        "verb": verb,
        "machine": name,
        "action_id": action_id,
    })

    os.execvp(argv[0], argv)
    return 127


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (Refused, OSError, subprocess.TimeoutExpired) as exc:
        emit({"phase": "refused", "reason": str(exc)})
        print(f"HyperLab: {exc}", file=sys.stderr)
        raise SystemExit(2) from None
