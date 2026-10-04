# HyperLab Platform — the shell

One long-running Quickshell process owns every HyperLab surface on both
compositors. This document is the design and behaviour contract for those
surfaces. The security boundaries are restated at the end and are not
negotiable by any of the design decisions above them.

## What the product is

HyperLab is an enterprise virtualization and isolation platform. The
interface has one job: let an operator see and operate machines, configure
the host, and understand what the host actually knows — without ever
implying a guarantee the host has not made.

Three rules shape everything else:

1. **The idle desktop is quiet.** Wallpaper, the rail, and almost nothing
   else. Rich content appears when an operator opens something and goes away
   when they close it.
2. **No fake state.** Unknown, absent, stale, unavailable, refused and failed
   are six different words with six different meanings. Collapsing any of
   them into a value is how an interface starts lying.
3. **Presentation has no operational authority.** Shared QML never calls a
   compositor, a hypervisor, `sudo`, `pkexec`, a device node or a shell. It
   names a reviewed action; something else decides whether to perform it.

## Surfaces

```text
HyperLab Platform
  Desktop                  wallpaper + rail, per output
  Top rail                 identity · workspaces | context · clock | host state
  Workspace                one ordinary window, three destinations
    Machines               inventory, and the selected machine
    Control Center         Session · Audio and network · Input and appearance
    Diagnostics            Overview · Isolation and GPU · Inventory · Session
  Launcher                 Destinations · Machines · Commands
  System panel             quick adjustments, on the summoning output
  OSD                      transient confirmed host feedback
  Confirmation             one target-bound dialog, inside the workspace
  Lock                     hyprlock / swaylock, in the product language
```

The three destinations are **native application destinations**, not renamed
compositor workspace numbers, and they share one compositor-managed window.
It is opened deliberately, it takes keyboard focus like any other
application, the compositor places and stacks it normally, and closing it
returns to the same quiet desktop.

The idle desktop is a bottom-layer surface with an **empty input region**, so
no click is ever intercepted by something invisible.

## The top rail

At full width the rail has three bounded regions:

```text
[symbol HyperLab] [workspaces]   [focused surface] | 09:41 Thu 4 Sep |   [provenance] [GPU] [net audio battery] [settings]
```

The clock holds the display centre while both side regions still fit beside
it. Below that the rail reduces in a defined order rather than colliding:

1. the focused-surface context elides, then disappears;
2. the date disappears;
3. the wordmark collapses to the symbol;
4. workspace chips fold into a counted overflow.

Time, essential system access and any unavailable-data indication always
survive.

- **Workspace chips** show only what the compositor reported: active,
  occupied or urgent. An empty or unreadable snapshot says
  "Workspaces unavailable" — the rail never invents workspace 1. Activation
  goes through the reviewed `workspace-select` operation.
- **Context** is the compositor's own name for the focused host surface. It
  is host metadata about a host process. It is not a provenance claim and it
  is never the GPU trust tooltip wearing a different label.
