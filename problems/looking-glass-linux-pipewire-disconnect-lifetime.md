# Looking Glass Linux PipeWire disconnect lifetime

## Symptom

The experimental Linux Looking Glass sender could survive normal capture and
fullscreen GPU workloads, but closing the physical-host Looking Glass client
could terminate the guest sender with `SIGSEGV`.

The failure was reproduced independently of the standalone SPICE recovery
console. The guest compositor remained healthy, `HEADLESS-0` stayed available
at the reviewed 1920x1080 at 144 Hz mode and the failure occurred during the
capture teardown boundary after the client disappeared.

This is a separate failure from the earlier PipeWire frame-lifetime problem
documented in
[`looking-glass-linux-pipewire-frame-lifetime.md`](looking-glass-linux-pipewire-frame-lifetime.md).
That earlier issue involved a frame being copied while its backing PipeWire
storage could change. The disconnect failure instead affected stream and
PipeWire object lifetime during teardown.

## Failure boundary

The reproduced disconnect crash used the pinned Looking Glass source commit
`0140a3f6fb616c5636d6c430eb71b8a7d5338e39`.

The failing production sender reached the normal transition from streaming to
paused/unconnected capture state, then crashed while the PipeWire stream was
being torn down. The captured backtrace included
`pw_stream_queue_buffer+0x29`.

The controlled failure had:

- a healthy Hyprland session;
- `HEADLESS-0` at 1920x1080 at 144 Hz;
- no framebuffer-write crash at this boundary;
- no requirement for a standalone SPICE viewer to trigger the problem;
- a sender `SIGSEGV` immediately associated with the client-disconnect
  lifecycle.

A first narrow callback/queue guard changed the fault location but did not
eliminate the crash, so it was rejected.

## Root cause

The capture stream could still be observed by PipeWire callbacks while the
capture thread and PipeWire objects were moving through stop and destruction.

The safe lifetime boundary therefore cannot be expressed as only a queue-buffer
guard. Stop state, stream visibility, the PipeWire thread loop and object
destruction have to be ordered as one lifecycle.

The portal/PipeWire session is also client-driven. A disconnect is expected to
leave a healthy idle sender. A fresh portal session and a new streaming
transition are expected when the next client connects, not immediately after
the previous client disconnects.

## Fix

The accepted lifecycle-v2 design extends the existing reviewed PipeWire runtime
patch.

During capture stop it:

- takes the PipeWire thread-loop lock;
- marks capture stopped;
- invalidates `hasFormat` and `frameData`;
- signals the waiting capture path;
- avoids racing a live stream disconnect against callbacks.

During final teardown it:

- stops and joins the PipeWire thread loop before destroying PipeWire objects;
- destroys the stream with `pw_stream_destroy()`;
- disconnects the existing core connection in the reviewed teardown path;
- destroys the context with `pw_context_destroy()`;
- destroys the thread loop only after it has stopped;
- resets capture state and portal resources.

The combined patch keeps the previously reviewed frame-copy locking behavior
and adds the disconnect-lifetime ordering.

The exact combined runtime patch SHA256 is:

`80c89e6a42902e7526916ac6d4879e4de13e0f55a8afba317ad531d410d0ee2f`

The pinned source commit remains:

`0140a3f6fb616c5636d6c430eb71b8a7d5338e39`

## Integration regressions found while proving the fix

Two harness/integration failures were found without invalidating the runtime
fix.

First, Ansible check mode predicted the temporary runtime patch copy but did
not materialize that temporary file. The following build transaction then
expected a checksum that cannot exist in check mode. The reviewed build block
is therefore skipped with `when: not ansible_check_mode`; normal reconciliation
and change prediction remain active.

Second, a Level-4 acceptance runner treated
`hyperlabctl open looking-glass` like a short-lived launcher. The command
actually finishes by `exec`-replacing itself with the Looking Glass client, so
the runner waited for the GUI process to exit before reaching its health check.
Production acceptance now owns the foreground client in a dedicated user
systemd unit and observes sender health externally.

Neither harness problem required rebuilding or changing the accepted sender
payload.

## Regression proof

The lifecycle-v2 candidate first completed five controlled reconnect cycles.
A corrected client-driven stress then completed twenty additional reconnect
cycles with the same sender process.

Production acceptance on the installed managed sender subsequently completed
ten real host-client connect/disconnect cycles.

Across the production cycles:

- all 10 reconnects reached a new streaming transition;
- all 10 disconnects returned capture to the paused state;
- the sender PID remained `98741`;
- installed and running sender SHA256 remained
  `51f3cbf4277bc717bb69f9387975277d48c18ee08586a03ff6dbc4faa858aa3a`;
- fatal crash regressions remained 0;
- wrong-context regressions remained 0;
- no sender restart was required.

After the ten-cycle stress, a standalone SPICE console opened and remained
usable while Looking Glass was closed. SPICE did not create a new Looking Glass
streaming transition and did not disturb the sender.

The standalone console then closed cleanly and the authoritative production
Looking Glass PRIMARY path was restored. That final reconnect produced another
fresh streaming transition with the same sender PID.

The same completion campaign also rechecked the host 125 percent software
volume ceiling. The managed guest played the same controlled signal at host
100 percent and 125 percent. Machine checks passed and the operator reported
the 125 percent sample as clean, with no audible clipping or distortion.

## Policy

The runtime patch is provenance, not a loose source edit. Its exact SHA is
pinned by role defaults and static/hardware contracts and is recorded in the
installed sender build stamp.

Do not normalize whitespace inside the reviewed patch payload merely to satisfy
a generic repository whitespace check. Normal YAML, Python and documentation
remain subject to ordinary whitespace checks.

A production disconnect acceptance is not complete unless a client can close,
the same sender survives without new fatal or wrong-context markers, a later
client creates a fresh streaming session and the independent SPICE recovery
path still works.
