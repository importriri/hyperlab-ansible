# Nitro runtime broker accepted unexpected JSON fields

Author: [importriri](https://github.com/importriri).

Status: proved on Acer Nitro AN515-55.

## Symptom

The initial broker validated operation names and the values it consumed, but it
did not require an exact JSON object shape. A request could therefore carry an
unrelated extra key and still reach a valid operation handler.

For example, a `status` request containing an invented `path` field would ignore
that field rather than refusing the malformed request.

## Security impact

The broker did not use caller-supplied filesystem paths, so an extra `path`
field could not redirect a write. Fan, battery and RGB paths still came only
from the root-owned systemd unit.

The problem was protocol ambiguity instead: a privileged API should fail closed
when a client sends fields that were never reviewed. Ignoring unknown fields can
hide version skew, misspelled field names or a future client assumption that the
broker does not actually implement.

## Fix

Each operation now has one exact field set. Request shape is validated before
the operation handler runs:

- `status` accepts only `op`;
- `set_fan` accepts only `op`, `cpu` and `gpu`;
- `set_battery_limiter` accepts only `op` and `enabled`;
- `set_rgb` accepts only `op`, `zones` and `brightness`.

Both missing and unexpected keys are refused. Value validation and the existing
fixed-path, peer-credential and rate-limit boundaries remain unchanged.

## Regression gate

The structural and unit contracts must prove the exact schemas before
deployment.

On the Nitro host, a raw read-only `status` request with an extra field must
return `ok: false`. Broker status before and after that refusal must be
identical. The test deliberately avoids a write operation so hardware state is
not changed merely to prove parser behavior.

A second real `nitro-sense.yml` apply must then complete with `changed=0`.

## Runtime validation

The exact-field protocol gate was validated on the Acer Nitro AN515-55 after
deployment through `nitro-sense.yml`.

A normal-user client first read the broker status. A raw read-only request was
then sent over the broker socket with an unexpected field:

`{"op":"status","path":"/etc/shadow"}`

The hardened broker refused the request with `ok: false` and reported
`invalid request fields for status: unexpected path`.

A second normal status read was byte-for-byte identical to the first one. Fan
state remained `100,100`, the battery limiter remained enabled and four-zone
RGB readback remained `ff00ff,00ff00,0000ff,ff00ff,100`.

This proves that unexpected fields are rejected before a handler can mutate
hardware state. The existing fixed-path boundary also remained intact: the
invented `path` field could not redirect a filesystem operation.

A second real `nitro-sense.yml` apply completed with `changed=0` and `failed=0`,
proving role idempotence after the protocol hardening.
