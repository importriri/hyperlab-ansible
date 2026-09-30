# HyperLab theme system

The HyperLab Shell uses a registry of declarative theme packages rather than a
hard-coded list of colour variants.

## Ownership

A theme may own:

- Quickshell presentation;
- GTK presentation;
- Rofi presentation;
- terminal appearance;
- lockscreen appearance;
- wallpaper policy;
- keyboard RGB policy.

Themes do not own security classification.

Trust identity remains host-owned. A guest cannot select `clean`, `dev`,
`services`, `dirty` or `lab` for itself.

## Keyboard RGB

Keyboard RGB is a first-class theme output.

On hardware exposing the validated Nitro four-zone interface, theme RGB reaches
the keyboard only through `/usr/local/bin/hyperlab-nitro-control`.

Themes and Quickshell must never write sysfs directly and must never gain a
generic privileged execution primitive.

`trust-model` derives RGB colours from host-owned trust provenance.

Ordinary themes may use Theme Sync or another reviewed presentation mode. If a
machine has no compatible RGB device, the rest of the theme still applies.

## Terminals

The host presentation target is Foot.

The managed Hyprland workstation guest presentation target is Kitty.

The theme engine therefore needs adapters for both instead of forcing one
terminal onto both environments.

## Migration

Green, Violet, Blue and Red and their legacy wallpaper pools are migration
inputs only. They will be deleted once the registry, new visual assets,
Quickshell selector and physical Nitro acceptance are complete.

## Canonical visual assets

`themes/assets/hyperlab-symbols-v1/` is the first canonical HyperLab visual
asset set.

Its ten PNG files are pinned byte-for-byte by SHA256. The images replace the
legacy visual library, but their trust-domain roles are intentionally not
inferred from filename, dominant colour or appearance.

`trust-model` may consume the set only after its semantic mapping has been
explicitly reviewed.

The old Green/Violet/Blue/Red wallpaper pools remain only as rollback material
during migration and are deleted after the new theme path passes physical Nitro
acceptance.

## Trust Model visual contract

`trust-model` uses a restrained near-black appearance. Generic focus,
telemetry and ordinary controls remain neutral; canonical trust colours are
reserved for actual provenance indicators.

The canonical identities are:

- host: neutral grey `#8b949e` — the control plane, above the GPU ladder and
  never a rung on it;
- unclassified: no colour at all, drawn as a dashed neutral outline so it can
  never be mistaken for HOST or for an identity;
- clean: green `#72f2a5` — rung 3;
- dev: blue `#5b8cff` — rung 2;
- services: cyan `#35e4dd` — outside the GPU handoff entirely;
- dirty: orange `#ff9d45` — rung 1;
- lab: violet `#b184ff` — rung 0.

Every variant publishes all six as `dom_*`, including the legacy Green, Violet,
Blue and Red appearances, so provenance means the same thing under every theme.
`tools/palette/audit_palette.py` holds the five trust domains apart by hue and
checks HOST only for readability, because HOST carries no hue claim.

A provenance marker never travels alone: the shell always pairs it with its
word, so provenance is legible without relying on colour vision. An identity
outside this set, or an incomplete `dom_*` table, resolves to neutral text —
never to a borrowed colour. Diagnostics reports an incomplete table rather than
letting the shell quietly invent one.

The focused host-owned provenance drives Trust-mode keyboard RGB. On the Nitro
four-zone backend every zone carries the same canonical identity colour. A
host-native or unclassified surface returns the keyboard to the neutral host
indication.

The keyboard remains an output, never a source of security state.

The trust wallpaper set is `hyperlab-symbols-v1`, but exact symbol-to-trust
assignment remains pending visual review. Filenames and image colours are
explicitly forbidden from becoming trust authority.

The product identity is separate and neutral: the generated "Isolation Ring"
family is the default product wallpaper and the lock surface asset, and it
carries no provenance at all. See
[`wallpaper-art-direction.md`](wallpaper-art-direction.md).

