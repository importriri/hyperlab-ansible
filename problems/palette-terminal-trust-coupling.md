# Foot ANSI colors were coupled to trust-domain tokens

Author: [importriri](https://github.com/importriri).

## Symptom

Making `clean`, `dev`, `services`, `dirty` and `lab` immutable across desktop
themes also changed Foot colors in Blue, Red and Violet.

The trust fix was correct, but ordinary terminal ANSI output had accidentally
depended on the same tokens.

## What was wrong

`render_palette.py` used `dom_dev`, `dom_lab` and `dom_services` as Foot ANSI
slots 4, 5 and 14.

Those names describe security identity in HyperLab. ANSI slots describe terminal
appearance. Reusing one vocabulary for both meant a security-semantic change
could recolor unrelated shell output.

The renderer also still carried a Superfile writer after the desktop migration
had removed Superfile from the managed host.

## Fix

Give the affected ANSI slots explicit theme-owned tokens and preserve each
theme's pre-separation terminal colors in those slots.

Generated GTK, Waybar, Rofi and Sway fragments continue to receive theme plus
canonical trust tokens; they do not receive terminal-only ANSI tokens.

Remove the retired Superfile writer instead of allowing a palette render to
recreate a deleted desktop component.

## Regression proof

Green, Violet, Blue and Red all render the same canonical five trust colors.

Their Foot fragments keep the reviewed theme-specific ANSI slot values that
existed before trust was centralized. A domain-color change can no longer alter
those terminal slots.

The renderer no longer produces `hyperlab-palette-superfile.toml`, and the
already-removed runtime fragments remain absent.
