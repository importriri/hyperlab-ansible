# ADR 0064 - Spheres are Machines

Status: Accepted (operator decision, 2026-11-02); the component choices below are proposed.

## Context

On 2026-11-02 the operator renamed the product Sfere (by Doppiari) and chose
the sphere as its visual language. The name has to mean something on
screen: every Machine is a sphere, and the host is the grey sphere at the
centre. Until now the shell drew a Machine as an 8-pixel provenance square
beside a word, the product symbol of
[ADR 0056](0056-product-symbol-geometry-b.md) carried no state or trust
claim, and the v3 trust pool already tinted a sphere inside each guest
wallpaper without giving it authority. Later surfaces need one rule and one
component, so that no surface invents its own drawing of a Machine.

## Decision — Accepted, operator decision

**Grey is the host, always.** The product symbol (geometry B: grey arcs,
ring, grey core) is the host. It appears on the host only: the product
glyph, the idle desktop, the host wallpaper and the lock surface. Its core
is never tinted there, with the one exception of the bar core below.

**One coloured sphere per Machine.** A Machine is drawn as a lit sphere
tinted with its domain colour from `tools/palette/palette.yml`: clean
`#72f2a5`, dev `#5b8cff`, services `#35e4dd`, dirty `#ff9d45`, lab
`#b184ff`, host `#8b949e`. If these values and the palette ever differ, the
palette wins; no drawing carries its own copy of a colour.

**The bar core is a trust indicator.** In the host bar, the core of the
product glyph takes the colour of the Machine that owns the focused window,
and grey only when the host itself has focus. The host draws it from
host-side facts, so no guest can fake it. This amends the
[visual trust contract](../visual-trust-contract.md) and the consequence of
ADR 0056 that the mark carries no trust claim: the arcs and the ring still
carry none; the bar core does. It is not built by this decision; a
separate change builds it.

**Guest wallpapers are ambience, not authority.** The v3 pool tints the
sphere inside each guest desktop; a guest draws its own wallpaper, so it
proves nothing. Authority stays with host-drawn signals: the bar core and
the window borders.

**State is shape and light, never colour alone**, and the domain is always
also written as a word next to the sphere where space allows:

| State | Drawing |
| --- | --- |
| running | lit sphere |
| shut off | dark sphere, only its rim in the domain colour |
| starting, stopping | rim with a moving arc, only while the bridge reports the transition |
| paused or suspended | dimmed sphere with a pause notch |
| disposable | dashed ring around the sphere |
| owns the GPU | the GPU token docked on its ring |
| external, unclassified | neutral outline, no fill, word `external` |

**Themes never touch the spheres.** A theme or scheme may change the host's
accents and personal wallpaper; it never changes a sphere colour, the host
grey, the bar core or a trust colour.

**Truth before motion.** A sphere changes state only when the source that
owns that state confirms it (bridge, GPU ownership, inventory), never on a
click alone.

**One component draws every sphere.**
`roles/host_desktop_common/files/quickshell/hyperlab/MachineSphere.qml`
is the one drawing of a Machine that every later surface uses. Its inputs
are `domain`, `state`, `disposable`, `gpuOwner` and `size`; it is a disc lit
from the upper left, darker to the lower right, with a thin rim of the
domain colour and a small specular highlight, and nothing beyond the
sphere's own edge (no bloom, no glow). It stays legible from 12 to 256
pixels, honours reduced motion with a static marker instead of the moving
arc, exposes an accessible name such as `dev-01, dev, running`, and takes
every colour from the palette through the shell's Theme.

## Component choices — Proposed

The operator's decision leaves these open. Each is the conservative reading
the component and its contract implement today; each can be changed in the
component and its contract alone.

- **The neutral outline is the appearance text tone, the one themed tone
  on a sphere.** It is the outline ADR 0060 proposes for unclassified
  Machines (`textPrimary`), still Proposed there. The palette publishes no
  theme-invariant neutral, and inventing one would type a colour into the
  shell. So a theme changes the outline's exact shade, between near-white
  tones; it never brings it near an identity: under every appearance the
  outline must stay at least 48 levels, in some channel, from the HOST grey
  and every domain colour, or the contract refuses. Rules out: the HOST grey
  or any domain colour for the outline, and a theme whose text tone
  approaches an identity colour.
- **The outline is solid, not dashed**, because a dashed ring means
  disposable in the sphere language. The 8-pixel provenance marker keeps
  its dashed outline until a surface replaces it with a sphere. Rules out: a
  dashed external ring.
- **External and unclassified share one drawing** and differ only in the
  word: **external** for a domain a readable registry places outside the
  product, **unclassified** for a registry Machine whose identity did not
  resolve. This amends the accepted table, whose row writes the word
  `external` for both: following [ADR 0060](0060-external-machine-visibility.md),
  which reserves **external** for domains a readable registry places outside
  the product, a registry Machine is never called external. Rules out: a
  domain colour or fill for either, and the word external for a registry
  Machine.
