# ADR 0045 - Looking Glass stream health and a capture restart from the shell

Status: proposed. The software is built and checked by contracts; the
Nitro test below decides it.

## Context

A Linux Machine's Looking Glass stream froze for a day while the guest was
healthy, and nothing on the host said so
([`../../problems/looking-glass-sender-streaming-without-frames.md`](../../problems/looking-glass-sender-streaming-without-frames.md)).
The fix to the sender stops the known cause and makes a stall visible in
the sender's log: `No usable frame for N s`, `Frames resumed`, and a capture
restart after 30 s. What was missing is the operator's view: is the stream
alive, is the guest alive, and a way to restart the capture that does not
restart the Machine. The recovery done by hand on 2026-10-05 also failed:
an unanchored `pkill -f looking-glass-host` ended its own shell.

## Options

**A. Ask the guest's sender, on demand, from the shell (recommended).**
`hyperlabctl looking-glass health NAME` reports three facts, each from its
own authority: the guest agent's answer to `guest-ping` (from the host, as
the user, through libvirt), whether the sender process runs, and the stream
state the sender last logged, read over the pinned SSH channel. It reduces
them to one word: `ok`, `stalled`, `sender-down`, `idle` (no client),
`starting`, `guest-unresponsive` or `unknown`. `hyperlabctl looking-glass
restart-capture NAME` stops the sender by its anchored path, restarts the
guest's screen-cast portals and starts the sender through the same path as
`open looking-glass`; the host client reconnects by itself. The typed
bridge offers `restart-capture` only for a running managed Linux Looking
Glass guest, and `stream-health` only where it offers the restart. The
Machine pane shows a Stream section there: the health, checked when the
restart becomes available and every 15 s while the pane is shown, and the
action.

**B. Measure frames on the host.** The host client sees frames arrive, but
it has no interface HyperLab can read, and reading the shared memory's
frame queue would bind the shell to Looking Glass internals.

**C. Restart the sender on a timer in the guest.** Recovers without the
operator, but hides the failure, and the sender's own watchdog already
restarts a stalled capture.

## Recommendation

A. The sender recovers by itself; the shell names what happened and gives
one action when it did not.

## What this does not cover

- A stall in the old sender: it logged nothing when frames stopped, so its
  stream reads as streaming. The rebuilt sender is required.
- Windows guests: their sender is another program; the action is refused.
- A frozen host client while the guest's stream is healthy.
- Restarting the Machine, its GPU, or Hyprland in the guest.
- The overview's Machine cards: the state is shown in the selected
  Machine's pane, not on every card.

## Amendment (2026-10-09): silence is information, not a failure

On dev-01 the sender's 30 s restart fired on a pause that, like fifteen
before it, carried no process callback at all, and the restart hung for 28
hours ([`../../problems/looking-glass-sender-hung-after-capture-stop.md`](../../problems/looking-glass-sender-hung-after-capture-stop.md)).
A still desktop probably sends no frame, so silence cannot tell a healthy stream
from a stuck one, and restarting on it put every still desktop through
the riskiest path. Decided by the operator:

- the sender restarts its capture only when the stream reports ERROR,
  loses its node (UNCONNECTED), or the core reports an error;
- silence stays visible as information: the sender still logs once after
  10 s, and `health` adds `no_frame_seconds`, measured on the guest's clock
  from that log line and the sender's start; the pane shows "Streaming, no
  new frame for N s", never an alarm, and the verdict stays `ok`;
- `stalled` now names only a restart that did not end with a new capture.

Option C's remark that the watchdog restarts a stalled capture no longer
holds; the operator's "Restart capture" is the recovery for a stream that
is silent and should not be.

## Hardware test

On Nitro, with the rebuilt sender (the operator's test plan has the
commands):

1. `hyperlabctl looking-glass health dev-01` with the client open reports
   `ok`, agent `yes`; with the client closed, `idle`.
2. The Machine pane shows the Stream section for `dev-01` and not for a
   server Machine.
3. With the client open, `restart-capture` from the pane: the picture
   comes back within seconds, the guest's uptime is unchanged, and the
   sender log shows a new `Capture Start`.
4. The sender stopped by hand: the pane shows `Sender stopped` within 15 s;
   the action brings it back.
5. With the guest agent stopped in the guest: `Guest not answering`, and
   the action is refused.
6. A still desktop for two minutes with the client open: the same sender
   pid, no capture restart, and the pane shows "Streaming" with "no new
   frame for N s", not an alarm.
