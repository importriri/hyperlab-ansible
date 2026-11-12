# ADR 0064 - Spheres are Machines

Status: Accepted (operator decision, 2026-11-02).

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

## Decision

**Grey is the host, always.** The product symbol (geometry B: grey arcs,
ring, grey core) is the host. It appears on the host only: the product
glyph, the idle desktop, the host wallpaper and the lock surface. Its core
is never tinted there, with the one exception of the bar core below.

**One coloured sphere per Machine.** A Machine is drawn as a lit sphere
tinted with its domain colour from `tools/palette/palette.yml`, published to
the shell as the `dom_*` keys and reached only through
`Theme.provenanceColor()`: clean `#72f2a5`, dev `#5b8cff`, services
`#35e4dd`, dirty `#ff9d45`, lab `#b184ff`, host `#8b949e`. If these values
and the palette ever differ, the palette wins; no drawing carries its own
copy of a colour.

**The bar core is a trust indicator.** In the host bar, the core of the
product glyph takes the colour of the Machine that owns the focused window,
and grey only when the host itself has focus. The host draws it from
host-side facts (the reviewed surface provenance resolver), so no guest can
fake it. This amends the [visual trust contract](../visual-trust-contract.md)
and the consequence of ADR 0056 that the mark carries no trust claim: the
arcs and the ring still carry none; the bar core does. It is not built by
this decision; a separate change builds it.

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

Disposable and GPU ownership are independent marks: they combine with any
state. The external and unclassified outline is the one ADR 0060 proposes
for unclassified Machines: the appearance text tone, never a domain colour
or the HOST grey, with the word **external** for a domain outside a readable
registry and **unclassified** for a registry Machine without a resolved
identity. Inside a sphere that outline is solid, because a dashed ring means
disposable; the 8-pixel provenance marker keeps its dashed outline until a
surface replaces it with a sphere.

**Themes never touch the spheres.** A theme or scheme may change the host's
accents and personal wallpaper; it never changes a sphere colour, the host
grey, the bar core or a trust colour. The only themed tone on a sphere is
the neutral outline, which is appearance text by definition.

**Truth before motion.** A sphere changes state only when the source that
owns that state confirms it (bridge, GPU ownership, inventory), never on a
click alone. The transition arc is the only loop a sphere has, and it runs
only while a transition is reported; it is a state, not ambience. With
reduced motion the arc stays still at its first position.

## The component

`roles/host_desktop_common/files/quickshell/hyperlab/MachineSphere.qml`
is the one drawing of a Machine that every later surface uses. Its inputs
are `domain`, `state` (the words of the table; the component's `Item.state`,
with no QML States declared), `disposable`, `gpuOwner`, `size` and
`machineName`, plus the shell's `theme` and `tokens`.

- A disc lit from the upper left, darker to the lower right, a thin rim in
  the domain colour and a small specular highlight. Nothing is drawn beyond
  the sphere's own envelope: no bloom, no glow, no shadow. The noise
  texture of the reference renders is left out, because it does not hold
  at 16 pixels.
- Shut off and transitioning Machines are dark bodies with a lit rim;
  paused and suspended Machines are dimmed with two cuts through the top of
  the silhouette. Starting runs its arc clockwise from the top, stopping
  counter-clockwise, so they differ even when still.
- Colour comes only from `Theme.provenanceColor()`, derived shades of it and
  the appearance text tone. A domain outside the reviewed set, an incomplete
  `dom_*` table or a state outside the vocabulary draws the neutral outline
  without fill, never a plausible sphere (fail closed).
- The component reads nothing from the host, runs nothing and declares no
  pointer handler: it presents what its caller confirmed.
- It exposes an accessible name such as `dev-01, dev, running`, extended
  with `disposable` and `owns the GPU`, and the word a surface writes beside
  it as `domainWord`.

## Consequences

`tests/machine_sphere_contract.py` executes the real component with the
real Theme and Tokens under the Qt software rasteriser. It reads this
record's state table and refuses a row without a drawn case; it checks every
state and mark for every domain at 12, 16, 32, 64, 128 and 256 pixels, the
exact rim colours, the neutral outline against the HOST grey and every
domain colour, independence from every appearance palette and from the
domain table for the outline, motion only while a transition is reported,
the fail-closed inputs, the accessible name and the absence of any colour
literal or host service in the component. Its `--contact-sheet` option
writes the review sheet of all states and domains at 16 to 128 pixels.

No surface uses the component yet; each later surface adopts it in its own
change. The bar core, the window borders and the rename of files, paths or
strings are outside this record. Software checks do not establish that the
domains are told apart at 16 pixels on a real display or that the spheres
match the reference renders: that is the operator's review of the contact
sheet, and Nitro and Predator acceptance stay open.
