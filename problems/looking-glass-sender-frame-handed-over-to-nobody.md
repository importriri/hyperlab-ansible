# A frame handed over between two captures froze the sender's stream

Author: [importriri](https://github.com/importriri).

Status: corrected in the reviewed sender patch and covered by
`tests/looking_glass_sender_teardown_contract.py`; not yet proven on Nitro.

## Symptom

Found in review of the fix for
[`looking-glass-sender-hung-after-capture-stop.md`](looking-glass-sender-hung-after-capture-stop.md),
and reproduced on the real PipeWire thread loop; not seen on a guest.

## Cause found in the code

The capture holds the thread loop lock except while it waits for a frame
(`pw_thread_loop_timed_wait`, one second) and between two captures, after
`getFrame` unlocks. A frame callback that runs between two captures
broadcasts to nobody, then waits in `pw_thread_loop_signal(loop, true)` for
an accept. The next capture waits for a signal that already went by: it
times out every second, `getFrame` never runs, nothing accepts, and the
PipeWire thread delivers nothing more. The sender's log then shows "No
usable frame ... 0 process callbacks", the same as a still desktop.

Until now only the watchdog's restart after 30 s ended such a freeze; before
the teardown fix it could hang in the teardown instead (the note above).
Without a restart on silence the freeze would last.

## Fix

In `pipewire-thread-loop-runtime.patch`, the capture does not wait when the
handshake records a callback already waiting: it takes that frame at once.

## Regression proof

`tests/looking_glass_sender_teardown_contract.py`, scenario "missed
wake-up": two frames are each handed over while the capture is not
waiting. Before the fix the capture returns `a timeout` for the first;
after it, both are taken and their buffers go back to the stream.

## Still to prove on Nitro

- Group 16 with the rebuilt sender: the stream does not freeze while the
  screen changes.
