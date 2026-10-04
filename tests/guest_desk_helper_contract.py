#!/usr/bin/env python3
"""Behaviour contract for hyperlab-desk, the guest Desk and project helper.

The helper runs against a recording hyprctl stand-in, in a private HOME, so
every assertion is about what the helper asks Hyprland to do and what it
writes, never about a live compositor.

What it proves:

  1. Desk d owns workspaces d*10+1..d*10+9; switching Desk returns to the
     slot last used there; ALT+N slots stay inside the current Desk;
  2. a refused user configuration is reported, never half-applied, and never
     overwritten by a later edit;
  3. projects get the first free slot, names are unique per Desk, and opening
     a project launches its programs only when its workspace is empty, in its
     directory, on its own workspace, with the path shell-quoted;
  4. every dispatch is a Lua dispatcher expression that a real Lua
     interpreter accepts, as Hyprland 0.56 with a Lua configuration requires,
     including commands that contain Lua's own string delimiters;
  5. the helper refuses a Desk that does not exist rather than inventing one;
  6. a project remembers the applications its workspace held when it was
     left, as desktop entry ids only, and reopens them from their entries
     in its folder; nothing it cannot map, and no process argument, is kept;
  7. a quiet Desk puts the notification daemon in its do-not-disturb mode
     whenever that Desk comes to the front, and takes it out when another
     Desk does; a focus quiets the Desk in front for a time and then puts
     back the quiet state it found;
  8. time tracking is off until turned on, credits only sampled minutes of
     an unlocked session to the Desk and slot in front, never a gap, keeps
     five weeks, and its sampler runs once per session and stops when
     Hyprland is gone.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "roles/guest_desktop_hyprland/files/hyperlab-desk.py"

FAKE_HYPRCTL = ROOT / "tests/fixtures/fake_hyprctl_lua.py"


class Lab:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.home = base / "home"
        self.home.mkdir()
        self.bin = base / "bin"
        self.bin.mkdir()
        hyprctl = self.bin / "hyprctl"
        hyprctl.write_text(FAKE_HYPRCTL.read_text())
        hyprctl.chmod(0o755)
        # Recording stand-ins: the contract never reaches a real session bus.
        for tool in ("makoctl", "gdbus"):
            stand_in = self.bin / tool
            stand_in.write_text(
                "#!/bin/sh\n"
                f'printf "%s\\n" "{tool} $*" >> "$FAKE_NOTIFY_LOG"\n'
            )
            stand_in.chmod(0o755)
        self.notify_log = base / "notify.log"
        pgrep = self.bin / "pgrep"
        pgrep.write_text('#!/bin/sh\n[ -n "${FAKE_LOCKED:-}" ] && exit 0\nexit 1\n')
        pgrep.chmod(0o755)
        self.extra: dict[str, str] = {}
        self.state = base / "hypr.json"
        self.log = base / "hypr.log"
        self.set(active=1, windows={})

    def set(self, active: int, windows: dict[str, int], clients: list | None = None) -> None:
        self.state.write_text(json.dumps(
            {"active": active, "windows": windows, "clients": clients or []}
        ))
        self.log.write_text("")

    @property
    def active(self) -> int:
        return json.loads(self.state.read_text())["active"]

    def calls(self) -> list[list[str]]:
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def run(self, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        env = {
            "HOME": str(self.home),
            "PATH": f"{self.bin}:{os.environ.get('PATH', '/usr/bin')}",
            "FAKE_HYPR_STATE": str(self.state),
            "FAKE_HYPR_LOG": str(self.log),
            "HYPERLAB_DESK_SYSTEM_CONFIG": str(self.base / "etc-desks.json"),
            "XDG_DATA_HOME": str(self.base / "data-home"),
            "XDG_DATA_DIRS": str(self.base / "data-dirs"),
            "FAKE_NOTIFY_LOG": str(self.notify_log),
            **self.extra,
        }
        result = subprocess.run(
            [sys.executable, str(HELPER), *args],
            capture_output=True, text=True, timeout=20, env=env, check=False,
        )
        if ok:
            assert result.returncode == 0, (args, result.stderr)
        else:
            assert result.returncode == 2, (args, result.returncode, result.stdout)
            assert "hyperlab-desk" in result.stderr, result.stderr
        return result

    def json(self, *args: str) -> dict:
        return json.loads(self.run(*args).stdout)

    @property
    def user_config(self) -> Path:
        return self.home / ".config/hyperlab-workspace/desks.json"


def check_mapping(lab: Lab) -> None:
    model = lab.json("model")
    assert model["source"] == "builtin" and model["errors"] == []
    assert [desk["name"] for desk in model["desks"]] == [
        "Programming", "3D Design", "Research", "Systems",
    ]

    lab.set(active=1, windows={})
    assert lab.json("desk", "1")["workspace"] == 11 and lab.active == 11
    lab.json("workspace", "3")
    assert lab.active == 13
    status = lab.json("desk", "2")
    assert (status["desk"], status["slot"], lab.active) == (2, 1, 21)
    lab.json("workspace", "5")
    assert lab.active == 25
    # Back to Programming lands on the slot left there, not slot 1.
    assert lab.json("desk", "1")["slot"] == 3 and lab.active == 13
    assert lab.json("desk-next")["desk"] == 2 and lab.active == 25
    lab.json("desk", "4")
    assert lab.json("desk-next")["desk"] == 1, "Desk cycling must wrap"
    assert lab.json("desk-prev")["desk"] == 4

    lab.json("desk", "1")
    lab.json("move-to-workspace", "7")
    assert ["move", "17"] in lab.calls()

    lab.run("desk", "5", ok=False)
    lab.run("desk", "0", ok=False)
    lab.run("workspace", "0", ok=False)

    # Outside the Desk range (legacy workspace 1) ALT+N lands on Desk 1.
    lab.set(active=1, windows={})
    lab.json("workspace", "2")
    assert lab.active == 12


def check_projects(lab: Lab) -> None:
    lab.set(active=11, windows={})
    first = lab.json("project-new", "1", "HyperLab", "--cwd", "~/src/hyper lab")
    assert first == {"desk": 1, "name": "HyperLab", "slot": 1}
    second = lab.json("project-new", "1", "Doppiari site")
    assert second["slot"] == 2
    lab.run("project-new", "1", "hyperlab", ok=False)  # case-insensitive twin
    lab.run("project-new", "1", "Clash", "--slot", "2", ok=False)
    lab.run("project-new", "9", "Nowhere", ok=False)
    lab.run("project-new", "1", "Bad", "--cwd", "relative/path", ok=False)
    lab.run("project-new", "1", "   ", ok=False)

    saved = json.loads(lab.user_config.read_text())
    projects = saved["desks"][0]["projects"]
    assert [p["name"] for p in projects] == ["HyperLab", "Doppiari site"]
    assert projects[0]["launch"] == ["kitty"] and projects[1]["cwd"] == "~"
    assert lab.json("model")["source"] == "user"

    status = lab.json("status")
    assert status["project_name"] == "HyperLab" and status["desk_name"] == "Programming"
    assert lab.run("lock-label").stdout.strip() == (
        "HyperLab Workstation · Desk Programming / HyperLab"
    )

    # An empty project workspace launches its programs there, in its folder.
    lab.set(active=25, windows={})
    opened = lab.json("project-open", "1", "1")
    assert opened["launched"] == 1 and lab.active == 11
    execs = [call for call in lab.calls() if call[0] == "exec"]
    home = str(lab.home)
    assert execs == [[
        "exec", f"cd -- '{home}/src/hyper lab' 2>/dev/null; exec kitty",
    ]], execs

    # A launch command that contains Lua's own closing delimiters stays one
    # intact string.
    lab.json("project-new", "1", "Tricky", "--slot", "5", "--launch", "echo ']]' ']=]' done")
    lab.set(active=25, windows={})
    lab.json("project-open", "1", "5")
    execs = [call for call in lab.calls() if call[0] == "exec"]
    assert execs and execs[-1][1].endswith("exec echo ']]' ']=]' done"), execs
    lab.json("project-remove", "1", "5")

    # A project that already has windows is only focused.
    lab.set(active=25, windows={"11": 3})
    assert lab.json("project-open", "1", "1")["launched"] == 0
    assert not [call for call in lab.calls() if call[0] == "exec"]
    lab.run("project-open", "1", "9", ok=False)

    assert lab.json("project-remove", "1", "2")["removed"] is True
    lab.run("project-remove", "1", "2", ok=False)


def application(lab: Lab, where: str, ident: str, body: str) -> None:
    directory = lab.base / where / "applications"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{ident}.desktop").write_text("[Desktop Entry]\n" + body)


def client(window_class: str, workspace: int, pid: int = 4242) -> dict:
    return {"class": window_class, "initialClass": window_class,
            "workspace": {"id": workspace, "name": str(workspace)}, "pid": pid}


def check_restore(lab: Lab) -> None:
    application(lab, "data-dirs", "kitty", "Type=Application\nExec=kitty\n")
    application(lab, "data-dirs", "org.mozilla.firefox",
                "Type=Application\nExec=/usr/lib/firefox/firefox %u\n")
    application(lab, "data-dirs", "gimp",
                "Type=Application\nStartupWMClass=Gimp-2.10\nExec=gimp-2.10 %U\n")
    application(lab, "data-dirs", "inline",
                "Type=Application\nExec=sh -c 'open --file=%f'\n")
    application(lab, "data-dirs", "ghost",
                "Type=Application\nHidden=true\nExec=ghost\n")
    # The user's own entry wins over the system one with the same id.
    application(lab, "data-home", "kitty",
                "Type=Application\nExec=kitty --single-instance\n")
    lab.json("project-new", "1", "Restore", "--slot", "3", "--cwd", "~/r",
             "--launch", "fallback-tool")
    home = str(lab.home)
    state = lab.home / ".local/state/hyperlab-workspace/desks-state.json"

    # Leaving the project's workspace records what maps to an application.
    lab.set(active=13, windows={"13": 5}, clients=[
        client("org.mozilla.firefox", 13), client("firefox", 13),
        client("unmapped-tool", 13), client("Gimp-2.10", 13),
        client("ghost", 13), client("kitty", 14),
    ])
    lab.json("workspace", "4")
    saved = json.loads(state.read_text())["windows"]["13"]
    assert saved == ["org.mozilla.firefox", "org.mozilla.firefox", "gimp"], saved
    assert "4242" not in state.read_text() and "pid" not in state.read_text()

    # An empty project workspace reopens them from their entries, in its folder.
    lab.set(active=14, windows={})
    opened = lab.json("project-open", "1", "3")
    assert opened["restored"] is True and opened["launched"] == 3, opened
    execs = [call[1] for call in lab.calls() if call[0] == "exec"]
    assert execs == [
        f"cd -- {home}/r 2>/dev/null; exec /usr/lib/firefox/firefox",
        f"cd -- {home}/r 2>/dev/null; exec /usr/lib/firefox/firefox",
        f"cd -- {home}/r 2>/dev/null; exec gimp-2.10",
    ], execs

    # Passing through the empty workspace of a fresh session keeps the memory;
    # a slot that is not a project records nothing.
    lab.set(active=13, windows={})
    lab.json("workspace", "4")
    assert json.loads(state.read_text())["windows"]["13"] == saved
    lab.set(active=16, windows={"16": 1}, clients=[client("kitty", 16)])
    lab.json("workspace", "4")
    assert "16" not in json.loads(state.read_text())["windows"]

    # project-save records now; the user's entry for an id wins.
    lab.set(active=13, windows={"13": 1}, clients=[client("kitty", 13)])
    assert lab.json("project-save", "1", "3")["applications"] == ["kitty"]
    lab.set(active=14, windows={})
    lab.json("project-open", "1", "3")
    execs = [call[1] for call in lab.calls() if call[0] == "exec"]
    assert execs == [f"cd -- {home}/r 2>/dev/null; exec kitty --single-instance"], execs
    lab.set(active=13, windows={"13": 1}, clients=[client("unmapped-tool", 13)])
    lab.run("project-save", "1", "3", ok=False)
    lab.run("project-save", "1", "8", ok=False)

    # An entry with an embedded field code, a tampered id or a vanished entry
    # is never run; with nothing usable the launch commands apply.
    for remembered in (["inline"], ["../../../bin/sh"], ["gone"]):
        data = json.loads(state.read_text())
        data["windows"]["13"] = remembered
        state.write_text(json.dumps(data))
        lab.set(active=14, windows={})
        opened = lab.json("project-open", "1", "3")
        assert opened["restored"] is False, remembered
        execs = [call[1] for call in lab.calls() if call[0] == "exec"]
        assert execs == [f"cd -- {home}/r 2>/dev/null; exec fallback-tool"], execs

    # Forgetting, and removing the project, clear the memory.
    lab.set(active=13, windows={"13": 1}, clients=[client("kitty", 13)])
    lab.json("project-save", "1", "3")
    assert lab.json("project-forget", "1", "3")["forgotten"] is True
    assert "13" not in json.loads(state.read_text())["windows"]
    lab.json("project-save", "1", "3")
    lab.json("project-remove", "1", "3")
    assert "13" not in json.loads(state.read_text())["windows"]


def check_quiet(lab: Lab) -> None:
    def modes() -> list[str]:
        lines = lab.notify_log.read_text().splitlines() if lab.notify_log.exists() else []
        lab.notify_log.write_text("")
        return [line for line in lines if line.startswith("makoctl")]

    lab.set(active=11, windows={})
    modes()
    quiet = lab.json("quiet", "on")
    assert quiet == {"desk": 1, "desk_name": "Programming", "quiet": True}, quiet
    assert modes() == ["makoctl mode -a do-not-disturb"]
    assert lab.json("status")["quiet"] is True

    # Another Desk in front lifts the mode; coming back restores it.
    lab.json("desk", "2")
    assert modes() == ["makoctl mode -r do-not-disturb"]
    assert lab.json("status")["quiet"] is False
    lab.json("desk", "1")
    assert modes() == ["makoctl mode -a do-not-disturb"]
    lab.set(active=21, windows={"11": 1})
    lab.json("project-open", "1", "1")
    assert modes() == ["makoctl mode -a do-not-disturb"]

    # A slot of the same Desk changes nothing; a Desk set from elsewhere
    # changes the mode only when it is in front.
    lab.json("workspace", "2")
    assert modes() == []
    lab.json("quiet", "on", "--desk", "3")
    assert modes() == []
    lab.json("desk", "3")
    assert modes() == ["makoctl mode -a do-not-disturb"]
    assert lab.json("quiet", "toggle")["quiet"] is False
    assert modes() == ["makoctl mode -r do-not-disturb"]

    # The confirmation names the helper, which the quiet mode never hides.
    log = lab.notify_log
    lab.json("quiet", "toggle")
    notices = [line for line in log.read_text().splitlines() if line.startswith("gdbus")]
    assert notices and "Notify hyperlab-desk 0" in notices[-1], notices

    # A session start applies the Desk in front.
    lab.set(active=31, windows={})
    modes()
    assert lab.json("quiet", "sync") == {"desk": 3, "quiet": True}
    assert modes() == ["makoctl mode -a do-not-disturb"]

    lab.run("quiet", "on", "--desk", "9", ok=False)
    lab.run("quiet", "loud", ok=False)
    for desk in (1, 3):
        lab.json("quiet", "off", "--desk", str(desk))


def check_focus(lab: Lab) -> None:
    def modes() -> list[str]:
        lines = lab.notify_log.read_text().splitlines()
        lab.notify_log.write_text("")
        return [line for line in lines if line.startswith("makoctl")]

    lab.set(active=11, windows={})
    lab.notify_log.write_text("")
    started = lab.json("focus", "25")
    assert started["desk"] == 1 and modes() == ["makoctl mode -a do-not-disturb"]
    status = lab.json("status")
    assert status["quiet"] is True and status["focus_until"] == started["until"]
    lab.run("focus", "10", ok=False)  # one focus at a time
    # Before its time nothing changes; after it the Desk is loud again.
    lab.json("track", "sample", "--now", str(started["until"] - 5))
    assert lab.json("status")["quiet"] is True and modes() == []
    lab.json("track", "sample", "--now", str(started["until"] + 1))
    status = lab.json("status")
    assert status["quiet"] is False and status["focus_until"] is None
    assert modes() == ["makoctl mode -r do-not-disturb"]

    # A Desk that was quiet before the focus stays quiet after it.
    lab.json("quiet", "on")
    lab.json("focus", "5")
    assert lab.json("focus", "stop") == {"ended": True}
    assert lab.json("status")["quiet"] is True
    assert lab.json("focus", "stop") == {"ended": False}
    lab.json("quiet", "off")
    for bad in ("0", "481", "soon"):
        lab.run("focus", bad, ok=False)


def check_tracking(lab: Lab) -> None:
    time_file = lab.home / ".local/state/hyperlab-workspace/desks-time.json"

    def sample(now: int, active: int, locked: bool = False) -> None:
        lab.set(active=active, windows={})
        lab.extra = {"FAKE_LOCKED": "1"} if locked else {}
        lab.json("track", "sample", "--now", str(now))
        lab.extra = {}

    def report(now: int) -> dict:
        data = lab.json("track", "report", "--days", "1", "--now", str(now))
        return {desk["desk"]: desk for desk in data["desks"]}

    # Off until turned on: a sample writes nothing.
    sample(1000, 12)
    assert not time_file.exists()
    assert all(desk["minutes"] == 0 for desk in report(1000).values())

    lab.json("track", "on", "--now", "1000")
    sample(1060, 12)                 # Desk 1, slot 2
    sample(1120, 12, locked=True)    # locked: not credited
    sample(1180, 23)                 # Desk 2, slot 3
    sample(2000, 23)                 # a gap of 820 s: not credited
    sample(2060, 23)
    desks = report(2060)
    assert desks[1]["minutes"] == 1 and desks[1]["slots"][0]["slot"] == 2
    assert desks[2]["minutes"] == 2 and [s["slot"] for s in desks[2]["slots"]] == [3]
    assert desks[3]["minutes"] == 0 and desks[3]["slots"] == []
    assert "1.2" in time_file.read_text() and "pid" not in time_file.read_text()

    # Five weeks are kept; older days go.
    later = 2060 + 40 * 86400
    sample(later, 11)
    sample(later + 60, 11)
    days = json.loads(time_file.read_text())["days"]
    assert len(days) == 1 and report(later + 60)[1]["minutes"] == 1

    lab.json("track", "off", "--now", str(later + 60))
    sample(later + 120, 11)
    assert report(later + 120)[1]["minutes"] == 1, "a sample after off was credited"
    lab.run("track", "report", "--days", "36", ok=False)
    assert lab.json("track", "clear") == {"tracking": False}
    assert report(later + 120)[1]["minutes"] == 0

    # One sampler per session, and it ends once Hyprland is gone.
    lock = lab.home / ".local/state/hyperlab-workspace/.tracker.lock"
    import fcntl
    with open(lock, "w") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        lab.run("track", "run", ok=False)
    lab.extra = {"HYPERLAB_DESK_SAMPLE_SECONDS": "1", "FAKE_HYPR_STATE": str(lab.base / "gone.json")}
    stopped = lab.json("track", "run")
    lab.extra = {}
    assert stopped == {"stopped": "Hyprland is gone"}, stopped


def check_refused_configuration(lab: Lab) -> None:
    good = lab.user_config.read_text()
    broken = json.loads(good)
    broken["desks"].append({"name": "programming"})  # duplicate Desk name
    lab.user_config.write_text(json.dumps(broken))

    model = lab.json("model")
    assert model["source"] == "builtin", "a refused file must not be half-applied"
    assert model["errors"] and "appears twice" in model["errors"][0]

    before = lab.user_config.read_text()
    lab.run("project-new", "1", "Another", ok=False)
    assert lab.user_config.read_text() == before, "a refused file was overwritten"

    # The image default is used when the user has no file of their own.
    lab.user_config.unlink()
    (lab.base / "etc-desks.json").write_text(json.dumps({
        "version": 1, "desks": [{"name": "Studio", "projects": []}],
    }))
    model = lab.json("model")
    assert model["source"] == "system" and model["desks"][0]["name"] == "Studio"

    for bad in (
        {"version": 2, "desks": [{"name": "A"}]},
        {"version": 1, "desks": []},
        {"version": 1, "desks": [{"name": "A\u0007"}]},
        {"version": 1, "desks": [{"name": "A", "projects": [
            {"slot": 10, "name": "x"}]}]},
        {"version": 1, "desks": [{"name": "A", "projects": [
            {"slot": True, "name": "x"}]}]},
        {"version": 1, "desks": [{"name": "A", "projects": [
            {"slot": 1, "name": "x", "launch": ["a\nb"]}]}]},
        {"version": 1, "desks": [{"name": f"D{i}"} for i in range(10)]},
    ):
        path = lab.base / "candidate.json"
        path.write_text(json.dumps(bad))
        lab.run("check", str(path), ok=False)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="hyperlab-desk-") as temporary:
        lab = Lab(Path(temporary))
        check_mapping(lab)
        check_projects(lab)
        check_restore(lab)
        check_quiet(lab)
        check_focus(lab)
        check_tracking(lab)
        check_refused_configuration(lab)
    print("HyperLab guest Desk helper contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
