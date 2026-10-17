# ADR 0047 - One host key pauses every Machine and cuts its network

Status: proposed. The software is built and checked by tests and contracts;
the key itself is a proposal pending the operator (open question 22 of the
test plan), and the Nitro test below decides the rest.

## Context

When something looks wrong in a Machine (a download that should not have
started, a guest that reacts to nothing, a page that asks for what it should
not), the operator needs one gesture that stops every Machine from doing
anything more, now, without deciding first which one it is. Shutting
Machines down loses their state, and that state is often the evidence, and
the work. Disconnecting the host's own network does not stop a Machine from
reaching another Machine or the host.

The gesture must also be safe to make by mistake: undoing it must be exact
(nothing the operator had paused or disconnected before comes back on its
own) and deliberate.

## Options

**A. Link down, then pause, both reversible (recommended).**
`hyperlabctl panic engage`, as the operator against `qemu:///system`, takes
every domain that is running and, for each one, first sets every network
interface link down (`virsh domif-setlink DOMAIN MAC down`, interfaces from
`virsh domiflist`), then pauses it (`virsh suspend`). Interfaces are named by
MAC, which every interface type has; the target name can be `-`. A link the
operator had already set down is left alone and not recorded. The changes are
recorded in `$XDG_RUNTIME_DIR/hyperlab/panic.json` (0600 in a 0700
directory): when it was engaged, and per domain the links it set down and
whether it paused it. The record is written before the first change and after
every one, so a crash never loses what there is to restore. One failing domain
never stops the others; every failure is reported and makes the command exit
non-zero. Engaging again keeps the record and adds to it, so a second press
never forgets what the first one changed. The stop never waits on its
record: a record that cannot be read is left as it is and one that cannot be
written is reported, and every running Machine is still cut and paused; the
output then says Restore cannot undo that press
(`problems/emergency-stop-blocked-by-its-record.md`).

`hyperlabctl panic restore --confirm` sets up the links the record set down,
then resumes the domains the record paused, and removes the record; without
`--confirm` it refuses. A Machine the operator had paused before the stop
stays paused, and one that was shut off was never touched. A domain confirmed
shut off or crashed by restore time is skipped with a note: link changes are
live only, so it comes back with the links its definition has. A failed state
query does not prove a domain is gone: unavailable, unknown and transitional
states remain recorded, report failure and leave that domain untouched for
retry. What could not be restored stays recorded, and restoring again retries
only that.

The host key is `SUPER+SHIFT+Escape` in the Hyprland session (proposed; the
test plan also proposes `SUPER+SHIFT+Pause` if Nitro has the key). While a
record exists, the top rail shows "Emergency stop" and the workspace shows,
above every destination, "Emergency stop: Machines paused, networks cut" with
what was changed and a **Restore** action. Restore goes through the shared
confirmation with the word `restore` typed, and the machine bridge runs
`hyperlabctl panic restore --confirm` (`privatestack-machine-actions
panic-restore`). The bridge only reads the stop (`panic-status`) and restores
it; it has no way to engage it.

**B. Destroy the Machines and their networks (`virsh destroy`,
`virsh net-destroy`).** Stops everything for certain, but it is a power cut:
unsaved guest work and the guests' memory, often the evidence, are lost, and
nothing can be undone. Rejected.

**C. Take the host's own network down.** Cuts the internet, but Machines
still reach each other over the bridges and still reach the host; a guest
keeps running whatever it was running. Does not answer the question.

## Recommendation

A. It stops every running Machine in one gesture, loses nothing, and its
undo is exact and deliberate.

## What this does not cover

- A guest already compromised keeps its memory and its disk as they were: a
  paused Machine is frozen, not cleaned. Restoring resumes it as it was.
- The GPU is not reset or reclaimed: a VFIO Machine keeps its passed-through
  devices while paused. A passed-through network card (ADR 0042) has no link
  libvirt can set down; pausing is what stops it.
- The host itself is not isolated from the internet, and host processes are
  not stopped.
- Machines that are not running at engage time are not touched, including
  one the operator had paused: resuming it later by hand brings its network
  up with it. A Machine started after the press is not stopped; press again.
- The key works where Hyprland sees it: while Looking Glass holds the
  keyboard, release it first (Right CTRL). The Sway recovery session has no
  binding. The key is not active on the lock screen.
- The shell reads the record every 5 seconds, so the banner can lag the key
  by that much; the stop itself does not wait for the shell.

## Hardware test

On Nitro, with at least two Machines running and one paused by hand:

1. `SUPER+SHIFT+Escape`: within 5 seconds the rail shows "Emergency stop";
   `virsh list` shows the running Machines paused, the hand-paused one still
   paused, and `virsh domif-getlink` shows their links down.
2. From inside a paused Machine nothing answers; after the restore below,
   a ping from it to its gateway works again.
3. Press the key twice; `hyperlabctl panic status` still lists every Machine
   from the first press.
4. Restore from the workspace: the dialog needs `restore` typed; afterwards
   the paused Machines run again with their links up, the hand-paused one is
   still paused, and the rail no longer shows the stop.
5. `hyperlabctl panic restore` without `--confirm` refuses and changes
   nothing.
