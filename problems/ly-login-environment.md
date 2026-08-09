# Ly had the right config but Hyprland had the wrong environment

Author: [importriri](https://github.com/importriri).

## Symptom

The Ly configuration pointed at the new login wrapper, but a newly opened
Hyprland session still used the QEMU virtual display and the compositor process
did not contain the expected NVIDIA-only variables.

## What was wrong

The Ly service itself had not been restarted after its configuration changed.
Closing only the graphical session left the display-manager process alive with
the configuration it had already loaded.

## Fix

Use Ly `login_cmd` for the pre-compositor wrapper and reload the Ly service when
that setting changes. The wrapper exports the NVIDIA policy before handing the
selected session command back to Ly.

## Regression proof

The Ly log later showed the wrapper in the actual session command, and the
Hyprland process environment contained both NVIDIA-only variables before any
monitor work was done.
