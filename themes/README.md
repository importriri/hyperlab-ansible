# HyperLab themes

HyperLab themes are declarative packages discovered from this directory.

Each theme owns presentation policy for the HyperLab desktop without gaining
authority over security state or arbitrary command execution.

A theme may define presentation for:

- Quickshell;
- GTK;
- Rofi;
- lockscreen;
- host Foot;
- guest Kitty;
- wallpaper;
- keyboard RGB.

The active theme is selected through the HyperLab Shell. Theme manifests are
data, not executable plugins.

`trust-model` is the first canonical theme. It binds selected presentation
outputs to host-owned trust provenance. The theme never decides or changes the
trust classification itself.

The legacy Green, Violet, Blue and Red themes remain only as temporary rollback
material during migration. They are removed after the new registry, visual
assets and physical Nitro acceptance are complete.
