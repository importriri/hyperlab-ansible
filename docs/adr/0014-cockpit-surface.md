# ADR 0014: The cockpit is a renderer, and privilege is data

Status: accepted

## Context

ADR 0004 put `hyperlabctl` in `tools/`, on the standard library plus PyYAML,
speaking to libvirt through `virsh`, with `--json` in the core rather than as an
extra. It did not say what may sit on top of it.

Three surfaces now do: a waybar module, a rofi palette and a full screen panel.
They run in the desktop session installed by the normal `lab.yml` laptop
target, while the CLI must keep working on the headless `foundation.yml`
target when no session exists.

Two things make this dangerous rather than merely fiddly. The session has no
password to give, so anything on it that needs `become` is a trap. And a
surface that reimplements a decision - which domains may start, how much RAM is
assignable - is a second copy of a rule that already exists.

## Decision

**One document, three renderers.** `status --json` is the only thing the
surfaces read. The bar reduces it to one pill, the palette reads the action
registry, the panel draws it. A surface holds no rule of its own.

**Privilege is a field, not a convention.** Every action declares `privileged`
and `destructive`. The palette never executes a privileged action: it opens a
terminal with the command prepared. Direct `start`/`stop` remain available only
for unmanaged libvirt domains. A domain carrying M3's Hyperlab metadata must be
operated through its checked-in spec and lifecycle playbook, so the cockpit
cannot bypass the transaction state, sealed-base verification, locks or exact
confirmation variables.

**Availability and target resolution are fields too.** An action declares the
playbook it `requires` and its target kind. An action whose playbook is not in
this checkout is not offered. Spec and manifest targets must be real,
non-symlinked files below their repository directories. The registry resolves
one selected action to an argv list; shell surfaces receive only the
shell-quoted rendering of that validated argv and never interpolate a domain
name themselves.

**The collapsed pill streams, the drawer polls.** `hyperlabctl watch` blocks on
`virsh event` and prints when something happens. Machine-parsed subprocesses
run under the C locale; the process timeout is longer than the heartbeat, and
a non-timeout libvirt error terminates the stream rather than becoming a busy
loop. The three pills behind the drawer, visible only while the pointer is over
the group, poll slowly and take `SIGRTMIN+8` after anything the CLI itself
caused. The signal number is asserted across both halves, because drift there
is invisible at runtime: the bar simply stops updating and nothing errors.

**Failure degrades, it never blanks.** A provider that fails takes its own
section to null and puts the reason in `problems`. The bar helper prints a
valid payload even when the CLI is absent, because a waybar module that exits
non-zero disappears from the bar.

**The dependency runs one way.** The panel and the bar know `hyperlabctl`;
`hyperlabctl` does not know they exist. The surfaces live in `roles/desktop`,
which `lab.yml` mounts before `looking_glass`; `foundation.yml` deliberately
mounts neither. The desktop role verifies the configured checkout before
package writes and generates completion as the administrator, not by executing
a mutable user checkout as root.

## Consequences

The cockpit grows by adding files: a section is a file in `providers/`, a
subcommand is a file in `commands/`, a tab is a class in `panel/views.py`, and a
provider dropped in `~/.config/hyperlabctl/providers` is picked up by all three
surfaces without a line changing anywhere.

`tests/hyperlabctl_contract.py` holds the claims that span the two halves and
runs the component suite, so CI gates the CLI through discovery rather than
through an edit to the workflow.

A GUI panel was rejected: `gtk4-layer-shell` and `python-gobject` would put a
toolkit on a host whose contract is TTY-first, and eww is AUR-only. The panel
is curses, which is standard library.