## Theme compiler

`tools/theme_render.py` compiles a declarative theme into the formats consumed
by HyperLab.

The Trust Model currently renders:

- Quickshell semantic JSON;
- GTK and Waybar colour fragments;
- Rofi tokens;
- Foot host colours;
- Kitty guest colours;
- Hyprland and Sway compositor tokens;
- lockscreen colours;
- the four-zone keyboard RGB identity map.

Generated files live under `themes/<theme>/rendered/` and must reproduce
deterministically from the theme source.

The generated preview is not a security source of truth and does not activate
the theme. It exists only for visual review before runtime deployment.

## Trust wallpaper rotation engine

`tools/trust_wallpaper_engine.py` is a pure presentation planner.

It receives an already host-resolved trust identity and the reviewed
`hyperlab-trust-v2` pool and returns the wallpaper/RGB presentation plan.

It does not discover trust itself and it performs no compositor, hardware or
privileged mutation.

The candidate pool rotates on 30-minute boundaries, but only inside the current
trust identity. A trust transition selects the destination trust pool
immediately.

Wallpaper variants may change while trust remains constant. Keyboard RGB does
not follow the wallpaper variant: all four zones continue to represent the
canonical host-owned trust identity.

The focused-surface provenance resolver and runtime application bridge are
separate gates. This separation prevents the old boot/GPU trust claim or
guest-controlled window metadata from accidentally becoming visual trust
authority.

## Focused-surface provenance

Trust Model presentation follows host-resolved focused-surface provenance.

A managed graphical guest surface is resolved through this chain:

`focused host PID -> HyperLab launcher registration -> managed VM name ->
reviewed vm-spec -> network_profile -> trust identity`.

The resolver verifies process start time as well as the approved host executable,
so a recycled PID cannot inherit an old guest identity. The VM specification is
also pinned by SHA256 for the lifetime of a registration; specification drift
invalidates that presentation provenance rather than silently changing trust.

Guest-controlled title text, application names and other presentation metadata
never assign trust.

Host-native surfaces resolve to neutral `HOST`. A surface that looks like a
managed transport but lacks valid host registration is `unresolved`; it may not
drive wallpaper or keyboard RGB until host provenance is recovered.

