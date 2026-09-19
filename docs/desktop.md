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

Sway remains the recovery compositor. Detailed session-lifecycle evidence is
recorded in
[`host-hyprland-session-lifecycle-acceptance-2026-09-18.md`](host-hyprland-session-lifecycle-acceptance-2026-09-18.md).

## HyperLab Gate

The Nitro host login surface now has a dedicated HyperLab identity rather than
following the selected Green, Violet, Blue or Red desktop palette. Ly renders a
near-black Gate with a crimson Matrix animation, cool neutral text and the
`HyperLab Gate` login box. The Matrix frame delay is 25 ms after physical visual
tuning on the Nitro host.

The Gate changes presentation only. Session provenance, authentication,
compositor ownership and the curated `HyperLab Hyprland` / `HyperLab Sway`
catalog remain owned by the session-lifecycle contract.

The Gate was applied twice on the Nitro host with the second pass at
`changed=0`, then exercised through a real logout and return to managed Sway.
Detailed evidence and the validation-harness note are recorded in
[`host-ly-gate-acceptance-2026-09-18.md`](host-ly-gate-acceptance-2026-09-18.md).

## Dual-compositor product contract

HyperLab is one desktop product with two first-class compositor backends.
Hyprland is the preferred day-to-day compositor, while Sway remains fully
supported and is also the recovery compositor.

Choosing `HyperLab Hyprland` or `HyperLab Sway` must preserve the same HyperLab
product semantics: trust model, themes, HyperLab Shell, Control Center, drawers,
VM workflows, wallpaper policy, keyboard policy, lock/power controls and
security meaning. Only compositor-native implementation primitives may differ
behind the shared adapter.

A feature is not complete when it works only on Hyprland. Cross-compositor
parity is a release contract. Sway may expose a compositor limitation through a
different truthful presentation, but it must not silently lose the HyperLab
function.

Quickshell is the shared HyperLab Shell target for both compositors. It is not a
Hyprland-specific shell and it does not become an operational authority;
`hyperlabctl`, reviewed specifications and contracts remain authoritative.


### Shared shell migration

Phase 2A stages the first compositor-neutral Quickshell source under
`/etc/xdg/quickshell/hyperlab`.

The stage is deliberately non-active. It installs the reviewed Quickshell 0.3
runtime and a generic 37-pixel Layer Shell foundation, but does not launch it,
replace Waybar, replace the resident GTK HyperLab surfaces, or introduce
compositor-specific imports.

Waybar and the GTK drawer/Control Center remain the authoritative live surfaces
until the Quickshell implementation reaches functional parity and passes real
validation under both managed Hyprland and managed Sway sessions.

No placeholder control is allowed to impersonate a working HyperLab action.
Operational controls move only when they are wired to the existing reviewed
backend authority.

## Keybinding security boundary

Host and guest compositor shortcuts use deliberately different namespaces:
`SUPER` belongs to the managed host desktop and `ALT` belongs to managed Linux
guests. Looking Glass keeps `RightCtrl` as its transport escape key.

This is a defence-in-depth rule in addition to captured-input isolation.
Guest-facing cheatsheets are complete only inside their authorized scope and
must never expose the host or hypervisor control plane.

See [`keybinding-security.md`](keybinding-security.md) for the binding,
collision and information-disclosure contract.

### Hyprland-first shell pilot

HyperLab is migrating to Quickshell on the preferred Hyprland backend first so
the validated Nitro host can move to Hyprland as its daily desktop without
waiting for the later Sway parity campaign.

The Quickshell source remains owned by `host_desktop_common`. Hyprland owns only
the session-lifecycle unit that starts the shared `hyperlab` configuration after
the managed Hyprland runtime has published its Wayland environment.

The pilot is bound to `hyperlab-hyprland-session.target`; it is not globally
enabled and cannot start as a generic user service. Sway remains the recovery
desktop and its Waybar/GTK surfaces are preserved.

This is an implementation order, not a product split. Sway parity remains a
release requirement after the Hyprland daily-driver cutover.

### Hyprland display scale

The Nitro physical-host Hyprland session uses display scale `1.0`.

The initial generic `auto` setting selected scale `1.5` on the internal
1920x1080@144 panel, which reduced the effective desktop workspace too much for
the HyperLab daily-driver layout. A live Lua-provider test changed the active
`eDP-1` output from `1.5` to `1.0` successfully.

The role keeps the value as an overridable HyperLab variable rather than binding
the configuration to the Nitro output name, so another reviewed hardware
profile can select a different scale without forking the Hyprland template.

### Quickshell Variants runtime compatibility

The first physical Hyprland pilot exposed a Quickshell 0.3.1 runtime issue in
the shared per-screen bar delegate. The service remained active, but a
`required property var modelData` declaration caused variant construction to
fail before the screen value could be injected.

The shared bar therefore uses the Quickshell 0.3 model-data injection contract
with a normal `property var modelData`. Runtime acceptance requires the panel
to instantiate successfully and reserve its configured 37-pixel top zone.

### Shared Quickshell read-only status core

The first real HyperLab Shell data surface is compositor-neutral and read-only.

It presents the product identity, host-owned trust state, RAM/GPU/VM summary and
clock. Trust uses the existing event-driven `hyperlabctl` stream through the
reviewed `privatestack-hyperlab` presentation bridge. RAM, GPU and VM summaries
retain the existing 30-second slow cadence.

Shared QML does not call `hyprctl`, `swaymsg`, privileged helpers, arbitrary
shells or hypervisor internals. Operational controls remain closed until their
reviewed `hyperlabctl` actions are migrated separately.

This stage is shared source for both Hyprland and Sway even though Hyprland is
the first physical runtime acceptance target.

### Shared workspace state and semantic shell theme

The HyperLab Shell workspace row is compositor-neutral. Shared QML consumes
only the reviewed `privatestack-compositor-adapter workspace-watch` JSON
stream. The adapter translates Sway workspace events and Hyprland event-socket
notifications into the same host-local contract.

Workspace presentation covers numbered workspaces 1 through 9. This phase is
read-only: navigation remains owned by the existing keyboard contract until
interactive shell actions are reviewed separately.

Quickshell colours are generated by `tools/palette/render_palette.py` from the
same palette source used by Sway, Hyprland, GTK, Waybar, Rofi and the terminal.
The active user copy is
`~/.config/hyperlab/palette-quickshell.json`.

Quickshell watches that file directly. A theme change therefore updates the
shared shell without a polling loop and without duplicating colour constants
inside QML. Semantic domain colours remain invariant across appearance themes.
