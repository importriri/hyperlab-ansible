# ADR 0032 - Clipboard out of a guest: to the host and to another guest

Status: proposed. The operator chooses before any of it is built; today
only host to guest exists ([ADR 0020](0020-host-to-guest-clipboard.md)).

## Context

ADR 0020 moves text from the host into one named Machine. The other
directions bring text the guest chose to somewhere it did not live:

- **guest → host** puts guest-controlled text in the host clipboard. Pasted
  into a host terminal, a line with control characters or an escape
  sequence can do more than it shows. The host is the control plane, above
  every network class, so this always moves data up.
- **guest → guest** relays text between two Machines. When the target's
  network class is higher than the source's (dirty → dev, lab → clean), data
  moves up the ladder of trust.

The platform rule stays: data crosses only through an explicit, one-shot,
host-mediated action aimed at one named target, and the host decides.

## Options

**A. A host pull, then the existing send (recommended).** A fixed guest
program, `hyperlab-clipboard-offer`, prints the guest clipboard once as
text; `hyperlabctl clipboard take MACHINE` runs it over the same reviewed SSH
argv as ADR 0020, with the same limits (UTF-8, at most 1 MiB, never in an
argument vector or a log). The text is then either put in the host
clipboard or sent on to a second Machine with the existing send.
- Guest → host always asks for confirmation in a host surface that shows the
  source Machine with its provenance, the length, and whether the text holds
  control characters; control characters other than newline and tab are
  refused outright.
- Guest → guest asks for confirmation when the target ranks above the
  source on the network ladder, or when either is on `services` (no rung).
- Each crossing is logged on the host with time, source, target, byte count
  and the text's sha256, never the text.
- Keys: `SUPER + SHIFT + C` takes from a Machine chosen in the launcher;
  the taken text is held by the host for one send or one paste, then
  dropped.

**B. Guest → guest only.** The host relays between Machines but guest text
never enters the host clipboard. Removes the host-terminal risk; leaves no
way to copy an error message out of a guest.

**C. A shared clipboard per network class.** Rejected: a continuous channel
is what ADR 0020 removed.

## Recommendation

A, with control characters refused rather than escaped: a refused paste is
visible, an escaped one can still surprise. B is the fallback if guest text
must never reach the host clipboard at all.