The resolver remains read-only. Its `stream` mode answers one correlated
request per line for the shell; see the live chain in
[`hyperlab-shell.md`](hyperlab-shell.md#focused-surface-provenance).

A surface that looks like a managed transport but reports no PID is also
`unresolved`: without a process identity no registration can be verified.

## Managed surface runtime binding

HyperLab launchers publish managed graphical provenance before replacing
themselves with the reviewed graphical client.

Because exec preserves the process ID and process start time, the runtime
registry binds a host process identity to a managed VM without trusting guest
window titles or application labels.

The per-user registry lives under
`$XDG_RUNTIME_DIR/hyperlab/surface-provenance.json`. Its directory is 0700 and
the registry is 0600. Writes are atomic, stale process identities are pruned and
each registration pins the reviewed VM specification by SHA256.

The shared compositor adapter exposes additive `focused-window-json` and
`focused-window-watch` primitives. The original `focused-window` API remains
unchanged.

The compositor provides the focused host PID. The host-owned provenance
resolver remains the authority that maps this to VM specification,
`network_profile` and trust identity.

## Read-only trust presentation coordinator

`tools/trust_presentation_coordinator.py` joins the focused-surface provenance
resolver to the trust wallpaper planner without applying either wallpaper or
keyboard RGB.

The coordinator consumes one PID-bearing surface snapshot or an event stream,
resolves the host-owned trust identity, and emits a presentation plan containing
the wallpaper that would be selected and the four RGB values that would be
requested.

Resolved host-native surfaces map to neutral `HOST`. Resolved managed guest
surfaces map through their reviewed VM specification and `network_profile`.

A managed-looking surface whose provenance cannot be verified enters `hold`:
neither wallpaper nor RGB receives a requested value. This is intentionally
different from silently treating an unresolved guest as HOST.

Guest-controlled title and application metadata remain non-authoritative.

The coordinator itself contains no compositor calls, hardware calls, privilege
boundary or filesystem writes. A later actuator gate may consume only reviewed
`planned` output.

## Focus provenance accents and keyboard RGB

`hyperlab-focus-accent.service` (wanted by the graphical session, so it runs
under Hyprland and Sway alike) mirrors existing authority onto presentation.
It decides no identity:

- the focused surface's identity comes from the reviewed surface provenance
  resolver, exactly as for the rail badge;
- the host trust claim comes from `hyperlabctl watch --field trust`,
  validated at its canonical rung;
- colours come only from the rendered trust-model map
  (`hyperlab-rgb-map.json`), itself pinned to the canonical trust colours.

**Accent.** A resolved surface's border takes its identity colour, bound to
that one window through the compositor adapter, so an identity can never
follow focus onto another window. A surface without a resolved identity
carries no trust colour, and a window whose provenance is lost returns to
the theme border. The generic focus token stays neutral. Sway can only
colour whatever is focused, so it reports accents as unsupported and keeps
its neutral border rather than risk showing one window's identity on the
next.

Accents are enabled only under `trust-model`. Other themes receive their own
appearance border, never a provenance colour. Cleanup does not read the live
`general:col.active_border`: the theme selection file changes before the
compositor reload, which can be deferred. The high-level focus actuator instead reads the selected
theme's root-owned palette under `/usr/share/hyperlab/palettes`. It supplies an
explicit validated colour to the adapter; the adapter owns only IPC translation
and contains no theme selection or palette policy.

The installed Nitro Hyprland 0.56.2 build
`efb50993780079460b0cbed1363e2166a2de1d9f` was probed on a disposable Foot on
2026-09-26. `hyprctl setprop address:WINDOW activebordercolor -1` returned
`unknown request`. The exact Lua candidate was:

```lua
hl.dsp.window.set_prop({
    prop = "active_border_color", value = "-1", window = "address:WINDOW"
})
```

It returned `ok` and `getprop ... active_border_color` became `0deg`, but the
rendered border remained DEV blue after changing the global border to
`#123456`. Thus neither that sentinel nor `unset` is used for cleanup. The
[matching upstream implementation](https://github.com/hyprwm/Hyprland/blob/efb50993780079460b0cbed1363e2166a2de1d9f/src/config/shared/actions/ConfigActions.cpp#L756)
assigns an empty gradient override; it does not remove this override.

The fallback explicitly paints the intended theme border. A second disposable
Foot probe verified Green → Trust Model → Violet → Trust Model as
`ff7ee787` → `ffd0d7de` → `ff9d6cff` → `ffd0d7de`, including captured border
pixels. The original global `ffd0d7de 0deg` was restored after the sentinel
probe and remained unchanged throughout the fallback probe. No service or
configuration was deployed by these probes.

Because fallback painting is not a native reset, the actuator retains cleanup
receipts for its previously touched windows and synchronizes those exact windows
on subsequent theme changes. The policy-free `window-identities-json` adapter
snapshot supplies current addresses and compositor stable IDs. Before repaint,
closed or reused-address receipts are pruned; writes target `stableid:` rather
than a recyclable address. At most 32 receipts (including the active accent) are
retained. If all 32 are live, new accents are declined until pruning frees a slot;
live cleanup ownership is never silently evicted. Synchronization handles one
receipt per loop and rechecks current input/correlation around blocking work.
Missing/invalid palettes suppress all repaint IPC until the selected palette's
file identity/content stamp or theme changes; backend failures back off for 60
seconds. These are neutral/appearance overrides, not extra
active trust accents. Only one window may own a trust accent. Receipts contain
no trust identity and are valid only for the recorded backend and compositor
instance; a new instance drops them without IPC. Sway cleanup exit 3 is terminal.
This synchronization requires the presentation service to be running; it also
runs when that service restarts in the same compositor instance.

**Keyboard RGB** follows `~/.config/hyperlab/rgb-mode`, set through the theme
controller (`privatestack-theme rgb-mode-toggle`, or *Keyboard lighting* in
the Control Center):

| Mode | Keyboard follows |
|---|---|
| `off` (default) | restore saved operator zones, then release RGB ownership |
| `system-trust` | the host trust claim; an unclaimed GPU is HOST |
| `focus-trust` | the resolved identity of the focused surface |

RGB is only driven while the trust-model theme is active, is written with
runtime scope through `hyperlab-nitro-control` (never persistent), keeps the
operator's current brightness, and respects the broker's rate limit. An
unresolved surface, an invalid claim or an unavailable broker holds the
current colours.

Window cleanup metadata remains in the private runtime HyperLab directory.
The session manager must already have created the user-owned `XDG_RUNTIME_DIR`;
the actuator creates only its `hyperlab` child, mode 0700. The window journal
contains schema, backend, exact compositor instance, current owned address and
bounded address-to-stable-ID cleanup receipts. Invalid journals are quarantined without using any
address from them.

RGB ownership is separate:
`$XDG_STATE_HOME/hyperlab/focus-accent/focus-accent-rgb.json` (default
`~/.local/state/hyperlab/focus-accent/focus-accent-rgb.json`). The directory is 0700 and the
atomically replaced file is 0600. The shared `hyperlab` parent may remain 0755;
its mode is not changed. A validated legacy same-boot baseline is migrated into
the private child before removing the old file; invalid legacy state still blocks
recapture. It contains only schema, the kernel boot ID,
four original operator zones and an ownership boolean. It survives logout
without linger. Same-boot restarts reuse the original baseline; a different boot
ID discards ownership without restoring old hardware state. Restores always read
current live brightness and use the Nitro broker's runtime scope.

Unsafe/malformed RGB records are renamed to the deterministic `.invalid`
quarantine entry without following symlinks. A quarantine entry keeps RGB in a
structured `rgb-degraded` hold across restarts; borders continue independently.
Unsafe directories disable writes rather than manufacturing replacement state.
Recovery is deliberate: stop the presentation service, set mode `off`, establish
known manual operator zones through the reviewed Nitro controls, then remove the
quarantined RGB entry from the private state directory and restart the service.
Do not remove quarantine merely to resume automatic lighting: current hardware
colours may still be the previous managed trust colour.

These probes prove the reset limitation and fallback rendering. Nitro physical
acceptance of the C9.4 focused-provenance interaction is also complete: rapid
HOST↔DEV focus switching updated the reviewed border/RGB presentation correctly,
and operator RGB restore passed. Logout/login remains part of broader session and
release qualification rather than an open C9.4 focus-accent defect.

## Shell visual roles

The HyperLab Shell derives every surface tone from the reviewed palette
instead of introducing colours of its own: hairlines, control fills, dim and
ghost text, the rail scrim and floating surfaces are the palette foreground
or base at fixed alphas (`Theme.qml`). A theme therefore restyles the whole
shell — rail, desktop, launcher, panel, OSD — by changing the palette alone.

Theme palette and trust palette remain separate. `provenanceColor()` is the
only path to a trust colour and it is used only by provenance indicators
(machine beacons, ladder rings, the rail badge under an explicit host claim).
Switching a theme never changes what a provenance colour means, and the
shell backdrop and lock surface carry no trust colour at all.

The theme picker and wallpaper picker are staged: the command surface
exposes `theme-cycle` and `wallpaper-mode-toggle` with the current state, and
a visual browser will follow once the registry exports one reviewed palette
summary per selectable theme.
