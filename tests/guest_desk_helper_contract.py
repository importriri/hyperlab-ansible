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
  5. the helper refuses a Desk that does not exist rather than inventing one.
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
        self.state = base / "hypr.json"
        self.log = base / "hypr.log"
        self.set(active=1, windows={})

    def set(self, active: int, windows: dict[str, int]) -> None:
        self.state.write_text(json.dumps({"active": active, "windows": windows}))
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
        check_refused_configuration(lab)
    print("HyperLab guest Desk helper contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