- **Provenance** and **GPU** are separate fields answering separate
  questions. The provenance badge reports the focused surface's identity as
  resolved by the host (see [Focused-surface provenance](#focused-surface-provenance)):
  HOST for a host-native surface, the VM's reviewed identity for a verified
  managed transport, a warning-toned "Unresolved" for a surface that looks
  managed but has no valid host registration, and quiet text while the
  resolution is pending or unavailable. Context and provenance never merge:
  Looking Glass stays the context while DEV is the provenance. The GPU entry shows a
  current owner, a retained boot claim, or an unreadable source — and stays
  silent when ownership is known and nothing holds it, because a free GPU at
  idle is not news.

## Machines

Inventory grouped by host-resolved provenance, with a count per group and an
explicit Unclassified group last. Cards are 300–420 units wide and carry, in
order: name and operating system, provenance, state, the allocation the
machine was given (memory, vCPU, network), and its relationship to the
passthrough GPU.

The operating system comes from the Machine's checked-in image manifest
(`os_variant`), read by the host: `Arch Linux`, `Debian 13`, `Fedora 44`,
`Windows 11`. A guest cannot rename itself there, and a variant the host
does not know reads **OS unknown** instead of a guess.

Memory and vCPU are labelled **allocation**, never consumption. A value the
host did not publish says Unknown; `networks: null` (the domain could not be
read) and `networks: []` (the domain declares none) are different facts and
never share a sentence.

Large inventories switch to a virtualized list, so every machine stays
reachable. There is no two-row cap and no self-referential "view all" tile.

Selecting a card opens the machine pane. **Selection never starts anything.**

### The selected machine

The pane holds a backend identifier, not a copied snapshot, and resolves it
against every new inventory. A machine that disappears keeps its name and
becomes "No longer available" with every operation disabled.

Operations are grouped by the decision being made — **Connect**, **Power**,
**Advanced** — and availability is never guessed. The shell asks
`privatestack-machine-actions capabilities NAME`, which re-derives the answer
from the live libvirt inventory, the checked HyperLab spec, the strict
runtime SSH inventory and the reviewed action registry. A disabled control
shows the bridge's own reason: *"Looking Glass is disabled by the machine
spec"*, *"runtime SSH inventory has the wrong mode"*.

For a VFIO guest the bridge reports the console as its *emulated* display,
and the pane labels it **Recovery console**: it is real and useful for boot
and login, but the guest desktop is on its passed-through GPU — Looking Glass
or the physical output. The console stays available; it is never presented
as the guest's desktop.

The bridge reconciles the domain's own managed metadata with the spec
inventory: a managed domain whose spec is unavailable is refused, not
treated as external, and an unreadable domain is neither. Start is offered
only from shut off or crashed. The SSH preflight applies exactly the
validation `hyperlabctl open ssh` enforces.

The answer is an observation in `ShellState`, not a second model in the
transport: it is accepted only for the outstanding request serial, only if
it names the machine that was asked about, and only if every entry has the
reviewed shape. It is then used only while the inventory it was read against
is current. Console, SSH and Looking Glass each run in their own runner for
the life of the connection, so an open guest display never blocks power
operations or a connection to another machine; a connection that ends is
recorded as *closed*, not *completed*.

Destructive operations stop at the shared confirmation and require the exact
machine name. That is an interaction safeguard, not a privilege boundary: the
reviewed backend remains the enforcement layer.

## Confirmation

One reusable dialog, owned by `ShellSurfaces`, living inside the workspace.

- The record is captured whole when the dialog opens and is the record
  executed. Selecting a different machine while it is open cannot redirect
  the operation.
- Cancel is default and holds focus. Escape cancels. Opening executes
  nothing.
- It is modal: while it is open the whole workspace behind it is disabled,
  so Tab and Backtab cycle only through the name field, Cancel and the
  confirm button, and no background control answers Enter or a click. A
  replaced record starts from an empty name and Cancel; closing returns
  focus to where it was. The body scrolls inside a bounded card and the
  buttons stay in a fixed footer at any window height.
- Leaving the destination, changing subpage, closing the workspace, opening
  the launcher or system panel, locking the session (on every lock path: the
  shared lock helper notifies the shell), the target changing state or
  disappearing, or a fresh capability answer that no longer offers the
  operation all invalidate it. An identical inventory poll does not.
- Submitting spends it, so a repeated activation cannot submit twice, and the
  captured target is re-checked against the current inventory at submission.

## Control Center

Three sections, native, replacing the Rofi and GTK control routes entirely.

- **Session** — Lock and Suspend are immediate; Log out, Reboot and Power off
  go through confirmation, and the consequence text names how many machines
  are running when the host knows.
- **Audio and network** — the structured audio level with mute and ±5, and
  the observed network, temperature and battery. No toggle is drawn for
  something the reviewed bridge cannot perform.
- **Input and appearance** — keyboard layout, theme, wallpaper source and
  keyboard lighting (off · system trust · focused window, see
  [theme-system.md](theme-system.md#focus-provenance-accents-and-keyboard-rgb))
  as the reviewed cycling operations, the rail toggle, and the observed
  reduced-motion setting.

Focused-window fullscreen and opacity are shown here, and in the system
panel, as the shortcuts they are, not as buttons. A button would act on
whatever the compositor reports as focused when the queued action runs --
the Control Center itself, or a window focused after the click -- rather than
on a captured target. They stay on `SUPER + F` / `SUPER + O` until a
target-bound operation is reviewed, and the shell's action allowlist does not
contain them.

## Diagnostics

Read-only, ordered by the questions an operator asks.

- **Overview** — every reviewed source, what it last said and when, plus the
  operations this session actually reported. Dispatch is never completion.
  Start, shutdown, force-stop and reset may be presented as *completed* only
  after fresh backend inventory verifies their distinct expected terminal
  state. Reboot and power-cycle both begin and end in Running, so Running
  alone is never accepted as proof that those lifecycle transitions occurred.
- **Isolation and GPU** — current owner, boot claim, observation age, the
  four-rung handoff ladder (CLEAN 3 · DEV 2 · DIRTY 1 · LAB 0), HOST above it
  as control plane and SERVICES in its own compartment outside the ladder.
  The diagram explains policy; it performs no handoff.
- **Inventory** — whether the inventory can be trusted right now, and the
  per-provenance counts, shown only when the inventory is actually known.
- **Session** — the compositor's identity for the focused surface (with its
  PID and window), the resolved provenance with its state, source, domain and
  reason code, host telemetry, and the appearance state including whether the
  provenance colour table is complete.

## Durable machine operations

Managed start, shutdown, reboot, force stop, power cycle and reset run through
`privatestack-operation`, never through QML or a terminal:

- `launch` re-resolves the allowlisted action from the checkout, refuses a
  second non-final operation for the same machine under one lock, writes a
  private record (`$XDG_RUNTIME_DIR/hyperlab/operations/<id>.json`, 0600) and
  starts `hyperlab-operation-<id>` as a transient user unit.
- The unit runs `privatestack-operation run <id>`, which owns a private PTY as
  Ansible's controlling terminal and relays it over a 0600, same-uid socket.
- Foot runs separately in `hyperlab-view-<id>-*` as `attach <id>`, an observer.
  Closing it detaches and never signals the operation. The Machine pane's
  *Open operation window* (bridge verb `operation-view`) reattaches, replaying
  recent output, for example to answer a pending become prompt.
- Records move `requested → dispatched → running → succeeded | failed |
  interrupted`. `interrupted` means the unit itself stopped (for example
  `systemctl --user stop`) or was found inactive before reaching a result.
- Runner `succeeded` means the reviewed backend command exited successfully;
  it is not automatically proof of every lifecycle transition. The shell
  reconciles start, shutdown, force-stop and reset against a fresh distinct
  backend state. Reboot and power-cycle deliberately become `unverified` in
  presentation after execution succeeds because both start and finish in
  Running; a future typed backend transition receipt may strengthen that
  status without making QML a lifecycle authority.
- The shell polls `operations` every 2 s. A shell restart rehydrates from the
  records, and a record-less active unit refuses new lifecycle requests.

The historical independent review for this design is recorded in
[`c9-independent-review-2026-09-27.md`](c9-independent-review-2026-09-27.md).

## Focused-surface provenance

`ShellState` turns every focus snapshot from the compositor adapter into one
numbered request to `privatestack-surface-provenance stream`, a read-only
bridge to the reviewed resolver (`tools/surface_provenance.py`) in the
HyperLab checkout. The request carries the PID, app id and window id; the
window title never leaves the adapter.

- Only the answer to the latest request is accepted. A different surface
  drops the previous identity immediately, so a guest identity never stays
  attached to the window that replaced it. Even an identical PID/window
  tuple clears its answer until revalidated, to avoid cached PID reuse.
- Every answer is shape-checked before presentation: a guest identity must
  agree with its `network_profile`, come from `host-owned-vm-spec`, name a
  domain and answer for the focused PID; a reason outside the resolver's
  vocabulary invalidates the answer.
- The resolver re-reads the per-user registry for every request. An
  untrusted registry, a resolver error, an unanswered request (3 seconds)
  or a stopped resolver is *unavailable*; none of them becomes HOST. The
  watchdog kills only its owned resolver process; focus churn cannot extend
  the deadline. The resolver restarts after 2 seconds with a new request for
  the current surface. Completed or cancelled requests cannot answer again.
- Provenance is re-resolved on every focus event and on the adapter's
  30-second heartbeat, which bounds how long specification drift or a
  vanished process can go unnoticed on a surface that keeps focus.


### Narrow Nitro deployment and physical acceptance — PASS

The focused-surface provenance path is now physically accepted on Nitro in
addition to its source and contract verification.

The accepted runtime evidence covers the security-relevant boundaries rather
than trusting application labels:

- a reviewed managed Looking Glass surface for `arch-dev-vfio` resolves to
  `DEV` from the host-owned VM specification;
- the reviewed managed SSH surface resolves to `DEV`;
- an ordinary unregistered Foot terminal resolves as `HOST`;
- a Foot window spoofing the managed SSH application id and title but lacking
  the reviewed registration fails closed as `Unresolved`;
- rapid switching between host-native and managed guest surfaces does not
  retain stale guest provenance;
- guest titles and application ids alone do not establish trust.

The managed SSH route is registered as surface kind `ssh`, with `/usr/bin/foot`
as its reviewed executable. `ShellState` accepts `ssh` only as one of the
reviewed managed-surface kinds and still requires a valid resolver answer
correlated to the focused PID/window request.

The spoof test is especially important: a window using
`hyperlab-managed-ssh` and an SSH-looking title without a matching reviewed
registration produced `managed-surface-not-registered`, no guest trust, and
the shell presented `Unresolved`. This preserves the fail-closed boundary.

The Nitro deployment was intentionally narrow. The provenance bridge and
shared shell source were deployed without changing VM trust, GPU ownership,
network policy or guest metadata authority. Provenance remains host-owned and
is re-resolved on focus changes.

Classification:

`C9_C_MANAGED_SURFACE_PROVENANCE=PHYSICAL_PASS`

The deterministic coverage in
`tests/surface_provenance_live_binding_contract.py` and
`tests/managed_ssh_surface_provenance_contract.py` remains the regression
boundary for this behavior.

## Launcher

Results are grouped **Destinations**, **Machines**, **Commands**. An empty
query favours navigation and reviewed commands; machines appear once an
operator asks for them, so opening the palette never lists two hundred rows
before the three destinations.

Dispatch is per kind: a destination goes to `ShellSurfaces`, a machine
selects an identifier, and only a reviewed command identifier reaches the
action bridge. Aliases such as "workstation controls" resolve to the
destination they mean instead of producing duplicate rows. The query never
becomes executable text.

Launching arbitrary desktop entries stays outside the typed bridge. Rofi
keeps that one job on `SUPER + D` as a transitional application launcher with
no HyperLab route; finishing it needs a reviewed desktop-entry catalogue that
returns stable application IDs.

## Design system

`Tokens.qml` owns geometry, type and motion. `Theme.qml` owns colour. No file
between them invents a margin, a radius or a hue.

- **Spacing** 4 / 8 / 12 / 16 / 20 / 24 / 32 / 48.
- **Radius** card 6, control 8, window 10, surface 12.
- **Type** Adwaita Sans for names, navigation and prose; JetBrains Mono for
  identifiers, values and shortcuts. 12 / 13 / 14 / 16 / 18 / 20 / 24.
  Nothing essential renders below 13.
- **Motion** hover 100, workspace 140, entry 160, exit 120, expand 180 ms,
  OutCubic. Reduced motion is a real host setting read from
  `~/.config/hyperlab/reduced-motion`, and every duration collapses to zero
  when it is on. There are no ambient loops and no animation that implies
  progress.
- **Breakpoints** are capacities, not monitor models: ≥1600 full, 1100–1599
  compact navigation, 760–1099 one region at a time, <760 single column.

Activation lives in three primitives — `ShellControl`, `PanelRow` and
`ShellCard`. Each takes keyboard focus, activates on Return or Space, refuses
activation while disabled or busy, carries an accessible name and explains
why it is unavailable. A raw pointer handler anywhere else is a named
exception in the interactive-controls contract.

### Colour

Three systems meet in `Theme.qml` and stay separate.

| System | Where it may appear |
| --- | --- |
| Appearance | every surface, boundary, fill and text tone |
| Provenance | labelled provenance markers, provenance group headers, the explicit trust diagram |
| Status | operational warning and error, as text and shape |

Provenance colours are fixed identity, immutable across every appearance, and
published by the theme registry as `dom_*`:

| Identity | Colour | Role |
| --- | --- | --- |
| HOST | `#8b949e` | control plane, above the ladder, never a rung |
| CLEAN | `#72f2a5` | rung 3 |
| DEV | `#5b8cff` | rung 2 |
| SERVICES | `#35e4dd` | outside the GPU handoff entirely |
| DIRTY | `#ff9d45` | rung 1 |
| LAB | `#b184ff` | rung 0 |

Selection, focus, ordinary controls, successful operations and generic
readouts stay neutral. Focus is one shared neutral ring everywhere, because
focus is not a security claim. An identity outside the reviewed set, or an
incomplete colour table, resolves to neutral text — never to a borrowed
colour.

### Identity

One geometry family: a split circular isolation boundary containing a core.
`IsolationGlyph.qml` draws it at 18 units in the rail, 24 on the idle
desktop, and `tools/wallpaper/render_isolation_ring.py` renders it as
architectural relief at wallpaper scale. "HyperLab" is the wordmark and
"Platform" the subtitle; neither is a trust claim. There is no second logo.

## Security boundaries

These do not change for any visual reason.

- Host modifier `SUPER`; managed guest modifier `ALT`; Looking Glass escape
  `KEY_RIGHTCTRL`. `F11`, `Ctrl+F` and `Ctrl+Alt+F11` are never guest
  fullscreen routes.
- Shared QML never executes `hyprctl`, `swaymsg`, `virsh`, `sudo`, `pkexec`,
  an arbitrary shell, hardware or sysfs controls, or hypervisor internals.
- No command is concatenated from presentation data. Two shapes cross the
  host action boundary: a fixed identifier resolved to an immutable argument
  vector the bridge owns, and one reviewed parameterised operation
  (`workspace-select`) whose only argument is an integer slot validated on
  both sides.
- `ShellState` is the only file that reads host runtime data. `ShellSurfaces`
  owns where the product is, never what the host is.
- The lock screen shows no machine name, no guest content and no provenance,
  and its background is a dedicated static asset — never a blurred screenshot
  and never a rotated theme wallpaper.
- Native confirmation is an interaction safeguard. A same-session caller can
  reach the user action bridge without it, so the reviewed backend remains
  the privilege boundary.

## Related documents

- [`desktop.md`](desktop.md) — the compositor sessions and their bindings.
- [`theme-system.md`](theme-system.md) — the theme registry and provenance.
- [`wallpaper-art-direction.md`](wallpaper-art-direction.md) — the identity
  asset family.
- [`keybinding-security.md`](keybinding-security.md) — the input ownership
  boundary.
