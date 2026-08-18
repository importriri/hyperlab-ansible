# One Nitro RGB allowlist authorized two different WMI capabilities

Author: [importriri](https://github.com/importriri).

## Symptom

`nitro_sense_four_zone_models` was used for both `per_zone` and `effect` LED
modes.

After the AN515-55 static protocol was physically proved, adding that model to
the shared allowlist would also have authorized `four_zone_mode`, even though
the campaign had not proved firmware effects on this machine.

## What was wrong

A four-zone keyboard is a hardware shape, not one indivisible software
capability.

The validated AN515-55 path writes four static zone colors and brightness
through its legacy payload. Firmware effects use a different sysfs node and WMI
command path. Evidence for one cannot authorize the other.

## Fix

Split the model policy into separate per-zone and effect allowlists.

AN515-55 enters the per-zone allowlist because static red, four independent
colors and brightness `10`, `30`, `100` were physically observed. It remains
absent from the effect allowlist.

Preflight chooses the allowlist from the requested LED mode and refuses the
request before package installation.

## Regression proof

A `per_zone` request for the reviewed AN515-55 can pass the model capability
gate when the out-of-tree replacement is explicitly enabled.

An `effect` request for the same model is refused by policy. The broader effect
path stays unavailable until that exact hardware behavior receives its own
physical validation.
