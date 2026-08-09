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
