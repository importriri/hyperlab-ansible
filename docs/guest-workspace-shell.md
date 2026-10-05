# Guest Workspace Shell

The HyperLab Workspace Shell is the desktop of a HyperLab guest workstation.
It runs inside the guest on Hyprland and Quickshell, and replaces the plain
Waybar session on the preferred path. It looks like a workstation of the
HyperLab platform, not like the host: floating islands instead of the host's
full-width rail, IBM Plex type, one accent colour.

The guest never shows trust. There is no trust badge, no provenance colour
and no GPU ownership in the guest shell: a guest can paint anything, so only
the host frame around it may say what the machine is and what it may reach.

## Rice profiles

Every Arch workstation guest is built by the same roles. A profile only
chooses what that kind of guest starts with, so a new Machine of a kind gets
the same rice without being riced again by hand.

| Profile | Playbook | Network | Theme and wallpaper | Extra software | Default Desks |
| --- | --- | --- | --- | --- | --- |
| `dev` | `guest-arch-dev-vfio.yml` | dev | `hyperlab-workstation`, `dev/02` | IDE stack | Programming, 3D Design, Research, Systems |
| `gaming-clean` | `guest-arch-gaming-clean.yml` | clean | `hyperlab-gaming-clean`, `clean/02` | Steam, Heroic (Epic, GOG), GameMode, MangoHud | Play, Stores, Capture, System |
| `gaming-dirty` | `guest-arch-gaming-dirty.yml` | dirty | `hyperlab-gaming-dirty`, `dirty/02` | Lutris, Wine, winetricks, GameMode, MangoHud | Play, Modding, Launchers, System |

Store accounts that own purchases live only in `gaming-clean`; `gaming-dirty`
never installs a store client. The VM specs `arch-gaming-clean` and
`arch-gaming-dirty` place them on their networks, take the GPU at their own
class of the handoff ladder and do not share the clipboard.

Wallpapers are the wordless `02` images of the reviewed `hyperlab-trust-v2`
identity set in this repository. The role checks each one against the
manifest digest before installing it. A guest carries only its own
profile's identity theme: the identity of another kind of Machine is never
installed nor offered, so a dev Machine cannot wear the clean or dirty
identity. `ALT+SHIFT+T` moves between that identity theme and the neutral
themes (`sakura-circuit`, `neon-terminal`, `moon-library`, `glitch-lab`); a
theme changes colours and style only, the wallpaper stays the guest's
identity wallpaper. `ALT+SHIFT+W` moves between the identity wallpapers.
The role records the identity in `/etc/privatestack/guest-identity-theme`,
root-owned. A guest starts on its profile's theme; a choice you made among
the allowed themes is kept, and a choice another kind of Machine owns is
dropped.

The playbooks run the full Arch sync and the Zen kernel on every run and keep
the stock kernel as the recovery boot entry, so no extra flags are needed.

## Machine, Desk, Project

```text
Machine        one guest, started from the host, with one network and one trust
└── Desk       a group of related work: Programming, 3D Design, Research ...
    └── Project    a named workspace of that Desk, with a folder and programs
        └── windows
```

A Desk is organisation, never a security boundary. Every Desk of a machine
shares the same machine, network and trust. Work that needs a different trust
level belongs in a different Machine, started from the host.

The mapping onto Hyprland is fixed and has no hidden state:

| | Hyprland workspaces |
| --- | --- |
| Desk `d` | `d*10+1` to `d*10+9` |
| slot `s` of Desk `d` | `d*10+s` |

So Desk 1 is workspaces 11 to 19, Desk 2 is 21 to 29, and the current Desk and
project are always read back from the active workspace. A Project owns one
slot; a slot without a project is just "Workspace n".

## Keys

The guest keeps the `ALT` namespace. `SUPER` belongs to the host and
`RIGHTCTRL` to the Looking Glass escape.

| Keys | Action |
| --- | --- |
| `ALT+1` … `ALT+9` | go to Desk n, on the slot last used there |
| `ALT+SHIFT+1` … `9` | move the focused window to Desk n |
| `ALT+CTRL+1` … `9` | go to workspace (project slot) n of this Desk |
| `ALT+CTRL+SHIFT+1` … `9` | move the focused window to slot n of this Desk |
| `ALT+Page_Down` / `ALT+Page_Up` | next / previous Desk |
| `ALT+D` | Desks overview |
| `ALT+Space` | launcher: applications, projects, actions |
| `ALT+N` | new project in the current Desk |
| `ALT+SHIFT+N` | quiet the Desk in front: notifications wait |
| `ALT+H` | the key sheet: every guest key, grouped |
| `ALT+L` | lock (hyprlock) |
| `ALT+Return` | terminal |

Inside the overview: `1`–`9` go to a Desk, arrows move, `Enter` opens the
selected Desk or project, `N` adds a project, `Esc` closes. Inside the
launcher: arrows move, `Tab` jumps to the next section, `Enter` opens.
Log out, restart and power off ask for a second `Enter`.

## Surfaces

