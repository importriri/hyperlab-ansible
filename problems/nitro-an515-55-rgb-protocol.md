# AN515-55 four-zone RGB accepted writes but turned the keyboard off

Author: [importriri](https://github.com/importriri).

## Symptom

The Linuwu-Sense four-zone sysfs interface accepted color writes on the Nitro
AN515-55 and returned the requested values on readback, but the physical
keyboard turned off instead of showing those colors.

A successful sysfs write was therefore not sufficient hardware evidence. The
driver could update its software state while sending a WMI payload that this
machine did not interpret as the intended keyboard command.

## What was wrong

The pinned Linuwu-Sense source treated the AN515-55 as a legacy Nitro model and
did not advertise its four-zone keyboard capability. Simply enabling the
generic four-zone quirk exposed the interface, but the generic per-zone path
still used the wrong command shape for this hardware.

The generic path sent each zone through the u64 WMI helper. That helper builds
an eight-byte input buffer. Older AN515-55 support used a four-byte payload for
the same gaming method:

```text
zone-mask, red, green, blue
```

The zone selector is a bit mask, not an ordinal. The four hardware zones use
`0x01`, `0x02`, `0x04` and `0x08`.

The machine also needed the gaming LED enable sequence before the zone writes,
followed by an explicit static keyboard mode selection. Without that complete
sequence, a write could look valid from sysfs while leaving the physical
backlight off.

## Fix

Keep the upstream Linuwu-Sense commit pinned and carry a reviewed AN515-55
overlay instead of modifying the managed source checkout.

The AN515-55 quirk now declares both the four-zone keyboard and its legacy
payload requirement. Only that quirk takes the compatibility path.

Before writing colors, the compatibility path performs the gaming-system query
and enables all four keyboard zones. It then sends one four-byte WMI payload per
zone using the hardware bit masks and finishes with the static-mode payload that
carries the requested brightness.

Other models remain on the upstream path. The compatibility code is deliberately
scoped to the DMI quirk that was proved on the AN515-55 rather than changing the
wire format globally.

The reviewed overlay has SHA-256:

```text
1a53b4709330ae86dcae16f2efd55ce9468e2cd2d850b48d0f6902641457a778
```

With pinned source commit
`73a25ec243a44ba2b1703e8d0a76fa2735062506`, the managed DKMS identity is
`6b45d4439e68`.

## Regression proof

The final overlay compiled successfully against the running hardened kernel.
A later runtime audit showed the target module loaded from the DKMS path and
both documented four-zone sysfs nodes present without new kernel errors. The
exact operation that first installed the already-satisfied target is tracked by
the separate DKMS provenance investigation.

Hardware checks on the Nitro AN515-55 proved all behavior needed by the static
software RGB engine:

- one static red value lit all four physical zones red;
- four different values produced red, green, blue and magenta on four distinct
  physical zones;
- brightness values `10`, `30` and `100` changed physical keyboard brightness
  while preserving the requested colors;
- every checked write had matching sysfs readback and produced no new kernel
  messages.

The earlier failure is the reason future RGB acceptance must include a physical
observation. Readback alone does not prove that an Acer WMI lighting command had
the intended hardware effect.

Animated firmware effects remain outside this proof. Static color, independent
four-zone color and brightness are the only RGB capabilities validated by this
campaign.
