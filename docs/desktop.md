# Desktop cockpit

The `desktop` role installs the Sway session used on the laptop host. It owns
Waybar, the compact HyperLab drawer, the full Control Center, runtime themes,
wallpapers, keyboard switching and the native Swaybar fallback.

The desktop is part of `playbooks/lab.yml`. It must be applied before the
Looking Glass host role because the normal laptop workflow expects a working
Sway session first.

## Main controls

| Action | Shortcut or click |
|---|---|
| Open the HyperLab action palette | `Mod+F1` |
| Open the terminal cockpit panel | `Mod+F2` |
| Run diagnostics in Foot | `Mod+F3` |
| Open the compact VM drawer | `Mod+F4`, or any mouse button on `HyperLab` |
| Open the drawer System tab | any mouse button on `TRUST` |
| Open the complete controls menu | `Mod+Shift+P`, or click `CTL` |
| Cycle Green, Violet, Blue and Red | `Mod+Shift+T` |
| Toggle public and personal wallpapers | `Mod+Shift+W`, or click `PUB/PVT` |
| Cycle Italian, English (US) and Arabic | `Mod+Ctrl+Space`, or click the keyboard label |
| Toggle Waybar | `Mod+Shift+B` |
| Toggle terminal opacity | `Mod+O` |
| Toggle fullscreen for the focused window | `Mod+F` |
| Lock the session | `Mod+Escape` |

The UI text is English. The initial keyboard layout comes from the selected
hardware profile and defaults to Italian on the current Nitro and Predator
profiles. Runtime choices are stored below `~/.config/hyperlab/` and survive a
Sway reload.

## HyperLab surfaces

One resident GTK4 process owns two Layer Shell surfaces:

- a `500×560` drawer anchored below the left side of Waybar;
- an `1180×760` full Control Center opened explicitly from the drawer or the
  controls menu.

Sway starts the process with `--warm`, which builds the drawer before the first
click. Closing either surface hides it instead of stopping the process. A later
open maps the existing window and refreshes status only when the cached data is
older than five seconds.

The drawer contains two tabs:

- **VMs** lists managed and unmanaged libvirt domains and their primary action;
- **System** summarizes host health, GPU ownership, trust domains and recovery
  paths.

The full Control Center adds image, network, policy, VFIO, activity and
diagnostic views. Privileged operations are still resolved through
`hyperlabctl`; the GTK layer does not bypass the lifecycle playbooks.

## Runtime themes

The selected palette is shared by Sway, Waybar, Rofi, Foot, Superfile, GTK,
Swaylock and the resident HyperLab process. The four supported values are:

```text
green
violet
blue
red
```

`privatestack-theme` copies the selected fragments into user-owned active files,
reloads Sway and Waybar, and tells the resident GTK process to reload its palette
without a logout. New Foot windows read the active palette at startup; an
already running terminal keeps the colors it loaded when it opened.

Ly runs on a TTY before the user session. Ansible therefore applies the
configured default palette to `/etc/ly/config.ini`; runtime theme changes do not
rewrite the login manager.

## Wallpaper modes

The repository contains twenty public 16:9 PNG files for each palette under
`roles/desktop/files/wallpapers/<theme>/`. Ansible installs them below
`/usr/share/backgrounds/privatestack/public/<theme>/`.

Personal wallpapers are host-local and never enter Git. The expected layout is:

```text
~/.local/share/hyperlab/wallpapers/personal/<theme>/01.png
...
~/.local/share/hyperlab/wallpapers/personal/<theme>/NN.png
```

Each personal theme may contain a different number of consecutively numbered
images. Numbering must start at `01.png` and contain no gaps. An empty personal
theme falls back to the matching public pool and marks the Waybar state as a
fallback. Swaylock uses the same source and palette but chooses an image three
positions after the current desktop image. The wallpaper daemon rotates every
60 seconds by default.

## Waybar and fallback behavior

Waybar is the primary cockpit and runs at 37 pixels on the tested Nitro setup.
The left side begins with `HyperLab`, the `TRUST` group and workspaces. Status
reads are warmed in the background so hovering the trust group does not query
libvirt on pointer entry.

Sway's native bar remains configured but hidden. The `privatestack-waybar`
supervisor enables it after three rapid Waybar failures. `Mod+Shift+B` controls
the active implementation, so the same shortcut still works during fallback.

## Validation

The repository verifier checks the desktop structure without requiring a
display. The hardware gate still requires a real Sway session and confirms:

- no Sway configuration warning banner;
- stable Waybar startup;
- immediate drawer reopening;
- separate `CTL` and `PUB/PVT` click targets;
- live theme changes in the resident HyperLab process;
- keyboard cycling through IT, EN and AR;
- public and personal wallpaper fallback behavior;
- a second desktop apply with `changed=0`.