- **A dark sphere keeps a body, in its own darkened hue.** Shut off and
  transitioning Machines are filled, much darker than running but always
  measurably brighter than the ground, so a shut-off Machine and the empty
  external outline differ in light and shape, not only in rim colour. The
  body is the domain colour darkened, not a neutral dark: this reads the
  accepted row ("dark sphere, only its rim in the domain colour") as "only
  the rim is lit in the domain colour", so that shut-off Machines of
  different domains still differ in the body as well as the rim. A neutral
  dark body is the alternative, at the cost of that difference. Rules out: a
  shut-off Machine drawn as a bare coloured ring.
- **The HOST grey sphere is the host's own.** The component draws the grey
  sphere only when its caller sets `isHost` for the domain `host`; `host`
  without `isHost`, or `isHost` with any other domain, is a contradiction
  and draws the neutral outline with the word **unclassified**. No guest
  Machine can be drawn with the host's identity by a provenance that merely
  resolves to `host`. Rules out: a guest Machine in the HOST grey.
- **The domain arrives in canonical form.** The component accepts only the
  lower-case domain names of the palette; `Host`, `HOST` or `Dev` draw the
  neutral outline with the word **unclassified**. The shell's colour lookup
  is case-insensitive, so without this rule a capitalised `Host` would pass
  the reserved-grey comparison and still be drawn in the HOST grey. Rules
  out: folding case inside the component.
- **The state input is the component's `Item.state`.** The component
  declares no QML `States`, so only its caller changes it. Rules out: QML
  States or transitions inside the component.
- **The state words.** The component draws the table's words and the three
  libvirt words that name one of them: `shutoff` as shut off, `in shutdown`
  as stopping (libvirt reporting a shutdown in progress), `pmsuspended` as
  suspended; its accessible name says the table word. Any other word, such
  as `crashed`, `blocked` or `unknown`, fails closed to the neutral outline
  while the accessible name keeps the domain and the word (`dev-01, dev,
  crashed`). A surface that adopts the component writes the state word
  beside a Machine in such a state, because the outline alone would read as
  external. Rules out: a plausible sphere for a state nobody confirmed.
- **Transitions.** Starting runs its arc clockwise from the top, stopping
  counter-clockwise, so they differ even when still; with reduced motion the
  arc stays at its first position. The arc is the only loop a sphere has and
  runs only while a transition is reported: it is a state, not ambience.
- **Marks.** Paused and suspended are dimmed with two cuts through the top
  of the silhouette. Disposable is twelve dashes on an orbit outside the
  body; the GPU token is a small chip with two pins, docked on that orbit at
  the right in the Machine's own domain colour, so no theme reaches any part
  of a classified sphere. Disposable and GPU ownership combine with any
  state. The noise texture of the reference renders is left out, because
  it does not hold at 16 pixels.
- **Marks are promised from 32 pixels.** Domain colour, light and the pause
  cuts hold from 12 pixels; the disposable dashes and the GPU token are
  drawn at every size but are reliably told apart only from 32 pixels. At
  12 and 16 pixels they are a hint, and a surface that draws a sphere that
  small writes `disposable` and `GPU` as words beside it, as the accessible
  name already does. Rules out: a surface relying on the 16-pixel token
  alone to say who owns the GPU.
- **Fail closed and present only.** A domain outside the reviewed set or an
  incomplete `dom_*` table draws the neutral outline. The component reads
  nothing from the host, runs nothing and declares no pointer handler: it
  presents what its caller confirmed. Its inputs beyond the decision are
  `machineName` and `isHost`, plus the shell's `theme` and `tokens`; it
  also exposes `domainWord`, the word a surface writes beside it.

## Consequences

`tests/machine_sphere_contract.py` executes the real component with the
real Theme and Tokens under the Qt software rasteriser. It reads this
record's state table and refuses a row without a drawn case; it checks every
state and mark for every domain at 12, 16, 32, 64, 128 and 256 pixels: the
exact rim colours, a dark body above the ground and an empty outline, the
paused body between shut off and running, the pause cuts, the marks' floor
at 16 pixels, dashes on the orbit, the token's place, the highlight, the
neutral outline against the HOST grey and every domain colour under every
appearance, independence from every appearance palette and, for the
outline, from the domain table, motion only while a transition is reported,
the libvirt words, the reserved HOST grey in canonical case, the fail-closed
inputs, the accessible name and the absence of any colour literal or host
service in the component. Its `--contact-sheet` option writes the review sheet of all
states and domains at 16 to 128 pixels.

No surface uses the component yet; each later surface adopts it in its own
change. The bar core, the window borders and the rename of files, paths or
strings are outside this record. Software checks do not establish that the
domains are told apart at 16 pixels on a real display or that the spheres
match the reference renders: that is the operator's review of the contact
sheet, and Nitro and Predator acceptance stay open.
