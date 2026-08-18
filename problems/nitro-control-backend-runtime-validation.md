# Nitro runtime broker required physical end-to-end validation

Author: [importriri](https://github.com/importriri).

## Symptom

Static checks could prove that the runtime broker accepted only a small typed
protocol, but they could not prove that the complete privilege boundary reached
the intended AN515-55 hardware or that rejected requests left hardware state
untouched.

## Root cause

The boundary crosses several independently valid layers: a normal-user client,
an AF_UNIX socket, Linux peer credentials, a root broker, the Linuwu-Sense sysfs
ABI, the AN515-55 legacy WMI path, and finally the physical keyboard.

A successful render or unit start is not evidence for the final two layers.

## Validation

The real role apply installed and started the broker, then its normal-user status
probe passed. Runtime ownership was inspected as `root:sid`, with the runtime
directory at `0750` and the socket at `0660`.

The four-zone pattern `ff0000,00ff00,0000ff,ff00ff` was moved from brightness
`100` to `30`. Broker response and direct sysfs readback agreed, and the physical
keyboard became visibly dimmer without changing the four colors.

The pattern was restored to brightness `100`; readback again agreed and the
keyboard became visibly brighter.

Invalid brightness, malformed color, out-of-range fan input and an `effect`
request were all refused. Hardware state remained unchanged after the refusals.

The fan and battery paths were then exercised with their already active values:
`100,100` and enabled. Both succeeded with matching direct readback.

A second real role apply completed with `changed=0`.

## Regression proof

The runtime backend is accepted only when static contracts, check-mode landing,
real normal-user status, physical RGB behavior, refusal isolation and real-run
idempotence all agree.

Firmware effects remain outside this proof.
