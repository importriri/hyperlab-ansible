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

The compositor adapter and launchers publish the required PID information in a
later runtime-integration gate. The resolver introduced here remains read-only.

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
