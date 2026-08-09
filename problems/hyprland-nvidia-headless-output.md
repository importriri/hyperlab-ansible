# NVIDIA-only Hyprland started with no monitor

Author: [importriri](https://github.com/importriri).

## Symptom

Hyprland was running on the passed RTX 3060, `nvidia-smi` was healthy and the
pre-compositor NVIDIA variables were present, but `hyprctl -j monitors` returned
an empty list. `grim` failed because there was no `wl_output`.

## What was wrong

The guest was intentionally restricted to the NVIDIA DRM device. The only
physical connector on that GPU was disconnected. Hyprland accepted the no-KMS
startup policy, but this setup did not create a headless output automatically.

A monitor rule can configure an output; it cannot create one.

## Fix

Create `HEADLESS-0` once from the `hyprland.start` callback. Keep resolution,
position and scale in the normal monitor rule.

That split matters: startup creates the object, while configuration continues to
own `1920x1080@144`, `0x0`, scale `1`.

## Regression proof

The runtime callback test created a second named headless output successfully.
The managed `HEADLESS-0` resolved to 1920×1080 at 144 Hz, scale 1, and `grim`
produced a 1920×1080 PNG. The role then deployed the callback and a second apply
reported `changed=0`.
