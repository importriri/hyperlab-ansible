# Nitro backend was hidden by the out-of-tree check-mode stop

Author: [importriri](https://github.com/importriri).

## Symptom

The first `nitro-sense.yml --check --diff` after adding the runtime control
backend was green, but none of the broker, client or unit landing tasks appeared
in the preview.

The recap therefore proved the existing driver refusal boundary, not the new
runtime backend files.

## What was wrong

The role intentionally stops the out-of-tree driver path before package
installation, compilation, DKMS and driver transition in check mode.

The backend was mounted only from `configure.yml`, which is reached after that
real driver transition. Reusing the same stop point accidentally hid the new
non-destructive file landing from check mode.

Starting systemd services or flushing restart handlers in that preview would be
wrong as well, because check mode does not actually install the unit file.

## Fix

Keep the driver transition stop exactly where it is, but include the narrow
runtime backend tasks separately in check mode.

The read-only identity checks and file/template tasks may preview normally.
Service start, handler flush, runtime probe and restart handler are guarded out
of check mode.

This preserves the reason the original stop exists while making new backend
files visible to `--check --diff`.

## Regression proof

The structural backend contract requires the check-mode include and the
non-mutating service guards.

Hardware acceptance still requires a Nitro `--check --diff` run to show the
broker, client and unit as predicted changes without starting the service or
writing fan, battery or RGB state.