| Surface | What it shows | Source |
| --- | --- | --- |
| Context island (top left) | the mark, `WORKSTATION`, Desk / Project | `hyperlab-desk model` + active workspace |
| Status island (top right) | `DESK quiet` or `DESK focus N min` for the Desk in front, GPU, CPU with a short trace, RAM, volume, network, date and time | `hyperlab-desk status`, re-read when the Desk or the helper's state file changes; see below |
| Dock (bottom) | the Desks, the slots of the current Desk, the launcher | `hyperlab-desk model` + Hyprland |
| Desks overview | every Desk with its projects and live window counts | same |
| Launcher | applications, projects of every Desk, actions | desktop entries, the model |
| OSD | Desk changes, volume, helper outcomes | Desk state, PipeWire |
| Key sheet | every guest key, grouped (`ALT+H`) | `keys.json`, also read by the rofi fallback |
| Lock | time, date, password, where you were | hyprlock, `hyperlab-desk lock-label` |
| Desktop | large clock, greeting, where you are, under the windows | the clock, `$USER`, the Desk state |

Every number comes from a real source inside the guest, and a source that
cannot be read hides its readout instead of showing a made-up value:

| Readout | Source |
| --- | --- |
| CPU | `/proc/stat`, sampled every two seconds |
| RAM | `/proc/meminfo` (`MemTotal - MemAvailable`) |
| NET | the interface holding the default route in `/proc/net/route`; `offline` when there is none |
| GPU | `nvidia-smi` utilisation, only when the guest has an NVIDIA driver |
| VOL | the default PipeWire sink |

## Configuring Desks and projects

`hyperlab-desk` owns the configuration. The first readable source wins:

1. `~/.config/hyperlab-workspace/desks.json` — your own Desks;
2. `/etc/hyperlab-workspace/desks.json` — the image default, rendered from
   `guest_desktop_hyprland_workspace_desks`;
3. the built-in four Desks.

A file that does not validate is never half-applied: the next source is used
and the overview says that your file was refused and why. A later edit never
overwrites a refused file.

```sh
hyperlab-desk project-new 1 HyperLab --cwd ~/src/hyperlab-ansible
hyperlab-desk project-new 2 "Blender renders" --cwd ~/renders --launch blender
hyperlab-desk project-remove 1 3
hyperlab-desk project-save 1 1      # remember the applications open there now
hyperlab-desk project-forget 1 1    # back to the launch commands
hyperlab-desk quiet toggle          # quiet the Desk in front (ALT+SHIFT+N)
hyperlab-desk quiet on --desk 2     # quiet Desk 2 whenever it is in front
hyperlab-desk focus 50              # quiet the Desk in front for 50 minutes
hyperlab-desk focus stop
hyperlab-desk track on              # opt in to time per Desk (off by default)
hyperlab-desk track report --days 7
hyperlab-desk track clear           # erase every recorded minute
hyperlab-desk model            # what the shell sees
hyperlab-desk check FILE       # validate a desks.json before using it
```

Opening a project goes to its workspace and, only when that workspace is
empty, starts its programs there in its folder (`kitty` by default).

A project also remembers the applications it had. When you leave a
project's workspace, the helper records which applications are open there,
matching each window's class to a desktop entry (`StartupWMClass`, then the
entry id, then a reverse-DNS id ending in the class). Only the entry ids are
kept, in `~/.local/state/hyperlab-workspace/desks-state.json`: never a
process's arguments, which can carry tokens, and nothing for a window that
matches no entry. Opening the project on an empty workspace then starts
those entries' `Exec` lines in the project's folder, field codes dropped,
instead of the launch commands.

- Leaving an empty workspace keeps the memory, so passing through a project
  at the start of a session does not forget it; `project-forget` does.
- An entry that is gone, hidden, or has a field code embedded in an argument
  is never run; if nothing usable is left, the launch commands apply.
- Removing a project forgets its applications.
- This reopens applications, not their documents or window layout; an
  application that restores its own session (a browser, an editor) does that
  part itself.

A Desk can be quiet. While a quiet Desk is in front, mako is in its
`do-not-disturb` mode: notifications are hidden, not dropped, except critical
ones and the helper's own confirmation; those still pending show again when
another Desk comes to the front. The helper sets the mode whenever the Desk
in front changes, and Hyprland runs `hyperlab-desk quiet sync` at session
start. `hyperlab-desk status` reports `quiet`. Who draws notifications, mako
or the shell, is [ADR 0027](adr/0027-guest-notification-owner.md), proposed.

A focus is a quiet Desk for a set time: `focus 50` quiets the Desk in front
and, fifty minutes later, puts back the quiet state it found, with a notice.
`status` reports `focus_until`.

Time tracking is off until you turn it on. Once on, a sampler that Hyprland
starts with the session credits each minute to the Desk and slot in front,
only while the session is unlocked; a longer gap (suspend, a stopped
sampler) is credited to nothing. The totals stay in
`~/.local/state/hyperlab-workspace/desks-time.json` for five weeks, are never
sent anywhere, and `track clear` erases them. It cannot tell an idle
unlocked session from work. The sampler also ends a focus on time; it runs
once per session and stops when Hyprland is gone. While tracking is on,
each card in the Desks overview shows that Desk's time today.

