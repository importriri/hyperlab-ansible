# Nitro AN515-55 hardware campaign

This note records the hardware observations that define the current
`nitro_sense` contract on the tested Acer Nitro AN515-55.

It is intentionally narrower than a model compatibility claim. Every capability
listed as proved below was observed on the physical machine; anything else
remains conditional on a separate hardware test.

## Machine boundary

The tested machine identifies as an Acer Nitro AN515-55 with board
`Stonic_CMS`. The host desktop runs on the Intel integrated GPU while the RTX
3060 display and audio functions remain bound to `vfio-pci`.

The Nitro control role must not pull a host NVIDIA desktop stack into this
arrangement. Platform controls and GPU ownership are independent boundaries.

The running hardened-kernel campaign used
`7.1.8-hardened1-2-hardened`.

## Native-first result

The machine did not expose `/sys/firmware/acpi/platform_profile`.

That absence is why the requested manual fan policy cannot be represented by
the generic platform-profile ABI. Replacing `acer_wmi` remains an explicit
opt-in and is never inferred solely from the product name.

## Reviewed source identity

The replacement uses Linuwu-Sense commit:

```text
73a25ec243a44ba2b1703e8d0a76fa2735062506
```

The AN515-55 compatibility overlay has SHA-256:

```text
1a53b4709330ae86dcae16f2efd55ce9468e2cd2d850b48d0f6902641457a778
```

The composite managed DKMS version for that pair is:

```text
6b45d4439e68
```

The pinned source checkout stays pristine. The overlay is applied only to an
isolated build probe and the managed DKMS copy.

## Fan and battery policy

This lab deliberately requests maximum fan duty at boot:

```text
CPU fan: 100
GPU fan: 100
```

The setting helper is required to read back `100,100` after writing it. A
successful oneshot service without that readback is not sufficient evidence.

The battery limiter is enabled and reads back `1`.

This campaign manages the tested limiter only through the documented Nitro
node. It does not claim that the machine lacks every other battery
charge-threshold ABI; those interfaces were outside this hardware audit.

## Four-zone keyboard

The upstream legacy quirk did not advertise AN515-55 RGB support. Exposing the
generic four-zone path alone was not enough: the first color writes were
accepted by sysfs but turned the physical keyboard off.

Hardware validation established the AN515-55 command sequence carried by the
repository overlay:

1. query gaming-system state;
2. enable all four keyboard zones;
3. send four-byte static color payloads with zone masks `1`, `2`, `4`, `8`;
4. select static keyboard mode with the requested brightness.

The following capabilities are physically proved:

- one static color across all four zones;
- four independent zone colors;
- brightness changes at `10`, `30` and `100`.

A red/green/blue/magenta test produced those four colors on four distinct
physical zones. No new kernel messages appeared during the validated writes.

Animated firmware effects are not part of the proof. The control panel must not
present an effect as hardware-supported until that exact path has a separate
physical validation.

## Persistence boundary

RGB writes are not persisted merely because the sysfs node accepts them.

The future control panel needs an explicit RGB policy and a narrow privileged
helper. The normal-user UI must select a validated mode and values; it must not
become a generic sysfs writer.

The same boundary applies to monitor-reactive RGB. A high-frequency desktop
effect must be rate-limited and tested as a workload before it is allowed to
turn reverse-engineered WMI calls into a continuous update loop.

## Lifecycle acceptance

The reviewed candidate completed the AN515-55 runtime, suspend and recovery
campaign on `2026-08-18`.

The genuine suspend proof waited for the kernel `PM: suspend exit` event before
collecting post-resume state. Both Nitro services returned active and enabled,
fan policy read back `100,100`, the battery limiter read back `1`, broker state
matched the pre-suspend state, and `wlan0` was `UP,LOWER_UP` with a usable route.
Brightness, volume, Wi-Fi, the Nitro key and fan behavior passed physical checks
after resume.

The controlled recovery transaction then completed with:

- rollback: `ok=46`, `changed=10`, `failed=0`;
- reinstall: `ok=113`, `changed=32`, `failed=0`;
- second run: `ok=91`, `changed=0`, `failed=0`.

Rollback removed the managed DKMS, source, service, client, boot-policy and
ownership boundaries and restored `acer_wmi`. Brightness, volume, Wi-Fi and the
Nitro key worked on the restored in-tree driver.

Reinstall rebuilt the pinned source and overlay, restored the exact DKMS module
and build stamp, activated both services and restored fan `100,100`, battery
limiter `1` and four-zone state `ff00ff,00ff00,0000ff,ff00ff,30`. All physical
controls, maximum-fan behavior and the four expected keyboard zones passed
again. The transition journal contained no driver error, failure, timeout, oops
or kernel bug, and recorded zero function-four unknown events during that
transition.

The separate suspend window recorded 48
`Unknown function number - 4 - 0` messages while physical keys were exercised.
No tested function regressed, so the message is tracked as an open observation
rather than silently suppressed. See
[`../problems/nitro-wmi-unknown-function-four.md`](../problems/nitro-wmi-unknown-function-four.md).

The first suspend snapshot raced the real sleep cycle; the corrected proof and
its lifecycle rule are recorded in
[`../problems/nitro-suspend-resume-evidence-race.md`](../problems/nitro-suspend-resume-evidence-race.md).

The rollback/reinstall boundary is now proved: the campaign observed complete
removal followed by a build and installation of version `6b45d4439e68`, then a
real second run with `changed=0`. This does not identify the historical command
that first produced the previously observed already-satisfied state; that
provenance question remains open. A future source, overlay, kernel or
DKMS-version change still requires a new transition proof.

This acceptance applies to the exact candidate and tested machine. It does not
replace the frozen-release replay or extend compatibility to another Acer
model.

## Runtime control broker evidence

The AN515-55 runtime broker has been exercised on physical hardware through the
normal user boundary rather than by writing sysfs directly.

Validated operations:

- read fan state;
- no-op fan write at `100,100`;
- read battery limiter state;
- no-op battery limiter write at enabled;
- read four-zone RGB state;
- four-zone RGB brightness transition `100 -> 30 -> 100`;
- refusal of out-of-range and malformed requests;
- refusal of the unsupported firmware-effect operation.

The four-zone brightness transition was confirmed physically in both directions.
The colors remained red, green, blue and magenta while the keyboard became
visibly dimmer at `30` and brighter again at `100`.

The installed broker reports `effect=false` on this model. No firmware effect is
considered validated by this campaign.
