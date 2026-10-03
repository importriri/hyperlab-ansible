#!/usr/bin/env python3
"""Static contract for the guest HyperLab Workspace Shell and its wiring.

The runtime contract proves the shell behaves; this one pins the decisions
that keep it safe and coherent, so a later edit cannot quietly undo them:

  1. the guest shell shows no trust and knows nothing of the host: no
     hypervisor tool, no provenance vocabulary, no host socket;
  2. the lock stays in hyprlock, a separate program, never in the shell;
  3. every guest key goes through the ALT namespace and through the
     helpers, so the keys keep working when the shell is not running, and a
     failing shell falls back to Waybar;
  4. the role installs every piece it wires in one full Arch transaction,
     pins the reviewed Quickshell API series, validates the image Desks and
     keeps Waybar deployed;
  5. Desk n owns workspaces n*10+1..n*10+9 in the helper and in the shell
     alike.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLE = ROOT / "roles/guest_desktop_hyprland"
SHELL = ROLE / "files/quickshell/hyperlab-workspace"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(f"guest workspace shell contract: {message}")


def code_only(source: str) -> str:
    """QML or JavaScript without comments, so prose cannot mask a token."""
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.S)
    return re.sub(r"(?m)//.*$", "", source)


def check_shell_sources() -> None:
    files = sorted(SHELL.glob("*"))
    names = {path.name for path in files}
    require("shell.qml" in names, "shell.qml is missing")
    require(
        SHELL.joinpath("shell.qml").read_text().startswith("//@ pragma ShellId hyperlab-workspace"),
        "shell.qml must declare the hyperlab-workspace shell id",
    )

    # Every component is used by another file; nothing ships unreferenced.
    sources = {path.name: path.read_text() for path in files}
    for path in files:
        if path.suffix == ".qml" and path.name != "shell.qml":
            component = path.stem
            used = any(
                re.search(rf"\b{component}\s*\{{", text)
                for name, text in sources.items() if name != path.name
            )
            require(used, f"{path.name} is not used by any other file")
        if path.suffix == ".js":
            used = any(f'"{path.name}"' in text for text in sources.values())
            require(used, f"{path.name} is not imported")

    forbidden = (
        "hyperlabctl", "virsh", "libvirt", "qemu", "vfio", "gpu_handoff",
        "provenance", "privatestack-hyperlab", "/run/hyperlab", "trust_level",
        "WlSessionLock", "Pam", "sudo", "pkexec",
    )
    for name, text in sources.items():
        code = code_only(text)
        for token in forbidden:
            require(token.lower() not in code.lower(), f"{name} uses {token!r}")

    # "trust" appears once, in the sentence saying a Desk is not isolation.
    mentions = [
        name for name, text in sources.items()
        if "trust" in code_only(text).lower()
    ]
    require(mentions == ["DeskOverview.qml"], f"trust is shown outside the overview: {mentions}")
    overview = sources["DeskOverview.qml"]
    require("It is organisation, not isolation" in overview,
            "the overview must say a Desk is organisation, not isolation")

    # Mutations go through the helper; the shell never dispatches by itself.
    for name, text in sources.items():
        require("Hyprland.dispatch" not in code_only(text),
                f"{name} dispatches to Hyprland directly instead of hyperlab-desk")

    desks = sources["desks.js"]
    require("desk * 10 + slot" in desks and "Math.floor(id / 10)" in desks,
            "desks.js no longer maps Desk n to workspaces n*10+slot")
    helper = (ROLE / "files/hyperlab-desk.py").read_text()
    require("divmod(workspace, 10)" in helper and "desk * 10 + " in helper,
            "hyperlab-desk no longer maps Desk n to workspaces n*10+slot")

    launcher = sources["Launcher.qml"]
    for action in ("logout", "reboot", "poweroff"):
        require(re.search(rf'"id": "{action}"[^}}]*"confirm": true', launcher),
                f"{action} must ask for a second Enter")


def check_hyprland_wiring() -> None:
    lua = (ROLE / "templates/hyprland.lua.j2").read_text()
    require('local main_mod = "ALT"' in lua, "guest namespace is not ALT")
    for bind, command in (
        ('main_mod .. " + D"', "hyperlab-workspace overview"),
        ('main_mod .. " + space"', "hyperlab-workspace launcher"),
        ('main_mod .. " + N"', "hyperlab-workspace new-project"),
        ('main_mod .. " + " .. key', '"hyperlab-desk desk " .. key'),
        ('main_mod .. " + SHIFT + " .. key', '"hyperlab-desk move-to-desk " .. key'),
        ('main_mod .. " + CTRL + " .. key', '"hyperlab-desk workspace " .. key'),
        ('main_mod .. " + CTRL + SHIFT + " .. key', '"hyperlab-desk move-to-workspace " .. key'),
        ('main_mod .. " + Page_Down"', "hyperlab-desk desk-next"),
        ('main_mod .. " + Page_Up"', "hyperlab-desk desk-prev"),
    ):
        pattern = re.escape(bind) + r",\s*\n\s*hl\.dsp\.exec_cmd\(" + r'\s*"?' + re.escape(command.strip('"'))
        require(re.search(pattern, lua), f"binding {bind} does not run {command}")
    require("hyprlauncher" not in lua, "ALT+D still opens hyprlauncher")
    require('hl.exec_cmd("hyperlab-desk desk 1")' in lua, "the session does not land on Desk 1")
    require("{% if guest_desktop_hyprland_shell == 'quickshell' %}" in lua,
            "the bar choice is not driven by guest_desktop_hyprland_shell")

    script = (ROLE / "files/hyperlab-workspace.sh").read_text()
    require("exec waybar" in script, "a failing shell no longer falls back to Waybar")
    require("QS_DISABLE_FILE_WATCHER=1" in script, "the shell would reload mid-deployment")
    require("exec rofi -show drun" in script, "the launcher key has no fallback")
    for call in ("launcher", "overview", "newProject"):
        require(f"shell_call {call}" in script, f"{call} does not try the shell first")

    lock = (ROLE / "files/hyprlock.conf").read_text()
    require("cmd[update:5000] hyperlab-desk lock-label" in lock, "the lock no longer says where you were")
    require("$guest_accent" in lock and "IBM Plex" in lock, "the lock lost the workstation style")
    require('"pidof hyprlock || hyprlock"' in lua, "ALT+L no longer locks with hyprlock")


def check_role() -> None:
    defaults = yaml.safe_load((ROLE / "defaults/main.yml").read_text())
    tasks = (ROLE / "tasks/main.yml").read_text()
    packages = defaults["guest_desktop_hyprland_packages"]
    for package in ("quickshell", "ttf-ibm-plex", "waybar", "hyprlock", "rofi"):
        require(package in packages, f"{package} is not installed")
    require(defaults["guest_desktop_hyprland_shell"] == "quickshell", "the shell is not the default")
    require(defaults["guest_desktop_hyprland_quickshell_series"] == "0.3",
            "the reviewed Quickshell series changed without review")
    require(defaults["guest_desktop_hyprland_theme_order"][0] == "hyperlab-workstation",
            "the workstation theme is not first")
    require(defaults["guest_desktop_hyprland_theme_default"] == "hyperlab-workstation",
            "the workstation theme is not the default")
    desks = defaults["guest_desktop_hyprland_workspace_desks"]
    require(1 <= len(desks) <= 9, "the image must define one to nine Desks")

    for needle in (
        "src: quickshell/hyperlab-workspace/",
        "dest: /etc/xdg/quickshell/hyperlab-workspace/",
        "{ src: hyperlab-desk.py, dest: hyperlab-desk }",
        "{ src: hyperlab-workspace.sh, dest: hyperlab-workspace }",
        "validate: /usr/local/bin/hyperlab-desk check %s",
        "dest: /etc/hyperlab-workspace/desks.json",
        "Verify the reviewed Quickshell API series",
        "{ src: waybar.jsonc, dest: waybar/config.jsonc }",
        "{ src: hyprlock.conf, dest: hypr/hyprlock.conf }",
    ):
        require(needle in tasks, f"the role no longer does: {needle}")

    install = tasks.split("- name: Install the official Hyprland guest stack", 1)[1].split("\n- name:", 1)[0]
    require("update_cache: true" in install and "upgrade: true" in install,
            "new guest packages must be installed in one full system transaction")

    controller = (ROLE / "files/privatestack-guest-theme.py").read_text()
    require('"privatestack-guest/palette.json"' in controller,
            "the theme controller no longer writes the shell palette")
    require('["pgrep", "-x", "waybar"]' in controller,
            "a theme change would start Waybar beside the shell")
    require('"hyperlab-workstation": {' in controller, "the controller lacks the workstation theme")


def main() -> int:
    check_shell_sources()
    check_hyprland_wiring()
    check_role()
    print("HyperLab guest workspace shell contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
