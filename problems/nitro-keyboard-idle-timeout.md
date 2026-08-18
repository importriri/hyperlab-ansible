# AN515-55 keyboard lighting turns off after idle without a timeout ABI

Author: [importriri](https://github.com/importriri).

## Symptom

The four-zone RGB state remains readable and valid, but after a period without
keyboard use the physical lighting turns off. Pressing a key wakes the lighting
again with the previously programmed colors and brightness.

## What is known

The active Linuwu-Sense AN515-55 sysfs tree exposes no `backlight_timeout` node
and no other file matching `*timeout*` under the active platform driver.

The runtime broker continues to report the expected four-zone value while the
keyboard is idle. Direct `per_zone_mode` readback also retains that value.

This means the observed light-off state is not equivalent to losing the RGB
configuration.

## Current interpretation

The idle transition is firmware or WMI behavior not represented by the validated
sysfs ABI. That is an inference from the absence of a timeout node and the fact
that a keypress restores the existing RGB state; the exact firmware mechanism
has not been proven.

## Policy

Do not expose a Backlight timeout control for AN515-55 unless a real supported
ABI is discovered and physically validated.

The Control Panel must treat configured RGB state and whether the keyboard is
currently emitting light as distinct concepts.

## Closure gate

Keep this problem open until either:

- a real timeout control is discovered and validated on AN515-55; or
- the firmware behavior is characterized well enough to document it as a fixed
  hardware property.

Do not fabricate a sysfs control or map an unrelated setting to this behavior.
