# Group 16 asked about the desktop before the stream was healthy

Seen on Nitro, 2026-10-12, in group 16 (`16-looking-glass-sender-171244`):
FAIL at "health is ok before the still phase", health `idle`. The operator
had just answered that Looking Glass showed dev-01's desktop.

## What happened

- The new sender (pid 736283, this build: identity PASS) logged `Capture
  Start` at +0.058 s, its start-up test of the capture, then `Capture Stop`
  at +0.064 s, and nothing more for the next 190 s. Its main thread waited in
  `hrtimer_nanosleep`, the idle loop's `usleep(100000)` (`host/src/app.c:988`):
  no Looking Glass client was subscribed to it. There was no PipeWire thread.
- `hyperlabctl looking-glass health` reads the last capture line: `Capture
  Stop` is `idle` (`looking_glass.py` `stream_state`, `verdict`). The health
  was right.
- The window still showed dev-01. Until frames arrive from the sender, the
  client shows the guest's SPICE display (`client/src/main.c:1486-1491`,
  "use the spice display until we get frames from the LG host application"),
  and HyperLab always gives it `spice:host=`. To the operator that looks
  like the stream.
- The script asked "Does Looking Glass show dev-01's desktop?" first and
  checked the health after. The answer could not tell the two apart, and
  the failure said only `idle`.

Read-only evidence: `readonly-after-fail-*/` in that run's directory.

## Fix

The script waits up to 60 s for the health word `ok` and only then asks the
operator; an operator who answers no stops the group before the still
phase. When the health stays `idle`, the report says that no Looking Glass
client is connected to the sender and that a window showing dev-01 is the
client's SPICE display, not the stream.

## Regression proof

`tests/acceptance_scripts_contract.py` runs group 16 against fake tools
(`sleep` returns at once and records what it was asked):

- healthy run: the health PASS comes before the operator's answer. Against
  the previous script: `16 asks whether the desktop shows before the stream
  is healthy`;
- health stays `idle`: FAIL, no question to the operator, the report names
  the missing client and the SPICE display, 13 health answers over 60 s.
  Against the previous script: `16 asked the operator before the stream was
  healthy`;
- the operator answers no: FAIL, and the still phase does not run.

Reviewed and left as they are (2026-10-12): the 60 s start as soon as the
script asks to open Looking Glass, so an operator who needs longer runs the
group again (the message states the 60 s); a health other than `idle`, such
as `sender-down`, gets no explanation line beyond the health answer in the
evidence.

## Still open

Why the client did not connect to the new sender is not known: after a
sender restart it should reconnect by itself (`client/src/main.c:1789-1810`),
and its output went to `/dev/null`. Another running VM sharing
`/dev/kvmfr0` is ruled out: the operator checked by hand that only dev-01
and arch-dev-vfio (shut off) declare it.
