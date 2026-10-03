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
  4. the role syncs the whole Arch system before installing what it wires,
     pins the reviewed Quickshell API series, validates the image Desks and
     keeps Waybar deployed;
  5. Desk n owns workspaces n*10+1..n*10+9 in the helper and in the shell
     alike.
"""

from __future__ import annotations

import json
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

    # Under Hyprland's Lua configuration `hyprctl dispatch` takes Lua, so the
    # classic dispatcher syntax must not come back anywhere in the shell.
    for name, text in sources.items():
        require("hyprctl\", \"dispatch" not in code_only(text) and "hyprctl dispatch" not in code_only(text),
                f"{name} uses classic hyprctl dispatch syntax")

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

    require("hl.dsp.focus(" in helper and "hl.dsp.window.move(" in helper
            and "hl.dsp.exec_cmd(" in helper,
            "hyperlab-desk must dispatch Lua expressions to Hyprland")

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
        ('main_mod .. " + H"', "hyperlab-workspace cheatsheet"),
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
    for call in ("launcher", "overview", "newProject", "cheatsheet"):
        require(f"shell_call {call}" in script, f"{call} does not try the shell first")

    lock = (ROLE / "files/hyprlock.conf").read_text()
    require("cmd[update:5000] hyperlab-desk lock-label" in lock, "the lock no longer says where you were")
    require("$guest_accent" in lock and "IBM Plex" in lock, "the lock lost the workstation style")
    require('"pidof hyprlock || hyprlock"' in lua, "ALT+L no longer locks with hyprlock")


def check_keys_sheet() -> None:
    """Every ALT binding the guest configures is on the sheet, and back."""
    sheet = json.loads((SHELL / "keys.json").read_text())
    listed = {
        entry["keys"] for group in sheet["groups"] for entry in group["keys"]
    }
    lua = (ROLE / "templates/hyprland.lua.j2").read_text()
    singles = set(re.findall(r'main_mod \.\. " \+ ([A-Za-z]+)"', lua))
    names = {"Return": "ALT+Return", "space": "ALT+Space"}
    for key in singles:
        if key.startswith("XF86") or key in ("left", "right", "up", "down"):
            continue
        if key in ("Page_Down", "Page_Up"):
            continue
        chord = names.get(key, "ALT+" + key.upper() if len(key) == 1 else "ALT+" + key)
        require(chord in listed, f"ALT binding {key!r} is missing from keys.json")
    for chord in ("ALT+1 … 9", "ALT+CTRL+1 … 9", "ALT+SHIFT+1 … 9",
                  "ALT+CTRL+SHIFT+1 … 9", "ALT+arrows", "ALT+SHIFT+arrows",
                  "ALT+Page Down / Up", "ALT+SHIFT+T", "ALT+SHIFT+W", "Right CTRL"):
        require(chord in listed, f"keys.json lost {chord}")
    # The sheet only promises keys that exist.
    for chord in listed:
        if chord.startswith("ALT+") and len(chord) == 5:
            require(f'main_mod .. " + {chord[-1]}"' in lua,
                    f"keys.json lists {chord}, which is not bound")


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
    profiles = defaults["guest_desktop_hyprland_profiles"]
    require(set(profiles) == {"dev", "gaming-clean", "gaming-dirty"},
            "the guest rice profiles changed without review")
    require(defaults["guest_desktop_hyprland_profile"] == "dev", "dev is not the default profile")
    themes = defaults["guest_desktop_hyprland_theme_order"]
    for name, profile in profiles.items():
        require(1 <= len(profile["desks"]) <= 9, f"{name} must define one to nine Desks")
        require(profile["theme"] in themes, f"{name} starts on an unknown theme")
        require(re.fullmatch(r"images/[a-z]+/02\.png", profile["wallpaper"]),
                f"{name} must use a wordless 02 identity wallpaper")
        require((ROOT / "themes/assets/hyperlab-trust-v2" / profile["wallpaper"]).is_file(),
                f"{name} wallpaper is missing from the identity set")
    # Store accounts live only in gaming-clean; dirty never gets a store client.
    require("steam" in profiles["gaming-clean"]["packages"], "gaming-clean lost Steam")
    for store in ("steam", "flatpak"):
        require(store not in profiles["gaming-dirty"]["packages"],
                f"gaming-dirty must not install the store client {store}")
    require(not profiles["gaming-dirty"].get("flatpaks"), "gaming-dirty must not install store apps")
    for kind, network in (("dev-vfio", "dev"), ("gaming-clean", "clean"), ("gaming-dirty", "dirty")):
        play = yaml.safe_load((ROOT / f"playbooks/guest-arch-{kind}.yml").read_text())[0]["vars"]
        require(play["workstation_kernel_profile"] == "arch-zen"
                and play["workstation_kernel_remove_fallback"] is False,
                f"guest-arch-{kind} must run the full sync and keep the recovery kernel")
        expected = "dev" if kind == "dev-vfio" else kind
        require(play["guest_desktop_hyprland_profile"] == expected,
                f"guest-arch-{kind} selects the wrong profile")
        spec_name = "arch-dev-vfio" if kind == "dev-vfio" else f"arch-{kind}"
        spec = yaml.safe_load((ROOT / f"vm-specs/{spec_name}.yml").read_text())
        require(spec["network_profile"] == network, f"{spec_name} is on the wrong network")
        if network != "dev":
            require(spec["clipboard"] is False, f"{spec_name} must not share the clipboard")
    gpu = yaml.safe_load((ROOT / "group_vars/all/networks.yml").read_text())["gpu_domain_profiles"]
    require(gpu.get("arch-gaming-clean") == "clean" and gpu.get("arch-gaming-dirty") == "dirty",
            "gaming guests must take the GPU at their own class")
    require("Require every identity wallpaper to match its reviewed digest" in tasks,
            "identity wallpapers are installed without their digest check")

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

    sync = tasks.split(
        "- name: Fully synchronize the Arch package state before installing new packages", 1
    )
    require(len(sync) == 2, "new guest packages are installed without a full system sync")
    sync_task = sync[1].split("\n- name:", 1)[0]
    require("update_cache: true" in sync_task and "upgrade: true" in sync_task,
            "the guest package sync is not a full upgrade")
    require("name:" not in sync_task.split("community.general.pacman:", 1)[1],
            "pacman refuses name together with upgrade")
    require(sync[1].find("- name: Install the official Hyprland guest stack") > 0,
            "the full system sync must run before the install")

    controller = (ROLE / "files/privatestack-guest-theme.py").read_text()
    require('"privatestack-guest/palette.json"' in controller,
            "the theme controller no longer writes the shell palette")
    require('["pgrep", "-x", "waybar"]' in controller,
            "a theme change would start Waybar beside the shell")
    require('"hyperlab-workstation": {' in controller, "the controller lacks the workstation theme")
    theme_lua = controller.split('CONFIG / "hypr/theme.lua"', 1)[1].split('""",', 1)[0]
    require("deg" not in theme_lua and not re.search(r"rgba\([^)]*\) rgba", theme_lua),
            "theme.lua colours must be single rgba() values under the Lua configuration")


def main() -> int:
    check_shell_sources()
    check_hyprland_wiring()
    check_keys_sheet()
    check_role()
    print("HyperLab guest workspace shell contract: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
