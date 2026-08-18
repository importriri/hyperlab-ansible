# Nitro runtime control backend

Author: [importriri](https://github.com/importriri).

The Nitro Control Panel must not write arbitrary sysfs paths and dynamic RGB
must not spawn one privileged process for every frame. The runtime backend
therefore exposes a small local protocol instead of a generic root shell.

## Boundary

The root broker listens on:

```text
/run/hyperlab-nitro/control.sock
```

The socket is reachable only through the configured host operator group. The
broker additionally checks Linux peer credentials and accepts the configured
operator UID or root.

Requests never contain filesystem paths. The accepted operations are:

- `status`
- `set_fan` with CPU and GPU percentages in `0..100`
- `set_battery_limiter` with a boolean
- `set_rgb` with exactly four `RRGGBB` values and brightness in `0..100`

Firmware effects are not part of the protocol. The AN515-55 campaign proved
static four-zone color and brightness, not the separate effect WMI path.

## Runtime ownership

The broker changes live hardware state only. It does not rewrite Ansible
defaults, systemd boot policy or repository files.

A reboot therefore returns fan, battery and keyboard policy to the reviewed
`nitro_sense` settings service. A future persistent GUI action needs a separate
ownership contract; it must not emerge accidentally from the runtime API.

## Dynamic RGB

The broker enforces a minimum interval between RGB writes. The initial limit is
200 ms, which caps callers at five writes per second.

Theme Sync, Trust and Ambient providers can later feed validated four-zone
frames through this same operation without gaining a filesystem or shell
primitive.

## Manual client

The installed normal-user client is:

```text
/usr/local/bin/hyperlab-nitro-control
```

Examples:

```bash
hyperlab-nitro-control status
hyperlab-nitro-control fan 100 100
hyperlab-nitro-control battery on
hyperlab-nitro-control rgb 30 ff0000 00ff00 0000ff ff00ff
```

Every command returns one JSON object and exits non-zero when the broker refuses
the request.

## Nitro AN515-55 hardware validation

The first hardware landing on the Nitro AN515-55 completed with the runtime
broker enabled and the normal-user status probe passing through the real Unix
socket. The installed boundary was then audited directly:

- the service was active under `root:sid`;
- `/run/hyperlab-nitro` was `root:sid` mode `0750`;
- `control.sock` was `root:sid` mode `0660`;
- the normal `sid` account could query status without `sudo`;
- the reported model was `Nitro AN515-55`;
- `fan`, `battery_limiter` and `per_zone` were available;
- `effect` was false;
- persistence remained `runtime-only`.

The RGB path was exercised with the already reviewed four-zone pattern. Moving
brightness from `100` to `30` preserved red, green, blue and magenta while the
keyboard became visibly dimmer. The broker status and direct sysfs readback both
reported:

```text
ff0000,00ff00,0000ff,ff00ff,30
```

Restoring brightness to `100` produced the inverse physical change while
preserving the same four colors.

Requests outside the protocol were refused before hardware state changed:
brightness `101`, a malformed color, fan CPU `101`, and the unsupported
`effect` operation all returned errors. The subsequent broker status and direct
RGB readback were unchanged.

The fan and battery positive paths were then exercised with their already active
values. `fan 100 100` and `battery on` both succeeded, direct readback remained
`100,100` and `1`, and no policy change was introduced.

A second real Ansible run completed with `changed=0`, proving idempotence after
the broker installation and runtime tests.

## Exact request schemas

The privileged broker treats the accepted JSON object shape as part of the
security boundary. Every operation has an exact field set:

- `status`: `op`
- `set_fan`: `op`, `cpu`, `gpu`
- `set_battery_limiter`: `op`, `enabled`
- `set_rgb`: `op`, `zones`, `brightness`

Missing and unexpected keys are refused before the operation handler runs.
This matters even though hardware paths are already fixed by the root-owned
systemd unit: silently ignored fields make a privileged protocol ambiguous and
can hide client/server version drift.

The normal client already emits only these reviewed fields.

## Exact-field runtime proof

The exact JSON schema boundary was exercised on the Acer Nitro AN515-55 after
the hardened broker was installed and restarted by the role.

A normal-user read-only `status` request carrying an unexpected `path` field was
rejected with `ok: false`. Broker status before and after the refusal was
identical, including fan state `100,100`, enabled battery limiter and RGB
readback `ff00ff,00ff00,0000ff,ff00ff,100`.

The second real Nitro Sense apply completed with `changed=0` and `failed=0`.
