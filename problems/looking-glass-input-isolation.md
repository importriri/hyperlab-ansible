# Looking Glass video is proven but the input-isolation gate is still open

Author: [importriri](https://github.com/importriri).

Status: open acceptance gate.

## Symptom

The Linux guest produces real Looking Glass frames through the headless
Hyprland, PipeWire and kvmfr path, but video success does not prove that keyboard
and pointer capture are isolated from host shortcuts.

A visually correct accelerated guest can still be unsafe to operate if a key
sequence intended for the guest also triggers the host compositor.

## What is already proved

The guest can expose `HEADLESS-0` at `1920x1080@144`, the Linux sender can be
started manually from the graphical session and the physical host client can
receive frames.

The sender intentionally has no persistent user or system service. Starting it
is an explicit action because capture is part of the lab boundary, not a
background desktop requirement.

The managed host-client acceptance baseline is:

```text
escapeKey=KEY_RIGHTCTRL
captureOnFocus=yes
autoCapture=yes
```

Performance experiments may override automatic capture for one run. Those
runtime overrides are not the acceptance baseline and must not be mistaken for
the installed client policy.

## Remaining proof

Acceptance must test capture and release independently from video:

- host shortcuts are inhibited while guest input is captured;
- the configured release chord reliably returns control to the host;
- pointer return works independently from keyboard return;
- lock, unlock and guest reconnect do not leave input captured unexpectedly.

Mode shortcuts that could hide or alter the capture state stay out of the guest
until this gate is closed.

## Why this is a separate problem

Frame transport and input ownership fail independently. Keeping them in one
"Looking Glass works" checkbox would allow a successful video test to hide an
input-boundary regression.
