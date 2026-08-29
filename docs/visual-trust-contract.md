# Visual trust contract

The HyperLab desktop uses color for two different jobs. Theme color identifies
the active visual palette and focus. Trust color identifies a security or
workload domain.

Those meanings must not be collapsed into one signal.

## Trust domains

The current domain colors are:

| Domain | Color |
| --- | --- |
| clean | `#72f2a5` |
| dev | `#5b8cff` |
| services | `#35e4dd` |
| dirty | `#ff9d45` |
| lab | `#b184ff` |

GPU handoff uses the trust ladder:

```text
clean(3) -> dev(2) -> dirty(1) -> lab(0)
```

During one boot the GPU may only move down that ladder. Raising GPU trust
requires a reboot.

`services` is a network/security domain but is not a GPU-handoff rung. UI code
must not infer the GPU ladder from the visual domain list.

## Window focus

A focused window keeps the active theme accent.

That rule makes focus location stable even when several trust domains are
visible at once. Trust color is used for unfocused/domain indicators where the
compositor can express that distinction without changing the meaning of focus.

Compositor limits are part of the contract. Hyprland can apply per-window
active/inactive border overrides; Sway's standard client color classes are
global. The host must not fake a per-window trust border by recoloring every
unfocused client together.

Where Sway cannot express the intended border semantics directly, the trust
signal belongs in an adjacent indicator owned by the HyperLab UI rather than in
a misleading compositor rule.

## Keyboard RGB

The Nitro keyboard is another output for the same semantic model, but it is not
restricted to trust display.

The control panel is intended to expose several RGB sources:

- Trust: derive colors from HyperLab trust state;
- Theme Sync: derive colors from the active palette;
- Ambient: sample monitor regions and map them to the four keyboard zones;
- Static: one color across all zones;
- Per-zone: four explicit colors;
- Gradient: interpolate a small palette across the zones;
- Load/Temperature: map measured system state to color;
- Audio Reactive: derive color from PipeWire level data.

Hardware-native animated effects remain a separate capability and stay hidden
until their exact WMI path is physically validated.

All modes share brightness and rate policy. Monitor or audio reactive modes must
include smoothing and a bounded update rate because the keyboard path crosses a
reverse-engineered platform WMI interface.

## Source of truth

`tools/palette/palette.yml` owns one top-level semantic domain palette. Theme
variants own appearance tokens only; the renderer merges the same domain tokens
into every generated GTK, Waybar, Rofi, Foot and Sway fragment.

The Control Center consumes those generated tokens instead of carrying a second
set of hexadecimal domain colors. Static domain assets and tests must match the
same semantic values.

Terminal ANSI slots are theme appearance as well. They have their own palette
tokens rather than borrowing `dev`, `lab` or `services`; changing trust policy
must not recolor ordinary terminal ANSI output as a side effect.

Palette-specific theme accents remain separate. Changing the theme must not
silently change what `clean`, `dev`, `dirty` or `lab` mean.

## Host-owned window provenance

Trust identity belongs to the hypervisor, not to the guest. A guest must never
be able to declare itself `clean`, `dev`, `dirty`, `lab` or `services`.

For a managed VM surface, the host resolves the domain identity to its reviewed
VM specification and derives trust identity from `network_profile`. Looking
Glass, SPICE and future seamless-application surfaces inherit that host-owned
provenance. Guest-provided window titles, application IDs and application names
are presentation metadata only and are not authority for trust classification.

Host-native applications are neutral host surfaces. `HOST` is not a sixth
network domain and must not be represented as `clean`.

The canonical visual identities remain:

- `clean`: green;
- `dev`: blue;
- `services`: cyan;
- `dirty`: orange;
- `lab`: violet;
- host-native/unclassified: neutral.

The selected appearance theme is independent from those meanings.

### Focus and keyboard trust indication

Trust-mode keyboard RGB follows the host-resolved provenance of the currently
focused surface. Focusing a managed guest surface selects that surface's trust
identity; focusing a host-native surface returns the keyboard to the neutral
host indication.

The keyboard is an additional physical trust signal, not the source of truth.
Control Center state, Waybar/domain indicators, window/seamless-app markers and
keyboard RGB must derive from the same host-owned classification.

Theme Sync, static, per-zone, gradient, load/temperature and audio-reactive
lighting remain presentation modes. They must not be mistaken for Trust mode.

### GPU trust is related but distinct

The GPU trust ladder controls which reviewed VFIO domain may receive the dGPU
during one host boot. Window provenance describes which security/network domain
owns a visible managed surface.

`services` therefore has a visual trust identity while remaining structurally
outside GPU handoff. Visual provenance must not infer GPU eligibility from the
presence of a trust color.

### Seamless application requirement

A future seamless application must carry provenance assigned by a host-owned
launcher/broker from the managed VM identity. The guest may provide an
application name, icon or title, but it cannot choose or override the trust
marker.

A seamless-app feature is not accepted until a user can distinguish host-native
applications from `clean`, `dev`, `services`, `dirty` and `lab` guest
applications through host-controlled visual and physical signals.
