# Host desktop

`host_desktop_sway` installs the Sway session used on the physical laptop. It is
part of `playbooks/lab.yml` and is applied before the Looking Glass host role.
The headless foundation does not depend on it.

## HyperLab surfaces

The resident GTK4 process owns two Layer Shell surfaces:

- a `500×560` drawer at the top-left of the display;
- an `1180×760` full Control Center opened explicitly.

The drawer is attached to the interface rather than floating beside it. Waybar
is 37 pixels high, so the drawer uses the left screen edge and begins immediately
below the bar: top margin `0`, left margin `0`. Waybar's exclusive zone already
provides the 37-pixel vertical offset; the drawer does not reserve work area.

Waybar routes the HyperLab controls consistently:

| Input | Result |
| --- | --- |
| left click on `HyperLab` | compact VMs drawer |
| right click on `HyperLab` | compact System drawer |
| middle click on `HyperLab` | full Control Center |
| left or right click on `TRUST` | compact System drawer |
| middle click on `TRUST` | full Control Center, System section |

Closing a surface hides it. The resident process stays warm so the next open does
not import GTK and rebuild the model from scratch.

## Keyboard controls

| Action | Shortcut |
| --- | --- |
| HyperLab action palette | `Mod+F1` |
| System drawer | `Mod+F2` |
| diagnostics terminal | `Mod+F3` |
| VMs drawer | `Mod+F4` |
| application launcher | `Mod+d` |
| fullscreen | `Mod+F` |
| file manager | `Mod+Shift+F` |
| cycle palette | `Mod+Shift+T` |
| cycle palette on the Nitro 5 | physical Nitro key (`XF86Presentation`) |
| switch public/personal wallpaper pool | `Mod+Shift+W` |
| cycle keyboard layout | `Mod+Ctrl+Space` |
| toggle Waybar | `Mod+Shift+B` |
| lock | `Mod+Escape` |

Fullscreen uses Sway directly. There is no second fullscreen controller.

## Themes and wallpapers

Green, Violet, Blue and Red share one palette across Sway, Waybar, Rofi, Foot,
GTK, Swaylock and the HyperLab surfaces. The selected runtime state lives under
`~/.config/hyperlab/`.

Public wallpaper pools are installed by the role. Personal pools stay in the
user home and never enter Git. Missing personal images fall back to the matching
public palette instead of leaving the session without a background.

## Waybar fallback

Waybar is the primary 37-pixel cockpit. Native Swaybar remains configured but
hidden and is restored by the Waybar supervisor after repeated startup failures.
The fallback exists so a cosmetic process cannot remove the basic controls from
the session. The supervisor holds an advisory lock for its complete lifetime;
`swaymsg reload` may execute the launcher again, but the extra launcher exits
without replacing the active supervisor or creating a second Waybar.

## Validation

The structural contract checks the Layer Shell boundary, surface sizes, routing,
left/top attachment, palette integration and dead-helper removal. The Nitro gate
still has to confirm the result visually and run the desktop role twice with the
second pass at `changed=0`.

## Host Hyprland migration

The first controlled physical-host Hyprland launch passed on the Nitro
validation host on 2026-09-18. The launch used a dedicated TTY while the
established Sway session remained available as the recovery surface.

The internal `eDP-1` panel was acquired through the Intel `i915` host GPU at
1920×1080 and approximately 144 Hz. The NVIDIA GPU remained on the VFIO
boundary. Hyprland exited cleanly and Sway IPC remained functional after
recovery.

The follow-up session-lifecycle milestone is accepted on the Nitro host.
HyperLab now owns compositor-specific user targets for Hyprland and Sway,
publishes and clears compositor environment through the lifecycle wrapper, and
publishes the IPC socket belonging to the exact active Sway PID.

Ly exposes only the managed `HyperLab Hyprland` and `HyperLab Sway` entries.
Native package session files remain installed but cannot bypass the HyperLab
wrapper from Ly.

A physical Sway → Hyprland → Sway round-trip passed managed environment,
target ownership, teardown, helper and IPC checks. The real closeout re-apply
was idempotent at `changed=0`.

Sway remains the recovery compositor. Quickshell and the final Ly visual theme
remain later presentation gates. Detailed evidence is recorded in
`host-hyprland-session-lifecycle-acceptance-2026-09-18.md`.
