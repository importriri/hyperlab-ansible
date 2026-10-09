# The Linux sender stayed "streaming" while no frame reached the client

Author: [importriri](https://github.com/importriri).

Status: corrected in the reviewed sender patch and covered by
`tests/looking_glass_frame_stall_contract.py`; not yet proven on Nitro.

## Symptom

Looking Glass was left open on `dev-01` for about a day. The operator found
the client frozen on a frame showing 20:15 on 2026-10-04, while the guest stayed healthy: Hyprland
running, the guest agent answering, no NVIDIA error in the kernel log.

## What was observed

Read on `dev-01` without privilege on 2026-10-05:

- `kvmfr0` was mapped at 19:35:22 (kernel log), so the sender started then;
  its log's times are elapsed time since that start, not clock times. A
  client subscribed at 19:51:14 (`+00:15:51`): a new portal session,
  `Capture Start`, the stream went `paused -> streaming`. That is the last
  line; the log file was last written at 19:51:14.
- No `Capture Stop` follows, so for the sender a client was still
  subscribed. Nothing else in the user, system or kernel journal between
  20:10 and 20:30 concerns the portal, PipeWire, Hyprland or the GPU.
- `xdg-desktop-portal-hyprland` (`xdph`) has run since 19:28:01 on 4 October,
  and its journal stops in the middle of the 19:51:14 session, before lines
  that certainly happened: its output is buffered, so its log cannot date
  anything after that.
- The sender ran until 20:50:37 on 5 October, when a recovery command
  stopped it. The same command meant to restart the portals, but did not:
  `pkill -f looking-glass-host` also matched the shell running the command,
  whose own command line contains that text, and ended it first.

## Cause found in the code

Two properties of the pinned sender (Looking Glass `0140a3f`) make this
failure silent, and one of them can cause it:

1. The PipeWire process callback dequeues every ready buffer and keeps the
   newest. When that buffer's chunk is empty it returns **without queueing
   the buffer back**. Each empty buffer is lost to the stream; when the pool
   is gone the producer cannot deliver anything, the process callback stops
   being called (so even "out of buffers" is never logged), and the stream
   stays `streaming`.
2. The capture waits one second per frame, and a timeout is treated as
   normal and not logged. A subscribed client then gets the last valid frame
   again, which is what a frozen image looks like.

Run against a fake stream with four buffers and one empty frame in ten, the
unpatched callback stops the producer at frame 40 after 36 frames delivered.

Not shown: that `xdph` sent empty buffers that evening. The sender's log
had no counter that could say so; the watchdog below adds one.

## Fix

In `pipewire-thread-loop-runtime.patch`:

- an empty buffer is queued back to the stream and counted;
- a frame watchdog logs `No usable frame for N s while streaming` once after
  10 s, with the process callbacks and empty buffers seen since the last
  usable frame (none means the producer stopped; some means it sent empty
  buffers), and after 30 s logs the same and returns
  `CAPTURE_RESULT_REINIT`. The sender was meant to stop the capture and,
  while the client is still subscribed, start it again with a new portal
  session. That restart was never seen working: on 2026-10-07 the first
  real one logged "Capture Stop" and hung for good
  ([`looking-glass-sender-hung-after-capture-stop.md`](looking-glass-sender-hung-after-capture-stop.md)).
  The watchdog runs only while the capture runs, which is only while a
  client is subscribed.
- Since 2026-10-09 the watchdog only logs: silence is not a failure (on
  dev-01 fifteen pauses of 10 to 26 s with no process callback ended by
  themselves), and `hyperlabctl looking-glass health` reports it as "no new
  frame for N s". The capture restarts only when the stream reports ERROR,
  loses its node (UNCONNECTED) or the core reports an error.

The patch applies on the pinned source together with the GCC compatibility
patch, and the patched sender builds (checked on Nitro's host with the same
`cmake` options as the role).

## Regression proof

`tests/looking_glass_frame_stall_contract.py` rebuilds the process callback
before and after the patch from the patch's own hunk and runs both against
the fake stream: before, the producer runs out of buffers; after, all 1000
frames are produced and the 900 usable ones delivered. It also runs the
watchdog policy (warn at 10 s, once; a frame resets it; silence never
restarts the capture) and checks the capture timeout uses it.
`tests/looking_glass_sender_capture_contract.py` runs the patched capture
on the real PipeWire thread loop: 61 s of silence give timeouts only, and a
stream error, a lost node or a core error each restart the capture.

## Still to prove on Nitro

- The rebuilt sender streams for hours without freezing.
- A desktop left still logs `No usable frame` once and keeps the same
  sender and capture; the health says "no new frame for N s", not an alarm.
  On dev-01 the 30 s restart did fire on such a pause; whether `xdph` sends
  nothing while nothing changes is the operator's screen-change test.

Related: [`looking-glass-splash-after-guest-reload.md`](looking-glass-splash-after-guest-reload.md),
a different symptom (the splash screen after `hyprctl reload`) whose cause
is still open.
