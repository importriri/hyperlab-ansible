# The Linux sender hung for good after "Capture Stop"

Author: [importriri](https://github.com/importriri).

Status: one of the three possible hangs corrected in the reviewed sender
patch and covered by `tests/looking_glass_sender_teardown_contract.py`; not
yet proven on Nitro.

## Symptom

On `dev-01` the Looking Glass client showed "Capture Disabled" from
14:20 on 2026-10-07 until 18:07 on 2026-10-08, when the operator ran
"Restart capture" (exit 0). The sender (pid 390233, the build installed by
group 16 the same day) was alive and sleeping (`S`) the whole time.

## What was observed

Its log was copied read-only to the evidence
(`lg-freeze-20261007.log`, sha256
`914b69187dec608444bb7f58cd2d59115f837c8c898e422be7f00d1703bdf350`):

- 15 warnings "No usable frame for 10 s while streaming: 0 process
  callbacks, 0 empty buffers", each followed by "Frames resumed" after 10
  to 26 s;
- at `+00:18:01` (14:20:18, guest clock) a pause reached 30 s: "No usable
  frame for 30 s: restarting the capture", then `app.c:461 Capture Stop`;
- nothing after that for 28 hours: no "Got session handle", which a new
  capture logs first, and no error.

"Capture Disabled" is the client's own alert that it released the input
grab (`client/src/main.c` `lgInit`, `client/src/core.c`); it is not a
message from the sender.

## Cause found in the code

`app.c` logs "Capture Stop" *before* it calls the capture's `deinit`, and a
new capture logs "Got session handle" early. The sender therefore stopped
between the two, in a wait with no deadline and no log. The code has three
such waits; the log cannot tell which one it was, and the restart ended the
process without recording its threads:

1. **The runtime patch's teardown (corrected here).** A PipeWire callback
   that hands over a frame or a format calls
   `pw_thread_loop_signal(loop, true)`, which waits until the capture calls
   `pw_thread_loop_accept`. A restart stops the capture without reading that
   frame: neither the restart path nor `pipewire_stop` accepted it.
   `pipewire_deinit` then calls `pw_thread_loop_stop`, which joins the
   PipeWire thread, still waiting: a deadlock. The callback can be waiting
   because a frame arrived between the capture's last timeout and
   `pipewire_stop`, or long before: a frame that arrives while the capture
   is not waiting finds no waiter, and its callback waits from then on
   ([`looking-glass-sender-frame-handed-over-to-nobody.md`](looking-glass-sender-frame-handed-over-to-nobody.md)). A format that arrives after `pipewire_stop`,
   before the thread stops, would wait the same way.
2. **The portal's waits** (`portal.c`): after each portal request the
   sender waits for the portal's Response with no deadline. A portal that
   never answers holds it for good.
3. **No client subscribed**: the sender idles until one subscribes. This is
   expected, and silent.

The restart itself was triggered by 30 s without a frame
([`looking-glass-sender-streaming-without-frames.md`](looking-glass-sender-streaming-without-frames.md)).
The 15 earlier pauses ended by themselves, which fits a still desktop.
The last one does not tell: "0 process callbacks" is also what a callback
stuck waiting for an accept looks like.

## Fix

In `pipewire-thread-loop-runtime.patch`, every handover and every accept
goes through one handshake that records whether a callback is waiting.
`pipewire_stop`, and `pipewire_deinit` before it joins the PipeWire thread,
release a callback that is still waiting; the callback then sees the stop
and returns. After the stop a callback never waits.

The patch now carries the whole of `pipewire.c` in one hunk, so the
contracts can rebuild the patched file. The patched sender builds with the
role's `cmake` options (checked on Nitro's host, no warnings).

## Regression proof

`tests/looking_glass_sender_teardown_contract.py` compiles the patched
`pipewire.c` against the real PipeWire thread loop (`libpipewire-0.3`),
with the Looking Glass framework, the portal and the stream's buffers
replaced by fakes:

- teardown: a usable frame arrives while the capture restarts, then the
  sender's own order runs (stop, "Capture Stop", deinit). Before the fix it
  prints `deinit blocked after Capture Stop`; after it, the teardown
  finishes;
- late format: a format arrives after the stop. Before the fix its callback
  waits for an accept (`a format after the stop waited for an accept`);
  after it, it returns;
- flow: three frames in a row still reach the capture, and every buffer
  goes back to the stream.

## Still to prove on Nitro

- Group 16 with the rebuilt sender: no hang after a capture restart.
- Which wait held pid 390233 is not known.

## Not corrected here (already in the pinned sender, not seen to fail)

- `sendFrame` in `app.c` can return while it still holds the loop lock
  (shutdown with a full queue, a failed `lgmpHostQueuePost`); `deinit`
  would then join the PipeWire thread with the lock held.
- A spurious wake-up of the capture's wait reads a frame no callback handed
  over, and its accept leaves the handshake's counter below zero.
- `pipewire_init` waits for the first format with no deadline.
