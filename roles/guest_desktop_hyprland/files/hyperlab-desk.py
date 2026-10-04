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

A Project also remembers which applications its workspace held when it was
left, as desktop entry ids and nothing else: never a process's arguments,
which can carry tokens. Opening an empty Project reopens those applications
from their desktop entries in the Project's folder, or its launch commands
when nothing usable was remembered.

A Desk can be quiet: while it is the current Desk, notifications are kept
out of sight (critical ones still show); those still pending show again when
another Desk comes to the front.
The notification daemon does the hiding through its ``do-not-disturb``
mode; this helper only sets the mode when the current Desk changes.

Focus is a quiet Desk for a set time: ``focus 50`` quiets the Desk in front
for fifty minutes and then puts back the quiet state it had.

Time tracking is off until the user turns it on (``track on``). It counts,
minute by minute, which Desk and slot are in front while the session is
unlocked, keeps the totals in a local state file for five weeks, and sends
them nowhere. It cannot tell an idle unlocked session from work.

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
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

VERSION = 1
MAX_DESKS = 9
SLOTS = range(1, 10)
MAX_NAME = 40
MAX_BLURB = 140
MAX_LAUNCH = 8
MAX_COMMAND = 512
MAX_RESTORE = MAX_LAUNCH
DESKTOP_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
FIELD_CODE = re.compile(r"^%[fFuUdDnNickvm]$")
QUIET_MODE = "do-not-disturb"
APP_NAME = "hyperlab-desk"
SAMPLE_SECONDS = 60
try:  # a shorter interval only for the contract's run of the sampler
    SAMPLE_SECONDS = max(1, min(3600, int(os.environ.get("HYPERLAB_DESK_SAMPLE_SECONDS", "60"))))
except ValueError:
    pass
KEEP_DAYS = 35
MAX_FOCUS_MINUTES = 480

HOME = Path.home()
CONFIG_HOME = Path(os.environ.get("XDG_CONFIG_HOME") or HOME / ".config")
STATE_HOME = Path(os.environ.get("XDG_STATE_HOME") or HOME / ".local/state")
USER_CONFIG = CONFIG_HOME / "hyperlab-workspace/desks.json"
SYSTEM_CONFIG = Path(
    os.environ.get("HYPERLAB_DESK_SYSTEM_CONFIG")
    or "/etc/hyperlab-workspace/desks.json"
)
STATE_FILE = STATE_HOME / "hyperlab-workspace/desks-state.json"
TIME_FILE = STATE_HOME / "hyperlab-workspace/desks-time.json"
DATA_HOME = Path(os.environ.get("XDG_DATA_HOME") or HOME / ".local/share")
DATA_DIRS = os.environ.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"

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


def lua_string(text: str) -> str:
    """Quote text as a Lua long string that its content cannot close."""
    level = 0
    while "]" + "=" * level + "]" in text:
        level += 1
    fence = "=" * level
    return f"[{fence}[{text}]{fence}]"


def dispatch(expression: str) -> None:
    """Run one Hyprland dispatcher.

    With a Lua configuration, `hyprctl dispatch X` evaluates
    `hl.dispatch(X)`, so X is a Lua dispatcher expression such as
    `hl.dsp.focus({workspace = 11})`, never the classic `workspace 11`.
    """
    result = subprocess.run(
        ["hyprctl", "dispatch", expression],
        capture_output=True, text=True, timeout=5, check=False,
    )
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0 or output not in ("", "ok"):
        raise DeskError("Hyprland refused: " + output)


def focus_workspace(workspace: int) -> None:
    dispatch(f"hl.dsp.focus({{workspace = {int(workspace)}}})")


def move_to_workspace(workspace: int) -> None:
    dispatch(f"hl.dsp.window.move({{workspace = {int(workspace)}}})")


def exec_command(command: str) -> None:
    dispatch(f"hl.dsp.exec_cmd({lua_string(command)})")


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


def read_entry(path: Path) -> dict[str, str] | None:
    """The unlocalised keys of a desktop entry's [Desktop Entry] group."""
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:
        return None
    fields: dict[str, str] = {}
    group = None
    for line in lines:
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            group = line[1:-1]
        elif group == "Desktop Entry" and "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            fields.setdefault(key.strip(), value.strip())
    usable = (
        fields.get("Type") == "Application"
        and fields.get("Hidden", "false") != "true"
        and fields.get("Exec")
    )
    return fields if usable else None