## Files

| Path | Role |
| --- | --- |
| `/etc/xdg/quickshell/hyperlab-workspace/` | the shell (`qs -c hyperlab-workspace`) |
| `/usr/local/bin/hyperlab-desk` | Desks, projects and workspace arithmetic |
| `/usr/local/bin/hyperlab-workspace` | session start and the key entry points |
| `/etc/hyperlab-workspace/desks.json` | the image default Desks |
| `~/.config/privatestack-guest/palette.json` | the active guest theme, read live by the shell |
| `~/.local/state/hyperlab-workspace/shell.log` | the shell's own log |

Source: `roles/guest_desktop_hyprland/files/quickshell/hyperlab-workspace/`.
`shell.qml` wires one theme, one Desk state, one set of readouts and one
surface controller into every surface. Logic that does not need Quickshell
lives in `desks.js`, `stats.js` and `launcher.js` and is tested directly.

## Look

- the focused window wears a border running from the theme's accent to its
  companion colour at 45 degrees, in the reviewed Lua gradient form
  (`{ colors = { … }, angle = … }`), and a glow of the accent; inactive
  windows dim slightly;
- terminals are translucent over the blurred wallpaper;
- the islands and panels blur what lies behind them, through a Hyprland
  layer rule in the reviewed Lua form (`hl.layer_rule`); only pixels above
  the alpha floor are blurred, and the wallpaper layer is not;
- an empty workspace shows the desktop clock and greeting;
- a Desk change is announced by name, and the context island catches a
  highlight;
- a readout that runs hot (85 % and above) turns to the urgent colour.

## Themes

The shell follows the active guest theme through `palette.json`, written by
`privatestack-guest-theme`, so `ALT+SHIFT+T` recolours it without a restart.
Each profile theme uses its identity wallpaper as `01.png`, before the
generated `bootstrap.png`. More wallpapers for a theme go in
`/usr/share/backgrounds/privatestack-guest/<theme>/desktop/` and
`.../lockscreen/` as `02.png`, `03.png` and so on.

## Recovery

Nothing depends on the shell being up:

- every key calls `hyperlab-workspace` or `hyperlab-desk`, never the shell
  directly; rofi stands in only when the shell is not running: the launcher,
  the overview and the new-project prompt then become rofi menus. A shell
  that is running but slow is asked again, never replaced, and no key opens
  rofi directly;
- `hyperlab-workspace session` restarts a shell that crashes after a normal
  run, and starts Waybar if the shell fails three times in a row;
- the lock is hyprlock, a separate program, so a shell crash can never leave
  the session unlocked or unlockable;
- a guest reached through Looking Glass never locks itself when idle:
  Hyprland stops screen capture while a session is locked, so Looking Glass
  would show nothing. The host session lock protects that window. `ALT+L`
  still locks on request; Looking Glass then shows no picture until the
  password, typed into the window, unlocks it;
- no guest turns its display off: a virtual display has no panel to save,
  and a guest behind Looking Glass must keep its output on;
- `guest_desktop_hyprland_shell: waybar` keeps the plain bar for a single
  run; no playbook or inventory file sets it, so every workstation Template
  (`workstation-dev`, `workstation-dev-standard`) gets the same shell
  (`tests/workstation_guest_contract.py`).

The role installs the shell only for the reviewed Quickshell API series
(`guest_desktop_hyprland_quickshell_series`, currently 0.3).

## Verification

| Contract | Proves |
| --- | --- |
| `tests/guest_desk_helper_contract.py` | Desk arithmetic, slot memory, project slots and launches, remembered applications, quiet Desks, focus, time tracking, refused configuration |
| `tests/guest_workspace_shell_runtime_contract.py` | the real QML in an offscreen scene: readouts, Desks, overview, launcher, refusals |
| `tests/guest_workspace_shell_contract.py` | no trust or host knowledge in the guest, lock in hyprlock, keys and fallbacks, role wiring |
| `tests/guest_presentation_contract.py` | exactly one bar, fullscreen and tearing policy |
| `tests/keybinding_namespace_security_contract.py` | every guest key stays in `ALT` |

With `HYPERLAB_RENDER_OUT=dir`, the runtime contract saves a capture of each
scenario. The Quickshell stand-ins it uses are described in
[`tests/quickshell_stubs/README.md`](../tests/quickshell_stubs/README.md).

Not proven in software, and therefore physical acceptance on a guest: the
real Quickshell runtime, layer-shell keyboard focus, Hyprland IPC events,
PipeWire, and the look with IBM Plex installed.

Known gaps:

- notifications are still drawn by mako, styled by the theme rather than the
  shell; the shell shows the quiet state and a focus, not the time report yet
  ([ADR 0027](adr/0027-guest-notification-owner.md), proposed).
