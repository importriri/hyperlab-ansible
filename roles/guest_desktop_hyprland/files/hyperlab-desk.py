#!/usr/bin/python3
"""Desks and projects for the HyperLab guest workstation.

A Desk groups related work inside one guest. A Project is a named slot of a
Desk with a working directory and the programs that open it. Both are
organisation only: every Desk shares the same machine, network and trust, and
nothing here changes what the guest may reach.

The mapping onto Hyprland is fixed and has no hidden state: Desk ``d`` owns
workspaces ``d*10+1`` to ``d*10+9`` and slot ``s`` of that Desk is workspace
``d*10+s``. The current Desk and Project are therefore always read back from
the compositor's active workspace, never remembered separately.

Configuration, first match wins:

    $XDG_CONFIG_HOME/hyperlab-workspace/desks.json   the user's own Desks
    /etc/hyperlab-workspace/desks.json               the image default
    built-in defaults                                last resort

A configuration that does not validate is never half-applied: the model
falls back to the next source and reports the error, so the shell can say
that the user's file was refused instead of silently showing other Desks.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

VERSION = 1
MAX_DESKS = 9
SLOTS = range(1, 10)
MAX_NAME = 40
MAX_BLURB = 140
MAX_LAUNCH = 8
MAX_COMMAND = 512

HOME = Path.home()
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config")
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME") or HOME / ".local/state")
USER_CONFIG = CONFIG_HOME / "hyperlab-workspace/desks.json"
SYSTEM_CONFIG = Path(
    os.environ.get("HYPERLAB_DESK_SYSTEM_CONFIG")
    or "/etc/hyperlab-workspace/desks.json"
)
STATE_FILE = STATE_HOME / "hyperlab-workspace/desks-state.json"

BUILTIN = {
    "version": VERSION,
    "desks": [
        {
            "name": "Programming",
            "blurb": "Code, repositories and the terminals around them.",
            "projects": [],
        },
        {
            "name": "3D Design",
            "blurb": "Blender and CAD, with the GPU when the machine has one.",
            "projects": [],
        },
        {
            "name": "Research",
            "blurb": "Reading, notes and documentation.",
            "projects": [],
        },
        {
            "name": "Systems",
            "blurb": "Ansible, networking and infrastructure work.",
            "projects": [],
        },
    ],
}


class DeskError(Exception):
    """A request or a configuration that must be refused."""


# --------------------------------------------------------------------------
# Validation


def clean_text(value: Any, field: str, limit: int, required: bool) -> str:
    if value is None and not required:
        return ""
    if not isinstance(value, str):
        raise DeskError(f"{field} must be text")
    text = " ".join(value.split())
    if required and not text:
        raise DeskError(f"{field} must not be empty")
    if len(text) > limit:
        raise DeskError(f"{field} is longer than {limit} characters")
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        raise DeskError(f"{field} contains control characters")
    return text


def clean_cwd(value: Any, field: str) -> str:
    if value in (None, ""):
        return "~"
    if not isinstance(value, str) or "\n" in value or "\0" in value:
        raise DeskError(f"{field} must be one path")
    if not (value == "~" or value.startswith("~/") or value.startswith("/")):
        raise DeskError(f"{field} must be absolute or start with ~/")
    if len(value) > 4096:
        raise DeskError(f"{field} is too long")
    return value


def clean_launch(value: Any, field: str) -> list[str]:
    if value is None:
        return ["kitty"]
    if not isinstance(value, list) or len(value) > MAX_LAUNCH:
        raise DeskError(f"{field} must be a list of at most {MAX_LAUNCH} commands")
    commands = []
    for index, command in enumerate(value):
        if not isinstance(command, str) or not command.strip():
            raise DeskError(f"{field}[{index}] must be a command")
        if "\n" in command or "\0" in command or len(command) > MAX_COMMAND:
            raise DeskError(f"{field}[{index}] must be one short line")
        commands.append(command.strip())
    return commands


def validate(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise DeskError("the configuration must be a JSON object")
    if data.get("version") != VERSION:
        raise DeskError(f"version must be {VERSION}")
    desks = data.get("desks")
    if not isinstance(desks, list) or not 1 <= len(desks) <= MAX_DESKS:
        raise DeskError(f"desks must list between 1 and {MAX_DESKS} Desks")

    normalized = []
    seen_desks: set[str] = set()
    for desk_index, desk in enumerate(desks, start=1):
        where = f"desks[{desk_index - 1}]"
        if not isinstance(desk, dict):
            raise DeskError(f"{where} must be an object")
        name = clean_text(desk.get("name"), f"{where}.name", MAX_NAME, True)
        if name.casefold() in seen_desks:
            raise DeskError(f"Desk {name!r} appears twice")
        seen_desks.add(name.casefold())
        blurb = clean_text(desk.get("blurb"), f"{where}.blurb", MAX_BLURB, False)

        projects = desk.get("projects", [])
        if not isinstance(projects, list) or len(projects) > len(SLOTS):
            raise DeskError(f"{where}.projects must list at most 9 projects")
        slots: set[int] = set()
        names: set[str] = set()
        cleaned = []
        for project_index, project in enumerate(projects):
            pwhere = f"{where}.projects[{project_index}]"
            if not isinstance(project, dict):
                raise DeskError(f"{pwhere} must be an object")
            slot = project.get("slot")
            if not isinstance(slot, int) or isinstance(slot, bool) or slot not in SLOTS:
                raise DeskError(f"{pwhere}.slot must be a number from 1 to 9")
            if slot in slots:
                raise DeskError(f"{where} uses slot {slot} twice")
            slots.add(slot)
            pname = clean_text(project.get("name"), f"{pwhere}.name", MAX_NAME, True)
            if pname.casefold() in names:
                raise DeskError(f"{where} has two projects named {pname!r}")
            names.add(pname.casefold())
            cleaned.append({
                "slot": slot,
                "name": pname,
                "cwd": clean_cwd(project.get("cwd"), f"{pwhere}.cwd"),
                "launch": clean_launch(project.get("launch"), f"{pwhere}.launch"),
            })
        cleaned.sort(key=lambda item: item["slot"])
        normalized.append({
            "index": desk_index,
            "name": name,
            "blurb": blurb,
            "projects": cleaned,
        })
    return {"version": VERSION, "desks": normalized}


def load_model() -> dict[str, Any]:
    """Return the first valid configuration and any refusal on the way."""
    errors = []
    for source, path in (("user", USER_CONFIG), ("system", SYSTEM_CONFIG)):
        if not path.is_file():
            continue
        try:
            model = validate(json.loads(path.read_text()))
        except (OSError, ValueError, DeskError) as error:
            errors.append(f"{path}: {error}")
            continue
        model.update(source=source, path=str(path), errors=errors)
        return model
    model = validate(BUILTIN)
    model.update(source="builtin", path="", errors=errors)
    return model


def storable(model: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": VERSION,
        "desks": [
            {
                "name": desk["name"],
                "blurb": desk["blurb"],
                "projects": [
                    {key: project[key] for key in ("slot", "name", "cwd", "launch")}
                    for project in desk["projects"]
                ],
            }
            for desk in model["desks"]
        ],
    }


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(name, 0o644)
        os.replace(name, path)
    except BaseException:
        if os.path.exists(name):
            os.unlink(name)
        raise


class ConfigLock:
    """Serialise writers; readers only ever see a whole file."""

    def __enter__(self) -> ConfigLock:
        USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(USER_CONFIG.parent / ".desks.lock", "w")
        fcntl.flock(self.handle, fcntl.LOCK_EX)
        return self

    def __exit__(self, *_: object) -> None:
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()


def editable_model() -> dict[str, Any]:
    model = load_model()
    if model["errors"] and model["source"] != "user" and USER_CONFIG.exists():
        # Never overwrite a file the user wrote just because it is invalid.
        raise DeskError(
            "your desks.json was refused, fix it before changing Desks: "
            + model["errors"][0]
        )
    return model


# --------------------------------------------------------------------------
# Compositor


def hyprctl_json(*args: str) -> Any:
    result = subprocess.run(
        ["hyprctl", "-j", *args],
        capture_output=True, text=True, timeout=5, check=False,
    )
    if result.returncode != 0:
        raise DeskError("hyprctl is not reachable; is Hyprland running?")
    try:
        return json.loads(result.stdout)
    except ValueError as error:
        raise DeskError(f"hyprctl returned unreadable output: {error}") from None


def dispatch(*args: str) -> None:
    result = subprocess.run(
        ["hyprctl", "dispatch", *args],
        capture_output=True, text=True, timeout=5, check=False,
    )
    if result.returncode != 0 or result.stdout.strip() not in ("", "ok"):
        raise DeskError(
            "Hyprland refused: " + (result.stdout.strip() or result.stderr.strip())
        )


def split_workspace(workspace: int) -> tuple[int, int] | None:
    desk, slot = divmod(workspace, 10)
    if 1 <= desk <= MAX_DESKS and slot in SLOTS:
        return desk, slot
    return None


def active_workspace() -> int:
    data = hyprctl_json("activeworkspace")
    workspace = data.get("id") if isinstance(data, dict) else None
    if not isinstance(workspace, int):
        raise DeskError("Hyprland did not report an active workspace")
    return workspace


def window_counts() -> dict[int, int]:
    data = hyprctl_json("workspaces")
    counts = {}
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("id"), int):
                counts[item["id"]] = int(item.get("windows") or 0)
    return counts


def load_state() -> dict[str, Any]:
    try:
        data = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def remember_slot(workspace: int) -> None:
    position = split_workspace(workspace)
    if position is None:
        return
    state = load_state()
    last = state.get("last_slot") if isinstance(state.get("last_slot"), dict) else {}
    last[str(position[0])] = position[1]
    state["last_slot"] = last
    try:
        write_json(STATE_FILE, state)
    except OSError:
        pass  # Returning to slot 1 is the only consequence.


def last_slot(desk: int) -> int:
    last = load_state().get("last_slot")
    slot = last.get(str(desk)) if isinstance(last, dict) else None
    return slot if isinstance(slot, int) and slot in SLOTS else 1


def desk_count(model: dict[str, Any]) -> int:
    return len(model["desks"])


def require_desk(model: dict[str, Any], desk: int) -> dict[str, Any]:
    if not 1 <= desk <= desk_count(model):
        raise DeskError(f"there is no Desk {desk}; this machine has {desk_count(model)}")
    return model["desks"][desk - 1]


def current_desk(workspace: int) -> int:
    position = split_workspace(workspace)
    return position[0] if position else 1


# --------------------------------------------------------------------------
# Commands


def describe(model: dict[str, Any], workspace: int | None) -> dict[str, Any]:
    position = split_workspace(workspace) if workspace is not None else None
    desk = project = None
    if position and position[0] <= desk_count(model):
        desk = model["desks"][position[0] - 1]
        project = next(
            (item for item in desk["projects"] if item["slot"] == position[1]),
            None,
        )
    return {
        "workspace": workspace,
        "desk": position[0] if position else None,
        "slot": position[1] if position else None,
        "desk_name": desk["name"] if desk else "",
        "project_name": project["name"] if project else "",
    }


def command_model(_: argparse.Namespace) -> dict[str, Any]:
    return load_model()


def command_status(_: argparse.Namespace) -> dict[str, Any]:
    model = load_model()
    status = describe(model, active_workspace())
    status["windows"] = {str(key): value for key, value in window_counts().items()}
    return status


def command_lock_label(_: argparse.Namespace) -> str:
    try:
        status = describe(load_model(), active_workspace())
    except DeskError:
        return "HyperLab Workstation"
    if not status["desk_name"]:
        return "HyperLab Workstation"
    place = status["desk_name"]
    if status["project_name"]:
        place += " / " + status["project_name"]
    return "HyperLab Workstation · Desk " + place


def go_desk(model: dict[str, Any], desk: int, current: int) -> dict[str, Any]:
    require_desk(model, desk)
    remember_slot(current)
    target = desk * 10 + last_slot(desk)
    if target != current:
        dispatch("workspace", str(target))
    return describe(model, target)


def command_desk(args: argparse.Namespace) -> dict[str, Any]:
    model = load_model()
    return go_desk(model, args.desk, active_workspace())


def command_desk_step(args: argparse.Namespace) -> dict[str, Any]:
    model = load_model()
    current = active_workspace()
    count = desk_count(model)
    desk = (current_desk(current) - 1 + args.step) % count + 1
    return go_desk(model, desk, current)


def command_workspace(args: argparse.Namespace) -> dict[str, Any]:
    model = load_model()
    current = active_workspace()
    target = current_desk(current) * 10 + args.slot
    if target != current:
        dispatch("workspace", str(target))
    remember_slot(target)
    return describe(model, target)


def command_move_workspace(args: argparse.Namespace) -> dict[str, Any]:
    model = load_model()
    target = current_desk(active_workspace()) * 10 + args.slot
    dispatch("movetoworkspace", str(target))
    remember_slot(target)
    return describe(model, target)


def command_move_desk(args: argparse.Namespace) -> dict[str, Any]:
    model = load_model()
    require_desk(model, args.desk)
    target = args.desk * 10 + last_slot(args.desk)
    remember_slot(active_workspace())
    dispatch("movetoworkspace", str(target))
    return describe(model, target)


def launch_line(workspace: int, cwd: str, command: str) -> str:
    directory = os.path.expanduser(cwd)
    return (
        f"[workspace {workspace}] cd -- {shlex.quote(directory)} 2>/dev/null; "
        f"exec {command}"
    )


def command_project_open(args: argparse.Namespace) -> dict[str, Any]:
    model = load_model()
    desk = require_desk(model, args.desk)
    project = next(
        (item for item in desk["projects"] if item["slot"] == args.slot), None
    )
    if project is None:
        raise DeskError(f"Desk {desk['name']} has no project in slot {args.slot}")
    target = args.desk * 10 + args.slot
    current = active_workspace()
    remember_slot(current)
    if target != current:
        dispatch("workspace", str(target))
    remember_slot(target)
    launched = 0
    if window_counts().get(target, 0) == 0:
        for command in project["launch"]:
            dispatch("exec", launch_line(target, project["cwd"], command))
            launched += 1
    result = describe(model, target)
    result["launched"] = launched
    return result


def command_project_new(args: argparse.Namespace) -> dict[str, Any]:
    with ConfigLock():
        model = editable_model()
        desk = require_desk(model, args.desk)
        name = clean_text(args.name, "project name", MAX_NAME, True)
        if any(item["name"].casefold() == name.casefold() for item in desk["projects"]):
            raise DeskError(f"Desk {desk['name']} already has a project named {name!r}")
        used = {item["slot"] for item in desk["projects"]}
        if args.slot is not None:
            if args.slot not in SLOTS or args.slot in used:
                raise DeskError(f"slot {args.slot} is not free on Desk {desk['name']}")
            slot = args.slot
        else:
            free = [slot for slot in SLOTS if slot not in used]
            if not free:
                raise DeskError(f"Desk {desk['name']} already has nine projects")
            slot = free[0]
        desk["projects"].append({
            "slot": slot,
            "name": name,
            "cwd": clean_cwd(args.cwd, "cwd"),
            "launch": clean_launch(args.launch or None, "launch"),
        })
        validated = validate(storable(model))
        write_json(USER_CONFIG, storable(validated))
    return {"desk": args.desk, "slot": slot, "name": name}


def command_project_remove(args: argparse.Namespace) -> dict[str, Any]:
    with ConfigLock():
        model = editable_model()
        desk = require_desk(model, args.desk)
        kept = [item for item in desk["projects"] if item["slot"] != args.slot]
        if len(kept) == len(desk["projects"]):
            raise DeskError(f"Desk {desk['name']} has no project in slot {args.slot}")
        desk["projects"] = kept
        write_json(USER_CONFIG, storable(validate(storable(model))))
    return {"desk": args.desk, "slot": args.slot, "removed": True}


def command_check(args: argparse.Namespace) -> dict[str, Any]:
    model = validate(json.loads(Path(args.path).read_text()))
    return {"valid": True, "desks": len(model["desks"])}


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        prog="hyperlab-desk",
        description="Desks and projects of the HyperLab guest workstation.",
    )
    commands = root.add_subparsers(dest="command", required=True)

    def add(name: str, handler: Any, help_text: str) -> argparse.ArgumentParser:
        sub = commands.add_parser(name, help=help_text)
        sub.set_defaults(handler=handler)
        return sub

    add("model", command_model, "print the validated Desks and projects")
    add("status", command_status, "print where the active workspace sits")
    add("lock-label", command_lock_label, "one line for the lock screen")
    add("desk", command_desk, "go to Desk N").add_argument("desk", type=int)
    add("desk-next", command_desk_step, "go to the next Desk").set_defaults(step=1)
    add("desk-prev", command_desk_step, "go to the previous Desk").set_defaults(step=-1)
    add("workspace", command_workspace, "go to slot N of this Desk").add_argument(
        "slot", type=int, choices=SLOTS)
    add("move-to-workspace", command_move_workspace,
        "move the focused window to slot N of this Desk").add_argument(
        "slot", type=int, choices=SLOTS)
    add("move-to-desk", command_move_desk,
        "move the focused window to Desk N").add_argument("desk", type=int)

    opened = add("project-open", command_project_open, "open a project")
    opened.add_argument("desk", type=int)
    opened.add_argument("slot", type=int, choices=SLOTS)

    new = add("project-new", command_project_new, "add a project to a Desk")
    new.add_argument("desk", type=int)
    new.add_argument("name")
    new.add_argument("--slot", type=int)
    new.add_argument("--cwd")
    new.add_argument("--launch", action="append",
                     help="a command that opens the project; repeat for more")

    removed = add("project-remove", command_project_remove, "remove a project")
    removed.add_argument("desk", type=int)
    removed.add_argument("slot", type=int, choices=SLOTS)

    add("check", command_check, "validate a desks.json file").add_argument("path")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = args.handler(args)
    except (DeskError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"hyperlab-desk: {error}", file=sys.stderr)
        return 2
    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