def desktop_entries() -> dict[str, dict[str, str]]:
    """Applications by desktop id; an earlier XDG data directory wins."""
    directories = [DATA_HOME] + [Path(item) for item in DATA_DIRS.split(":") if item]
    entries: dict[str, dict[str, str]] = {}
    for directory in directories:
        try:
            paths = sorted((directory / "applications").glob("*.desktop"))
        except OSError:
            continue
        for path in paths:
            if path.stem in entries or not DESKTOP_ID.match(path.stem):
                continue
            fields = read_entry(path)
            if fields is not None:
                entries[path.stem] = fields
    return entries


def entry_for_class(entries: dict[str, dict[str, str]], window_class: str) -> str | None:
    wanted = window_class.casefold()
    if not wanted:
        return None
    for matches in (
        lambda ident, fields: fields.get("StartupWMClass", "").casefold() == wanted,
        lambda ident, fields: ident.casefold() == wanted,
        lambda ident, fields: ident.casefold().endswith("." + wanted),
    ):
        found = sorted(ident for ident, fields in entries.items() if matches(ident, fields))
        if found:
            return found[0]
    return None


def entry_command(fields: dict[str, str]) -> str | None:
    """The entry's Exec as a shell command, its field codes dropped."""
    try:
        argv = shlex.split(fields["Exec"])
    except ValueError:
        return None
    command = []
    for argument in argv:
        if FIELD_CODE.match(argument):
            continue
        if "%" in argument.replace("%%", ""):
            return None  # an embedded field code has no safe expansion here
        command.append(argument.replace("%%", "%"))
    return shlex.join(command) if command else None


def workspace_applications(workspace: int) -> list[str]:
    clients = hyprctl_json("clients")
    entries: dict[str, dict[str, str]] | None = None
    found = []
    for client in clients if isinstance(clients, list) else []:
        if not isinstance(client, dict):
            continue
        place = client.get("workspace")
        if not isinstance(place, dict) or place.get("id") != workspace:
            continue
        window_class = client.get("initialClass") or client.get("class")
        if not isinstance(window_class, str):
            continue
        if entries is None:
            entries = desktop_entries()
        ident = entry_for_class(entries, window_class)
        if ident is not None and len(found) < MAX_RESTORE:
            found.append(ident)
    return found


def saved_applications(workspace: int) -> list[str]:
    saved = load_state().get("windows")
    items = saved.get(str(workspace)) if isinstance(saved, dict) else None
    if not isinstance(items, list):
        return []
    return [
        item for item in items[:MAX_RESTORE]
        if isinstance(item, str) and DESKTOP_ID.match(item)
    ]


def store_applications(workspace: int, applications: list[str] | None) -> None:
    state = load_state()
    saved = state.get("windows") if isinstance(state.get("windows"), dict) else {}
    if applications:
        saved[str(workspace)] = applications
    else:
        saved.pop(str(workspace), None)
    state["windows"] = saved
    write_json(STATE_FILE, state)


def remember_applications(model: dict[str, Any], workspace: int) -> None:
    """Record what a Project's workspace holds as the user leaves it.

    An empty workspace, or one with nothing that maps to a desktop entry,
    leaves the memory as it was: a fresh session must not forget a Project
    just because the user passed through its empty workspace.
    """
    if not describe(model, workspace)["project_name"]:
        return
    try:
        applications = workspace_applications(workspace)
        if applications:
            store_applications(workspace, applications)
    except (DeskError, OSError, subprocess.TimeoutExpired):
        pass  # Navigation never fails because memory could not be written.


def quiet_desks() -> set[int]:
    quiet = load_state().get("quiet")
    if not isinstance(quiet, list):
        return set()
    return {
        desk for desk in quiet
        if isinstance(desk, int) and not isinstance(desk, bool) and 1 <= desk <= MAX_DESKS
    }


def apply_quiet(desk: int) -> bool:
    """Put the notification daemon in the mode of the Desk now in front."""
    quiet = desk in quiet_desks()
    if shutil.which("makoctl"):
        try:
            subprocess.run(
                ["makoctl", "mode", "-a" if quiet else "-r", QUIET_MODE],
                capture_output=True, timeout=5, check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            pass  # Navigation never fails because of notifications.
    return quiet


def notify(summary: str) -> None:
    """One short notice from the helper; its app name is never hidden."""
    if not shutil.which("gdbus"):
        return
    try:
        subprocess.run(
            ["gdbus", "call", "--session",
             "--dest", "org.freedesktop.Notifications",
             "--object-path", "/org/freedesktop/Notifications",
             "--method", "org.freedesktop.Notifications.Notify",
             APP_NAME, "0", "", summary, "", "[]", "{}", "2500"],
            capture_output=True, timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


class StateLock:
    """Serialise the writers of one state file."""

    def __init__(self, name: str, blocking: bool = True) -> None:
        self.path = STATE_FILE.parent / f".{name}.lock"
        self.blocking = blocking

    def __enter__(self) -> StateLock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.handle = open(self.path, "w")
        flags = fcntl.LOCK_EX if self.blocking else fcntl.LOCK_EX | fcntl.LOCK_NB
        try:
            fcntl.flock(self.handle, flags)
        except BlockingIOError:
            self.handle.close()
            raise DeskError("another tracker already runs in this session") from None
        return self

    def __exit__(self, *_: object) -> None:
        fcntl.flock(self.handle, fcntl.LOCK_UN)
        self.handle.close()


def load_time() -> dict[str, Any]:
    try:
        data = json.loads(TIME_FILE.read_text())
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def session_locked() -> bool:
    result = subprocess.run(
        ["pgrep", "-x", "-u", str(os.getuid()), "hyprlock"],
        capture_output=True, timeout=5, check=False,
    )
    return result.returncode == 0


def track_sample(now: float) -> None:
    """Credit the minute just past to the Desk and slot in front."""
    with StateLock("time"):
        data = load_time()
        if data.get("enabled") is not True:
            return
        last = data.get("last")
        data["last"] = now
        days = data.get("days") if isinstance(data.get("days"), dict) else {}
        elapsed = now - last if isinstance(last, (int, float)) else 0
        # A longer gap is a suspend, a stopped tracker or a clock change;
        # it is never credited to anything.
        if 0 < elapsed <= 2 * SAMPLE_SECONDS and not session_locked():
            position = split_workspace(active_workspace())
            if position is not None:
                day = time.strftime("%Y-%m-%d", time.localtime(now))
                bucket = days.get(day) if isinstance(days.get(day), dict) else {}
                for key in (str(position[0]), f"{position[0]}.{position[1]}"):
                    previous = bucket.get(key)
                    previous = previous if isinstance(previous, int) else 0
                    bucket[key] = previous + int(round(elapsed))
                days[day] = bucket
        cutoff = time.strftime("%Y-%m-%d", time.localtime(now - KEEP_DAYS * 86400))
        data["days"] = {day: value for day, value in days.items() if day > cutoff}
        write_json(TIME_FILE, data)


def focus_state() -> dict[str, Any] | None:
    focus = load_state().get("focus")
    valid = (
        isinstance(focus, dict)
        and isinstance(focus.get("desk"), int)
        and isinstance(focus.get("until"), (int, float))
        and isinstance(focus.get("was_quiet"), bool)
    )
    return focus if valid else None


def end_focus(model: dict[str, Any], now: float, early: bool = False) -> bool:
    """Put back the quiet state a focus found, once its time is up."""
    focus = focus_state()
    if focus is None or (focus["until"] > now and not early):
        return False
    state = load_state()
    quiet = quiet_desks()
    if not focus["was_quiet"]:
        quiet.discard(focus["desk"])
    state["quiet"] = sorted(quiet)
    state.pop("focus", None)
    write_json(STATE_FILE, state)
    try:
        apply_quiet(current_desk(active_workspace()))
    except DeskError:
        pass  # The next Desk change applies it.
    desks = model["desks"]
    name = desks[focus["desk"] - 1]["name"] if focus["desk"] <= len(desks) else str(focus["desk"])
    notify(f"Desk {name}: focus ended")
    return True


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
        "quiet": bool(position) and position[0] in quiet_desks(),
        "focus_until": focus_until(position[0]) if position else None,
    }


def focus_until(desk: int) -> float | None:
    focus = focus_state()
    return focus["until"] if focus and focus["desk"] == desk else None


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
    remember_applications(model, current)
    target = desk * 10 + last_slot(desk)
    if target != current:
        focus_workspace(target)
    apply_quiet(desk)
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
        remember_applications(model, current)
        focus_workspace(target)
        if split_workspace(current) is None:
            apply_quiet(current_desk(target))  # from outside the Desks onto Desk 1
    remember_slot(target)
    return describe(model, target)


def command_move_workspace(args: argparse.Namespace) -> dict[str, Any]:
    model = load_model()
    target = current_desk(active_workspace()) * 10 + args.slot
    move_to_workspace(target)
    remember_slot(target)
    return describe(model, target)


def command_move_desk(args: argparse.Namespace) -> dict[str, Any]:
    model = load_model()
    require_desk(model, args.desk)
    target = args.desk * 10 + last_slot(args.desk)
    remember_slot(active_workspace())
    move_to_workspace(target)
    return describe(model, target)


def launch_line(cwd: str, command: str) -> str:
    directory = os.path.expanduser(cwd)
    return f"cd -- {shlex.quote(directory)} 2>/dev/null; exec {command}"


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
        remember_applications(model, current)
        focus_workspace(target)
        apply_quiet(args.desk)
    remember_slot(target)
    # The project's workspace is now the active one, so its programs open
    # there without a window rule.
    commands: list[str] = []
    restored = False
    if window_counts().get(target, 0) == 0:
        saved = saved_applications(target)
        entries = desktop_entries() if saved else {}
        commands = [
            command for command in (
                entry_command(entries[ident]) for ident in saved if ident in entries
            ) if command
        ]
        restored = bool(commands)
        if not restored:
            commands = list(project["launch"])
        for command in commands:
            exec_command(launch_line(project["cwd"], command))
    result = describe(model, target)
    result["launched"] = len(commands)
    result["restored"] = restored
    return result


def require_project(model: dict[str, Any], desk_number: int, slot: int) -> int:
    desk = require_desk(model, desk_number)
    if not any(item["slot"] == slot for item in desk["projects"]):
        raise DeskError(f"Desk {desk['name']} has no project in slot {slot}")
    return desk_number * 10 + slot


def command_project_save(args: argparse.Namespace) -> dict[str, Any]:
    target = require_project(load_model(), args.desk, args.slot)
    applications = workspace_applications(target)
    if not applications:
        raise DeskError("nothing on that workspace maps to an application to remember")
    store_applications(target, applications)
    return {"desk": args.desk, "slot": args.slot, "applications": applications}


def command_project_forget(args: argparse.Namespace) -> dict[str, Any]:
    target = require_project(load_model(), args.desk, args.slot)
    store_applications(target, None)
    return {"desk": args.desk, "slot": args.slot, "forgotten": True}


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
    try:
        store_applications(args.desk * 10 + args.slot, None)
    except OSError:
        pass  # A later project in this slot starts from its launch commands anyway.
    return {"desk": args.desk, "slot": args.slot, "removed": True}


def command_quiet(args: argparse.Namespace) -> dict[str, Any]:
    model = load_model()
    here = current_desk(active_workspace())
    desk = here if args.desk is None else args.desk
    name = require_desk(model, desk)["name"]
    if args.action == "sync":
        apply_quiet(here)
        return {"desk": here, "quiet": here in quiet_desks()}
    quiet = quiet_desks()
    wanted = desk not in quiet if args.action == "toggle" else args.action == "on"
    if wanted:
        quiet.add(desk)
    else:
        quiet.discard(desk)
    state = load_state()
    state["quiet"] = sorted(quiet)
    write_json(STATE_FILE, state)
    if desk == here:
        apply_quiet(desk)
    notify(f"Desk {name}: " + ("quiet, notifications wait" if wanted else "notifications on"))
    return {"desk": desk, "desk_name": name, "quiet": wanted}


def command_focus(args: argparse.Namespace) -> dict[str, Any]:
    model = load_model()
    now = time.time()
    end_focus(model, now)
    if args.minutes == "stop":
        return {"ended": end_focus(model, now, early=True)}
    try:
        minutes = int(args.minutes)
    except ValueError:
        raise DeskError("focus takes a number of minutes or stop") from None
    if not 1 <= minutes <= MAX_FOCUS_MINUTES:
        raise DeskError(f"focus lasts 1 to {MAX_FOCUS_MINUTES} minutes")
    if focus_state() is not None:
        raise DeskError("a focus is already running; focus stop ends it")
    desk = current_desk(active_workspace())
    name = require_desk(model, desk)["name"]
    state = load_state()
    quiet = quiet_desks()
    state["focus"] = {"desk": desk, "until": now + minutes * 60, "was_quiet": desk in quiet}
    quiet.add(desk)
    state["quiet"] = sorted(quiet)
    write_json(STATE_FILE, state)
    apply_quiet(desk)
    notify(f"Desk {name}: focus for {minutes} min")
    return {"desk": desk, "desk_name": name, "until": state["focus"]["until"]}


def track_report(model: dict[str, Any], days: int, now: float) -> dict[str, Any]:
    first = time.strftime("%Y-%m-%d", time.localtime(now - (days - 1) * 86400))
    totals: dict[str, int] = {}
    stored = load_time().get("days")
    for day, bucket in (stored.items() if isinstance(stored, dict) else []):
        if day >= first and isinstance(bucket, dict):
            for key, seconds in bucket.items():
                if isinstance(seconds, int):
                    totals[key] = totals.get(key, 0) + seconds
    report = []
    for index, desk in enumerate(model["desks"], start=1):
        names = {item["slot"]: item["name"] for item in desk["projects"]}
        slots = [
            {"slot": slot, "project": names.get(slot, ""),
             "minutes": totals[f"{index}.{slot}"] // 60}
            for slot in SLOTS if totals.get(f"{index}.{slot}", 0) >= 60
        ]
        report.append({"desk": index, "name": desk["name"],
                       "minutes": totals.get(str(index), 0) // 60, "slots": slots})
    return {"days": days, "desks": report}


def command_track(args: argparse.Namespace) -> dict[str, Any]:
    now = time.time() if args.now is None else args.now
    if args.action in ("on", "off", "clear"):
        with StateLock("time"):
            data = {} if args.action == "clear" else load_time()
            if args.action != "clear":
                data["enabled"] = args.action == "on"
                data["last"] = now
            write_json(TIME_FILE, data)
        return {"tracking": data.get("enabled") is True}
    if args.action == "sample":
        end_focus(load_model(), now)
        track_sample(now)
        return {"tracking": load_time().get("enabled") is True}
    if args.action == "report":
        if not 1 <= args.days <= KEEP_DAYS:
            raise DeskError(f"a report covers 1 to {KEEP_DAYS} days")
        return track_report(load_model(), args.days, now)
    # run: one sampler per session, started by Hyprland; it also ends a
    # focus on time. It stops once Hyprland has been gone for three samples.
    with StateLock("tracker", blocking=False):
        failures = 0
        while failures < 3:
            try:
                active_workspace()  # raises once Hyprland is gone, tracking or not
                end_focus(load_model(), time.time())
                track_sample(time.time())
                failures = 0
            except DeskError:
                failures += 1
            except (OSError, subprocess.TimeoutExpired):
                pass  # A full disk or a slow pgrep skips one minute.
            time.sleep(SAMPLE_SECONDS)
    return {"stopped": "Hyprland is gone"}


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

    for name, handler, help_text in (
        ("project-save", command_project_save,
         "remember the applications on a project's workspace now"),
        ("project-forget", command_project_forget,
         "forget a project's remembered applications"),
    ):
        remembered = add(name, handler, help_text)
        remembered.add_argument("desk", type=int)
        remembered.add_argument("slot", type=int, choices=SLOTS)

    removed = add("project-remove", command_project_remove, "remove a project")
    removed.add_argument("desk", type=int)
    removed.add_argument("slot", type=int, choices=SLOTS)

    quiet = add("quiet", command_quiet,
                "keep notifications out of sight while a Desk is in front")
    quiet.add_argument("action", choices=("on", "off", "toggle", "sync"))
    quiet.add_argument("--desk", type=int)

    focus = add("focus", command_focus, "quiet the Desk in front for N minutes")
    focus.add_argument("minutes", help="1 to 480, or stop")

    track = add("track", command_track, "opt-in time per Desk and slot, kept locally")
    track.add_argument("action", choices=("on", "off", "clear", "report", "sample", "run"))
    track.add_argument("--days", type=int, default=7)
    track.add_argument("--now", type=float, help=argparse.SUPPRESS)

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
